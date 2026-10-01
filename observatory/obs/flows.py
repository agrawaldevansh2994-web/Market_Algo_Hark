"""Institutional flows — NSE provisional (captured nightly) and NSDL (history).

  NSE provisional  FII/FPI and DII buy/sell/net for trade date T, published the
                   evening of T. The endpoint serves only the latest day, so a
                   night without a capture loses that day's DII figure for good
                   (FII can be recovered from NSDL, below).
  NSDL             FPI flows confirmed by custodians — investments daily since
                   the 1990s, derivatives since 2003. Per NSDL's own footnote a
                   reporting date covers trades "on and up to the previous
                   trading day", so rows stay on their reporting date and are
                   never silently shifted (research/02 §4.8).

Flows are levels in INR crore and often negative, so they never go through
log_returns. Storage is one file per month (store.write_partition): closed
months are immutable and a nightly run only rewrites the current month.
Raw NSDL partitions keep every dated row as received, subtotals included;
subtotals are dropped only when the panel is built.
"""

from __future__ import annotations

import re
import time as _time
from datetime import date
from io import StringIO

import pandas as pd
import requests

from .store import read_partition, read_partitions, write_partition

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

NSE_KEY = "nse_fiidii"
INVEST_KEY = "nsdl_fpi_invest"
DERIV_KEY = "nsdl_fpi_deriv"
SUBTOTAL_ROUTES = {"Sub-total", "Total"}


# ------------------------------------------------------------------- NSE

NSE_HOME = "https://www.nseindia.com/"
NSE_FIIDII = "https://www.nseindia.com/api/fiidiiTradeReact"


def nse_session() -> requests.Session:
    """NSE rejects API calls without the cookies its homepage sets."""
    s = requests.Session()
    s.headers.update({**UA, "Accept": "application/json, text/plain, */*"})
    s.get(NSE_HOME, timeout=30).raise_for_status()
    return s


def _fiidii_row(rows: list[tuple[str, str, float, float, float]], source: str) -> pd.DataFrame:
    """rows: (category, date string, buy, sell, net) → one wide row for the trade date."""
    dates = {d for _, d, *_ in rows}
    if len(dates) != 1:
        raise ValueError(f"{source}: expected one trade date, got {sorted(dates)}")
    out: dict[str, float] = {}
    for cat, _, buy, sell, net in rows:
        c = cat.strip().upper()
        tag = "fii" if c.startswith("FII") else "dii" if c.startswith("DII") else None
        if tag is None:
            raise ValueError(f"{source}: unknown category {cat!r}")
        out |= {f"{tag}_buy": buy, f"{tag}_sell": sell, f"{tag}_net": net}
    if len(out) != 6:
        raise ValueError(f"{source}: expected FII and DII rows, got {sorted(out)}")

    idx = pd.DatetimeIndex([pd.to_datetime(dates.pop(), format="%d-%b-%Y")], name="date")
    df = pd.DataFrame([out], index=idx)
    df["source"] = source
    df["captured_at"] = pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None)
    return df


def fetch_nse_fiidii(session: requests.Session | None = None) -> pd.DataFrame:
    """The latest published trade date: one row of FII and DII buy/sell/net."""
    s = session or nse_session()
    r = s.get(NSE_FIIDII, timeout=30,
              headers={"Referer": "https://www.nseindia.com/reports/fii-dii"})
    r.raise_for_status()
    return _fiidii_row([(x["category"], x["date"], float(x["buyValue"]),
                         float(x["sellValue"]), float(x["netValue"])) for x in r.json()], "nse")


MSEI_FIIDII = "https://www.msei.in/downloads/equity-reports/fii-dii-activities"


def fetch_msei_fiidii() -> pd.DataFrame:
    """Fallback: MSEI republishes the same combined NSE+BSE+MSEI figures on an
    unrelated host. Its components are not always consistent — on 2026-09-25
    its FII sell value disagreed with its own net — so checks.py validates
    buy − sell = net on every stored row."""
    r = requests.get(MSEI_FIIDII, headers=UA, timeout=40)
    r.raise_for_status()
    def num(v) -> float:
        return float(str(v).replace(",", "").strip())

    rows = []
    for t in pd.read_html(StringIO(r.text)):
        t.columns = [" ".join(str(c).split()) for c in t.columns]  # MSEI uses \xa0
        if {"Category", "Date", "Buy Value", "Sell Value", "Net Value"} <= set(t.columns):
            x = t.iloc[0]
            rows.append((str(x["Category"]), str(x["Date"]).strip(), num(x["Buy Value"]),
                         num(x["Sell Value"]), num(x["Net Value"])))
    return _fiidii_row(rows, "msei")


