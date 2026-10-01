"""Index constituent lists — the point-in-time membership problem.

NSE publishes only the *current* membership of each index. No free source
holds the history, so this module builds it two ways:

  forward   capture_constituents() stores a dated snapshot whenever a list
            changes. From the first capture onward membership is exact.
  backward  backfill_wayback() pulls the Internet Archive's dated copies of the
            same files. Sparse (a handful of versions per index, 2017 onward),
            so these are validation anchors, not a continuous history.

A snapshot dated D says what the file contained on D — a change takes effect
on NSE's effective date, which can be days earlier. Treat membership as
accurate to roughly a week around index reviews (March and September).

Stored like price snapshots: raw/constituents_<index>/<YYYY-MM-DD>.parquet,
only when content differs from the previous snapshot.
"""

from __future__ import annotations

import re
import time as _time
from datetime import date
from io import StringIO

import pandas as pd
import requests

from .flows import MAX_STREAK, UA
from .store import RAW, latest_snapshot, raw_path, read_raw, write_raw

# index key -> (file name, expected constituents)
INDEX_FILES = {
    "nifty50": ("ind_nifty50list.csv", 50),
    "niftynext50": ("ind_niftynext50list.csv", 50),
    "nifty100": ("ind_nifty100list.csv", 100),
    "nifty200": ("ind_nifty200list.csv", 200),
    "niftymidcap100": ("ind_niftymidcap100list.csv", 100),
    "nifty200_momentum30": ("ind_nifty200Momentum30_list.csv", 30),
}
HOSTS = ["https://nsearchives.nseindia.com/content/indices/",
         "https://www.niftyindices.com/IndexConstituent/"]
COLUMNS = ["company", "industry", "symbol", "series", "isin"]
ISIN = re.compile(r"^IN[A-Z0-9]{10}$")


def store_key(index: str) -> str:
    return f"constituents_{index}"


def parse_list(text: str, index: str) -> pd.DataFrame:
    """Parse and validate one constituent file; raises ValueError if it is not one."""
    if not text.lstrip().startswith("Company Name"):
        raise ValueError(f"{index}: not a constituent file (starts {text[:40]!r})")
    df = pd.read_csv(StringIO(text))
    df.columns = [str(c).strip() for c in df.columns]
    rename = {"Company Name": "company", "Industry": "industry", "Symbol": "symbol",
              "Series": "series", "ISIN Code": "isin"}
    if not {"Company Name", "Symbol", "ISIN Code"} <= set(df.columns):
        raise ValueError(f"{index}: unexpected columns {list(df.columns)}")
    df = df.rename(columns=rename)
    df = df[[c for c in COLUMNS if c in df.columns]].copy()
    for c in df.columns:
        df[c] = df[c].astype(str).str.strip()
    df = df.sort_values("symbol").reset_index(drop=True)

    want = INDEX_FILES[index][1]
    if len(df) != want:
        raise ValueError(f"{index}: {len(df)} constituents, expected {want}")
    if df["symbol"].duplicated().any():
        raise ValueError(f"{index}: duplicate symbols")
    bad = df.loc[~df["isin"].str.match(ISIN), "isin"].tolist()
    if bad:
        raise ValueError(f"{index}: malformed ISINs {bad[:3]}")
    return df


def fetch_list(index: str) -> pd.DataFrame:
    name = INDEX_FILES[index][0]
    last = None
    for host in HOSTS:
        try:
            r = requests.get(host + name, headers=UA, timeout=30)
            r.raise_for_status()
            return parse_list(r.text, index)
        except Exception as exc:
            last = exc
    raise RuntimeError(f"{index}: every host failed; last: {last!r}")


