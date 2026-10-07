"""NSE equity (cash market) bhavcopy — survivorship-free daily prices, raw.

One file per trading day since 1994, delisted names included. Two formats:

  legacy  .../content/historical/EQUITIES/{YYYY}/{MON}/cm{DD}{MON}{YYYY}bhav.csv.zip
          up to 2024-07-05. Columns SYMBOL, SERIES, OPEN … TOTTRDVAL (ISIN only
          from late 2010).
  UDiFF   .../content/cm/BhavCopy_NSE_CM_0_0_0_{YYYYMMDD}_F_0000.csv.zip
          from 2024-07-08. Same facts, ISO-style column names.

Both are normalised to one schema and stored one parquet per year under
data/bhav/eq/<YYYY>.parquet. Only the equity series that matter for an index
universe are kept (EQ, BE, BZ, SM excluded — see SERIES).

Prices are UNADJUSTED. `PREVCLOSE` is not rebased on ex-dates (tested on the
2017 Reliance bonus — research/04 §7.1), so returns across a split or bonus
are wrong until obs/corpactions.py adjusts them.

Storage policy: data/bhav/ is gitignored. The archive is NSE's own, immutable
and public, so the files are regenerable at any time with
    python build_bhav.py            # incremental; ~5,800 requests from scratch
unlike yfinance snapshots, which revise and must be committed.
"""

from __future__ import annotations

import io
import time as _time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from .flows import UA
from .store import DATA_ROOT

BHAV = DATA_ROOT / "bhav" / "eq"
HOST = "https://nsearchives.nseindia.com/content"
UDIFF_FROM = date(2024, 7, 8)
SERIES = ("EQ", "BE")  # EQ = rolling settlement, BE = trade-for-trade (stocks under surveillance stay listed)
COLS = ["symbol", "series", "isin", "open", "high", "low", "close", "prevclose", "volume", "turnover"]


def url_for(d: date) -> str:
    if d >= UDIFF_FROM:
        return f"{HOST}/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
    mon = d.strftime("%b").upper()
    return f"{HOST}/historical/EQUITIES/{d:%Y}/{mon}/cm{d:%d}{mon}{d:%Y}bhav.csv.zip"


