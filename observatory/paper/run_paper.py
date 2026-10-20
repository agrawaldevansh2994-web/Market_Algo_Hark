"""Daily paper mark-to-market for the Momentum 30 replica.   Run from observatory/:  python -m paper.run_paper

PAPER ONLY. State lives in paper/state/ (ledger.csv, positions.csv, daily.csv).
Prices: NSE CM bhavcopy (EQ close). Benchmark: Nifty200 Momentum 30 PRICE index from
NSE ind_close_all (not TRI, since the daily TRI is not fetchable), labelled as such.
Corporate actions on holdings are not yet adjusted (flagged as a known gap).
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import requests

from obs.bhavcopy import fetch_day

STATE = Path(__file__).parent / "state"
IDX = "Nifty200 Momentum 30"


def index_close(d: dt.date, s: requests.Session) -> float | None:
    r = s.get(f"https://nsearchives.nseindia.com/content/indices/ind_close_all_{d:%d%m%Y}.csv", timeout=30)
    if r.status_code != 200:
        return None
    for line in r.text.splitlines():
        if line.split(",")[0].strip() == IDX:
            return float(line.split(",")[5])
    return None


def eq_close(df: pd.DataFrame) -> dict:
    eq = df[df["series"].astype(str).str.strip() == "EQ"]
    return dict(zip(eq["symbol"].astype(str).str.strip(), eq["close"].astype(float)))


def main(upto: dt.date | None = None) -> None:
    pos = pd.read_csv(STATE / "positions.csv")
    daily = pd.read_csv(STATE / "daily.csv", parse_dates=["date"])
    cash = float(pos.loc[pos["symbol"] == "CASH", "shares"].iloc[0])
    held = pos[pos["symbol"] != "CASH"].set_index("symbol")["shares"].astype(int).to_dict()
    s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0"
    d = daily["date"].max().date() + dt.timedelta(days=1)
    upto = upto or dt.date.today()
    rows = []
    while d <= upto:
        df = fetch_day(d, s)
        ix = index_close(d, s) if df is not None else None
        if df is not None and ix is not None:
            px = eq_close(df)
            miss = [k for k in held if k not in px]
            nav = cash + sum(q * px.get(k, float("nan")) for k, q in held.items())
            rows.append(dict(date=d.isoformat(), nav=round(nav, 2), index_price=ix,
                             missing=";".join(miss)))
        d += dt.timedelta(days=1)
    if rows:
        out = pd.concat([daily.assign(date=daily["date"].dt.date.astype(str)), pd.DataFrame(rows)])
        out.to_csv(STATE / "daily.csv", index=False)
        print(f"added {len(rows)} day(s); last NAV {rows[-1]['nav']:,.0f}")
    else:
        print("nothing new")


if __name__ == "__main__":
    main()