def capture_fiidii() -> str:
    """Append the latest trade date to its month file — NSE first, MSEI if NSE
    refuses. The first capture of a date wins."""
    try:
        df = fetch_nse_fiidii()
    except Exception as nse_exc:
        try:
            df = fetch_msei_fiidii()
        except Exception as msei_exc:
            raise RuntimeError(f"NSE: {nse_exc!r}; MSEI: {msei_exc!r}") from msei_exc
    day, source = df.index[0], df["source"].iloc[0]
    part = f"{day:%Y-%m}"
    existing = read_partition(NSE_KEY, part)
    if existing is not None and day in existing.index:
        return f"FII/DII {day.date()}: already captured"
    merged = df if existing is None else pd.concat([existing, df]).sort_index()
    write_partition(NSE_KEY, part, merged)
    return f"FII/DII {day.date()}: captured from {source}"


# ------------------------------------------------------------------ NSDL

NSDL_ARCHIVE = "https://www.fpi.nsdl.co.in/web/Reports/Archive.aspx"
NSDL_START = "1999-01"
MAX_STREAK = 5  # consecutive failures before a backfill stops hammering a refusing source


class NoDataYet(ValueError):
    """NSDL answered, but with no investments table for the requested month."""


def _hidden(html: str, name: str) -> str:
    m = re.search(rf'name="{name}"[^>]*value="([^"]*)"', html)
    return m.group(1) if m else ""


def _num(s: pd.Series) -> pd.Series:
    """NSDL writes negatives as '(123.45)' and rates as 'Rs.46.2300'."""
    t = s.astype(str).str.replace(",", "").str.replace("Rs.", "").str.strip()
    neg = t.str.startswith("(") & t.str.endswith(")")
    v = pd.to_numeric(t.str.strip("()"), errors="coerce")
    return v.where(~neg, -v)


def _col(t: pd.DataFrame, prefix: str) -> str:
    for c in t.columns:
        if str(c).startswith(prefix):
            return c
    raise ValueError(f"NSDL layout changed: no column starting {prefix!r} in {list(t.columns)}")


def _flat(c) -> str:
    return " | ".join(str(x) for x in c) if isinstance(c, tuple) else str(c)


def _parse_investments(t: pd.DataFrame) -> pd.DataFrame:
    t = t.copy()
    t.columns = [c[-1] if isinstance(c, tuple) else c for c in t.columns]
    day = pd.to_datetime(t[_col(t, "Reporting Date")], format="%d-%b-%Y", errors="coerce")
    t, day = t[day.notna()], day[day.notna()]  # undated rows are monthly/yearly totals

    route = (t["Investment Route"].astype(str).str.strip()
             if "Investment Route" in t.columns else "All")
    out = pd.DataFrame({
        "asset": t[_col(t, "Debt/Equity")].astype(str).str.strip(),
        "route": route,
        "gross_buy": _num(t[_col(t, "Gross Purchases")]),
        "gross_sell": _num(t[_col(t, "Gross Sales")]),
        "net": _num(t[_col(t, "Net Investment (Rs")]),
        "net_usd_mn": _num(t[_col(t, "Net Investment US")]),
        "usdinr_ref": _num(t[_col(t, "Conversion")]),
    })
    out.index = pd.DatetimeIndex(day, name="date")
    return out


DERIV_COLS = ["product", "buy_contracts", "buy_cr", "sell_contracts", "sell_cr",
              "oi_contracts", "oi_cr"]


def _parse_derivatives(t: pd.DataFrame) -> pd.DataFrame:
    heads = [_flat(c) for c in t.columns]
    expected = ["Reporting Date", "Derivative Products", "Buy", "Buy", "Sell", "Sell",
                "Open Interest", "Open Interest"]
    if len(heads) != 8 or any(e not in h for e, h in zip(expected, heads)):
        raise ValueError(f"NSDL derivatives layout changed: {heads}")

    day = pd.to_datetime(t.iloc[:, 0], format="%d-%b-%Y", errors="coerce")
    t, day = t[day.notna()], day[day.notna()]
    out = pd.DataFrame({"product": t.iloc[:, 1].astype(str).str.strip().str.title()})
    for i, name in enumerate(DERIV_COLS[1:], start=2):
        out[name] = _num(t.iloc[:, i])
    out.index = pd.DatetimeIndex(day, name="date")
    return out