def parse(raw: bytes, d: date) -> pd.DataFrame:
    """One day's zip → normalised frame (EQ/BE rows only)."""
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        df = pd.read_csv(z.open(z.namelist()[0]))
    df.columns = [c.strip() for c in df.columns]
    if "TckrSymb" in df.columns:
        df = df.rename(columns={"TckrSymb": "symbol", "SctySrs": "series", "ISIN": "isin", "OpnPric": "open",
                                "HghPric": "high", "LwPric": "low", "ClsPric": "close",
                                "PrvsClsgPric": "prevclose", "TtlTradgVol": "volume", "TtlTrfVal": "turnover"})
    else:
        df = df.rename(columns={"SYMBOL": "symbol", "SERIES": "series", "ISIN": "isin", "OPEN": "open",
                                "HIGH": "high", "LOW": "low", "CLOSE": "close", "PREVCLOSE": "prevclose",
                                "TOTTRDQTY": "volume", "TOTTRDVAL": "turnover"})
    if "isin" not in df.columns:
        df["isin"] = pd.NA
    df["series"] = df["series"].astype(str).str.strip()
    df = df[df["series"].isin(SERIES)][COLS].copy()
    df["symbol"] = df["symbol"].astype(str).str.strip()
    for c in ["open", "high", "low", "close", "prevclose", "turnover"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").astype("int64")
    df.insert(0, "date", pd.Timestamp(d))
    return df.reset_index(drop=True)


def fetch_day(d: date, session: requests.Session, tries: int = 3) -> pd.DataFrame | None:
    """None on 404 (a holiday). Retries other failures."""
    for attempt in range(tries):
        try:
            r = session.get(url_for(d), timeout=30)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return parse(r.content, d)
        except Exception:
            if attempt == tries - 1:
                raise
            _time.sleep(3 * (attempt + 1))
    return None


def _path(year: int) -> Path:
    return BHAV / f"{year}.parquet"


def stored_dates(year: int) -> set[pd.Timestamp]:
    p = _path(year)
    return set(pd.read_parquet(p, columns=["date"])["date"].unique()) if p.exists() else set()


def _holidays_file() -> Path:
    return BHAV / "_holidays.txt"


def known_holidays() -> set[str]:
    p = _holidays_file()
    return set(p.read_text().split()) if p.exists() else set()


def update(start: str = "2004-01-01", end: str | None = None, workers: int = 6, log=print) -> int:
    """Fetch every missing weekday in [start, end]. Incremental and idempotent:
    stored days and confirmed holidays are skipped. Returns rows added."""
    BHAV.mkdir(parents=True, exist_ok=True)
    end_ts = pd.Timestamp(end) if end else pd.Timestamp.today().normalize() - pd.Timedelta(days=1)
    days = pd.bdate_range(start, end_ts)
    holidays = known_holidays()
    added = 0
    for year in sorted(set(days.year)):
        have = stored_dates(year)
        todo = [d.date() for d in days[days.year == year] if d not in have and str(d.date()) not in holidays]
        if not todo:
            continue
        s = requests.Session()
        s.headers.update(UA)
        with ThreadPoolExecutor(workers) as ex:
            got = list(ex.map(lambda d: (d, fetch_day(d, s)), todo))
        frames = [df for _, df in got if df is not None and len(df)]
        new_holidays = [str(d) for d, df in got if df is None]
        if new_holidays and pd.Timestamp(max(new_holidays)) < end_ts - pd.Timedelta(days=7):
            # only remember 404s that are old enough not to be "not published yet"
            with _holidays_file().open("a") as f:
                f.write("\n".join(new_holidays) + "\n")
        if frames:
            p = _path(year)
            old = [pd.read_parquet(p)] if p.exists() else []
            out = pd.concat(old + frames).sort_values(["date", "symbol", "series"]).reset_index(drop=True)
            out.to_parquet(p, compression="zstd")
            added += sum(len(f) for f in frames)
        log(f"bhav {year}: +{len(frames)} days, {len(new_holidays)} holidays")
    return added


def load(start: str | None = None, end: str | None = None, columns: list[str] | None = None) -> pd.DataFrame:
    files = sorted(BHAV.glob("[0-9]*.parquet"))
    if start:
        files = [f for f in files if int(f.stem) >= pd.Timestamp(start).year]
    if end:
        files = [f for f in files if int(f.stem) <= pd.Timestamp(end).year]
    if not files:
        raise FileNotFoundError("no bhavcopy stored — run build_bhav.py")
    df = pd.concat([pd.read_parquet(f, columns=columns) for f in files], ignore_index=True)
    if start:
        df = df[df["date"] >= pd.Timestamp(start)]
    if end:
        df = df[df["date"] <= pd.Timestamp(end)]
    return df


# ------------------------------------------------------------- F&O membership

def fo_url(d: date) -> str:
    if d >= UDIFF_FROM:
        return f"{HOST}/fo/BhavCopy_NSE_FO_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
    mon = d.strftime("%b").upper()
    return f"{HOST}/historical/DERIVATIVES/{d:%Y}/{mon}/fo{d:%d}{mon}{d:%Y}bhav.csv.zip"


def fo_stocks(d: date, session: requests.Session | None = None) -> set[str] | None:
    """Symbols with stock futures trading on day d (the index's F&O eligibility test).
    None if d was a holiday."""
    s = session or requests.Session()
    s.headers.update(UA)
    r = s.get(fo_url(d), timeout=60)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        df = pd.read_csv(z.open(z.namelist()[0]), low_memory=False)
    df.columns = [c.strip() for c in df.columns]
    if "FinInstrmTp" in df.columns:
        return set(df.loc[df["FinInstrmTp"].astype(str).str.strip() == "STF", "TckrSymb"].astype(str).str.strip())
    return set(df.loc[df["INSTRUMENT"].astype(str).str.strip() == "FUTSTK", "SYMBOL"].astype(str).str.strip())
