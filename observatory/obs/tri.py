"""Official Total Return Index (TRI) history from niftyindices.com (NSE Indices Ltd).

The site's own historical-data page POSTs to /BackPage/getTotalReturnIndexString with a
single-quoted JSON string in `cinfo` and returns a JSON list of {Date, TotalReturnsIndex}.
The endpoint is undocumented: it allows at most one year per request, wants a browser
User-Agent, and can change without notice, so every caller treats a failure as "try again
next run" and keeps the reference CSVs it already has.

Reference files (data/reference/<file>.csv, columns date,tri) are append-only text. They are the
answer key for the Momentum 30 replication and the paper book's benchmark.
"""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

import pandas as pd
import requests

URL = "https://www.niftyindices.com/BackPage/getTotalReturnIndexString"
PAGE = "https://www.niftyindices.com/reports/historical-data"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
REF = Path(__file__).resolve().parents[1] / "data" / "reference"

# reference file -> index name as niftyindices.com spells it
INDICES = {"nifty200mom30_tri": "NIFTY200 MOMENTUM 30",
           "nifty200_tri": "NIFTY 200"}


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Referer": PAGE, "Origin": "https://www.niftyindices.com",
                      "Content-Type": "application/json; charset=UTF-8"})
    return s


def parse(payload) -> pd.Series:
    """niftyindices JSON (a list, or {'d': '<json string>'} on older versions) -> date-indexed float Series."""
    if isinstance(payload, dict) and "d" in payload:
        payload = json.loads(payload["d"]) if isinstance(payload["d"], str) else payload["d"]
    if not isinstance(payload, list):
        raise ValueError(f"unexpected TRI payload: {str(payload)[:80]!r}")
    rows = {}
    for r in payload:
        v = str(r.get("TotalReturnsIndex", "")).replace(",", "").strip()
        if not v or v == "-":
            continue
        rows[pd.Timestamp(dt.datetime.strptime(r["Date"].strip(), "%d %b %Y"))] = float(v)
    return pd.Series(rows, name="tri", dtype=float).sort_index()


def fetch(index: str, start: dt.date, end: dt.date, s: requests.Session | None = None,
          tries: int = 3) -> pd.Series:
    """Daily TRI for `index` between start and end (inclusive), in <=1-year requests."""
    s = s or session()
    parts, a = [], start
    while a <= end:
        b = min(end, a + dt.timedelta(days=364))
        cinfo = (f"{{'name':'{index}','startDate':'{a:%d-%b-%Y}','endDate':'{b:%d-%b-%Y}',"
                 f"'indexName':'{index}'}}")
        for k in range(tries):
            try:
                r = s.post(URL, data=json.dumps({"cinfo": cinfo}), timeout=30)
                r.raise_for_status()
                parts.append(parse(r.json()))
                break
            except (requests.RequestException, ValueError):
                if k == tries - 1:
                    raise
                time.sleep(2 * (k + 1))
        a = b + dt.timedelta(days=1)
    out = pd.concat(parts) if parts else pd.Series(dtype=float, name="tri")
    return out[~out.index.duplicated(keep="last")].sort_index()


def read_ref(name: str, ref: Path = REF) -> pd.Series:
    return pd.read_csv(ref / f"{name}.csv", parse_dates=["date"]).set_index("date")["tri"]


def update_ref(name: str, today: dt.date | None = None, ref: Path = REF, s=None, fetcher=fetch,
               tol: float = 0.01) -> int:
    """Append TRI rows newer than the file's last date. Checks the overlap day first, so a changed
    series (different index, or a revised base) raises instead of being spliced on silently."""
    today = today or dt.date.today()
    cur = read_ref(name, ref)
    last = cur.index[-1].date()
    if last >= today:
        return 0
    new = fetcher(INDICES[name], last, today, s)
    if last in {x.date() for x in new.index}:
        if abs(new[pd.Timestamp(last)] - cur.iloc[-1]) > tol:
            raise ValueError(f"{name}: overlap {last} is {new[pd.Timestamp(last)]} vs {cur.iloc[-1]} on file")
    elif len(new):
        raise ValueError(f"{name}: no overlap day {last} in the fetched series, refusing to splice")
    add = new[new.index > pd.Timestamp(last)]
    if len(add):
        out = pd.concat([cur, add]).rename("tri")
        out.index.name = "date"
        out.to_frame().reset_index().assign(date=lambda x: x["date"].dt.strftime("%Y-%m-%d")).to_csv(
            ref / f"{name}.csv", index=False)
    return len(add)


def update_all(today: dt.date | None = None, ref: Path = REF, log=print) -> dict:
    """Best effort: one failed index never stops the other or the caller."""
    s, done = session(), {}
    for name in INDICES:
        try:
            done[name] = update_ref(name, today, ref, s)
            log(f"TRI {name}: +{done[name]} day(s), through {read_ref(name, ref).index[-1]:%Y-%m-%d}")
        except Exception as e:  # noqa: BLE001: the endpoint is undocumented; retry next run
            done[name] = None
            log(f"TRI {name}: fetch failed ({type(e).__name__}: {str(e)[:120]}); keeping the file as is")
    return done