def _same(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    cols = ["symbol", "isin"]
    return a[cols].reset_index(drop=True).equals(b[cols].reset_index(drop=True))


def capture_constituents(log=print) -> int:
    """Store a snapshot of every tracked index whose membership changed. Returns failures."""
    today = date.today().isoformat()
    failed = 0
    for index in INDEX_FILES:
        try:
            df = fetch_list(index)
        except Exception as exc:
            failed += 1
            log(f"constituents {index}: FAILED {type(exc).__name__}: {str(exc)[:140]}")
            continue
        key = store_key(index)
        prev = latest_snapshot(key)
        if prev is not None and _same(df, read_raw(key, prev)):
            log(f"constituents {index}: unchanged since {prev}")
            continue
        df["source"] = "live"
        write_raw(key, df, today)
        log(f"constituents {index}: NEW SNAPSHOT {today} "
            f"({'first capture' if prev is None else 'membership changed vs ' + prev})")
    return failed


# ------------------------------------------------------------- Wayback

CDX = "https://web.archive.org/cdx/search/cdx"
WAYBACK_RAW = "https://web.archive.org/web/{ts}id_/{original}"


def _get_polite(url: str, tries: int = 3) -> requests.Response:
    """GET that waits out the Archive's 429/503 instead of failing on them."""
    for attempt in range(tries):
        r = requests.get(url, headers=UA, timeout=90)
        if r.status_code in (429, 503):
            _time.sleep(60 * (attempt + 1))
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()
    return r


def _wayback_versions(index: str) -> list[tuple[str, str]]:
    """(timestamp, original url) for each distinct archived version of an index's list,
    across both hosts, oldest first."""
    name = INDEX_FILES[index][0]
    found: dict[str, str] = {}
    for host in ("niftyindices.com/IndexConstituent/", "nsearchives.nseindia.com/content/indices/"):
        for attempt in range(3):
            r = requests.get(CDX, headers=UA, timeout=90, params={
                "url": host + name, "output": "json", "fl": "timestamp,original,digest",
                "collapse": "digest", "filter": "statuscode:200"})
            if r.status_code == 200:
                for ts, original, _ in (r.json()[1:] or []):
                    found[ts] = original
                break
            _time.sleep(15 * (attempt + 1))
    return sorted(found.items())


def backfill_wayback(pause: float = 8.0, log=print) -> int:
    """Store the Internet Archive's dated copies as snapshots. Returns failures."""
    failed = streak = 0
    for index in INDEX_FILES:
        key = store_key(index)
        try:
            versions = _wayback_versions(index)
        except Exception as exc:
            failed += 1
            log(f"wayback {index}: FAILED listing — {type(exc).__name__}: {str(exc)[:100]}")
            continue
        kept = 0
        for ts, original in versions:
            day = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
            if raw_path(key, day).exists():
                continue
            try:
                r = _get_polite(WAYBACK_RAW.format(ts=ts, original=original))
                df = parse_list(r.text, index)
                streak = 0
            except ValueError as exc:  # an archived page that isn't a valid list — skip it
                log(f"wayback {index} {day}: skipped — {str(exc)[:90]}")
                _time.sleep(pause)
                continue
            except Exception as exc:
                failed += 1
                streak += 1
                log(f"wayback {index} {day}: FAILED {type(exc).__name__}: {str(exc)[:100]}")
                if streak >= MAX_STREAK:
                    log("wayback: too many consecutive failures — stopping; rerun later")
                    return failed
                _time.sleep(pause)
                continue
            prev = [d for d in sorted(p.stem for p in (RAW / key).glob("*.parquet")) if d < day]
            if prev and _same(df, read_raw(key, prev[-1])):
                _time.sleep(pause)
                continue  # identical to the previous snapshot — not a change
            df["source"] = "wayback"
            write_raw(key, df, day)
            kept += 1
            _time.sleep(pause)
        log(f"wayback {index}: {len(versions)} archived versions, {kept} new snapshots")
    return failed


# -------------------------------------------------------------- lookup

def members_at(index: str, as_of: str | pd.Timestamp) -> tuple[pd.DataFrame, str]:
    """Membership from the latest snapshot on or before as_of, plus that snapshot's date.

    The returned date is part of the answer: as_of far past it means the
    membership may be stale. Raises LookupError if nothing is that old."""
    key = store_key(index)
    day = pd.Timestamp(as_of).date().isoformat()
    snaps = sorted(p.stem for p in (RAW / key).glob("*.parquet")) if (RAW / key).exists() else []
    usable = [s for s in snaps if s <= day]
    if not usable:
        raise LookupError(f"{index}: no snapshot on or before {day} (earliest: {snaps[:1]})")
    return read_raw(key, usable[-1]), usable[-1]