def fetch_nsdl_month(as_of: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Every reporting date in as_of's month, up to as_of: (investments, derivatives)."""
    s = requests.Session()
    page = s.get(NSDL_ARCHIVE, headers=UA, timeout=60).text
    stamp = f"{as_of:%d-%b-%Y}"
    form = {
        "__EVENTTARGET": "btnSubmit1", "__EVENTARGUMENT": "",
        "__VIEWSTATE": _hidden(page, "__VIEWSTATE"),
        "__VIEWSTATEGENERATOR": _hidden(page, "__VIEWSTATEGENERATOR"),
        "__EVENTVALIDATION": _hidden(page, "__EVENTVALIDATION"),
        "hdnDate": stamp, "txtDate": stamp, "hdnFlag": "", "HdnValexceldata": "",
    }
    r = s.post(NSDL_ARCHIVE, data=form, headers={**UA, "Referer": NSDL_ARCHIVE}, timeout=90)
    r.raise_for_status()

    invest = deriv = None
    for t in pd.read_html(StringIO(r.text)):
        heads = " ".join(_flat(c) for c in t.columns)
        if "Derivative Products" in heads:
            deriv = _parse_derivatives(t)
        elif "Debt/Equity" in heads:
            invest = _parse_investments(t)

    if invest is None:
        raise NoDataYet(f"NSDL returned no investments table for {stamp}")
    if deriv is None:  # no derivatives table before 2003
        deriv = pd.DataFrame(columns=DERIV_COLS, index=pd.DatetimeIndex([], name="date"))

    month = pd.Period(as_of, "M")
    for name, df in (("investments", invest), ("derivatives", deriv)):
        stray = df.index[df.index.to_period("M") != month]
        if len(stray):
            raise ValueError(f"NSDL {name} for {stamp} contains other months: {stray[:3].tolist()}")
    return invest, deriv


def update_nsdl(start: str = NSDL_START, pause: float = 1.5, log=print) -> int:
    """Fill NSDL month files; returns the number of months that failed.

    Stored closed months are skipped; the current and previous months are
    always refetched, since both can still gain rows."""
    today = date.today()
    last = pd.Period(today, "M")
    failed = streak = 0
    for p in pd.period_range(pd.Period(start, "M"), last, freq="M"):
        part = str(p)
        if p < last - 1 and read_partition(INVEST_KEY, part) is not None:
            continue
        try:
            invest, deriv = fetch_nsdl_month(min(p.end_time.date(), today))
            streak = 0
        except NoDataYet as exc:
            # The current month legitimately has no rows until NSDL's first report.
            if p < last:
                failed += 1
                log(f"NSDL {part}: FAILED {exc}")
            else:
                log(f"NSDL {part}: nothing published yet")
            _time.sleep(pause)
            continue
        except Exception as exc:
            failed += 1
            streak += 1
            log(f"NSDL {part}: FAILED {type(exc).__name__}: {exc}")
            if streak >= MAX_STREAK:
                log(f"NSDL: {streak} consecutive failures — source is refusing us, stopping. "
                    "Rerun later; stored months are kept and skipped.")
                return failed
            _time.sleep(pause)
            continue
        if invest.empty:
            log(f"NSDL {part}: no rows")
        else:
            write_partition(INVEST_KEY, part, invest)
            if not deriv.empty:
                write_partition(DERIV_KEY, part, deriv)
            log(f"NSDL {part}: {invest.index.nunique()} days")
        _time.sleep(pause)
    return failed


def lost_capture_days(captured: pd.DatetimeIndex, trading_days: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """Trading days between the first and last capture that have no capture.

    The NSE/MSEI endpoint is latest-day-only, so each of these is permanent."""
    if len(captured) == 0:
        return []
    have = set(pd.DatetimeIndex(captured).normalize())
    window = pd.DatetimeIndex(trading_days).sort_values()
    window = window[(window >= min(have)) & (window <= max(have))]
    return [d for d in window if d not in have]


# ----------------------------------------------------------------- panel

def flows_panel() -> pd.DataFrame:
    """Daily flows in INR crore, one column per registry key.

    Each column keeps its source's date convention: NSE columns are on trade
    date, NSDL columns on reporting date (roughly T+1). Do not compare them on
    the same row without accounting for that.
    """
    cols: dict[str, pd.Series] = {}

    try:
        nse = read_partitions(NSE_KEY)
        cols["fii_net_cash"] = nse["fii_net"]
        cols["dii_net_cash"] = nse["dii_net"]
    except FileNotFoundError:
        pass

    try:
        inv = read_partitions(INVEST_KEY)
    except FileNotFoundError:
        inv = None
    if inv is not None:
        eq = inv[(inv["asset"] == "Equity") & ~inv["route"].isin(SUBTOTAL_ROUTES)]
        cols["fpi_equity_nsdl"] = eq.groupby(level=0)["net"].sum()
        exch = eq[eq["route"] == "Stock Exchange"]
        if not exch.empty:
            cols["fpi_equity_exch_nsdl"] = exch.groupby(level=0)["net"].sum()

    if not cols:
        raise FileNotFoundError("no flow data stored — run capture.py or backfill first")
    panel = pd.DataFrame(cols).sort_index()
    panel.index.name = "date"
    return panel
