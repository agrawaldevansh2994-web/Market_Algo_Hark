"""Daily paper mark-to-market for the Momentum 30 replica.   Run from observatory/:  python -m paper.run_paper

PAPER ONLY. State lives in paper/state/ (ledger.csv, positions.csv, daily.csv).
Prices: NSE CM bhavcopy (EQ close). Benchmark: Nifty200 Momentum 30 TOTAL RETURN index
(index_tri, official niftyindices.com series via obs/tri.py, which also keeps data/reference/
*_tri.csv current); the PRICE index from NSE ind_close_all is kept alongside as index_price.
A day whose TRI is not out yet stays blank and is filled on a later run.
Corporate actions (paper/corp.py, NSE MCP feed, cached in corp_actions.csv): cash dividends
are credited GROSS, pre-TDS, on the ex-date; splits/bonuses scale share counts so NAV stays
continuous on unadjusted prices. An action learned late is applied late and the marks since
its ex-date are restated. Rights and demergers are not adjusted.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import requests

from obs.bhavcopy import fetch_day
from obs import tri as T
from paper import corp as CP

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


def attach_tri(daily: pd.DataFrame, tri: pd.Series) -> pd.DataFrame:
    """(Re)map index_tri on every row from the reference series, so late-published days fill in."""
    d = daily.copy()
    d["index_tri"] = pd.to_datetime(d["date"]).map(tri).astype(float)
    return d


def main(upto: dt.date | None = None, fetch_ca: bool = True, fetch_tri: bool = True) -> None:
    pos = pd.read_csv(STATE / "positions.csv")
    daily = pd.read_csv(STATE / "daily.csv", parse_dates=["date"])
    ledger = pd.read_csv(STATE / "ledger.csv", dtype={"date": str})
    cash = float(pos.loc[pos["symbol"] == "CASH", "shares"].iloc[0])
    held = pos[pos["symbol"] != "CASH"].set_index("symbol")["shares"].astype(int).to_dict()
    s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0"
    daily["date"] = daily["date"].dt.date.astype(str)
    last = daily["date"].max()
    d = dt.date.fromisoformat(last) + dt.timedelta(days=1)
    upto = upto or dt.date.today()
    cache = STATE / "corp_actions.csv"
    syms = sorted(ledger.loc[ledger["side"] == "BUY", "symbol"].unique())
    acts = (CP.refresh(cache, syms, ledger["date"].min(), (upto + dt.timedelta(days=90)).isoformat())
            if fetch_ca else pd.read_csv(cache, dtype={"ex_date": str}) if cache.exists()
            else pd.DataFrame(columns=CP.COLS))
    closes: dict = {}

    def close(day: str) -> dict:
        if day not in closes:
            df = fetch_day(dt.date.fromisoformat(day), s)
            closes[day] = eq_close(df) if df is not None else {}
        return closes[day]

    def settle(through: str) -> list:
        nonlocal cash, ledger
        done = []
        for r in CP.pending(acts, ledger, through).itertuples():
            rows, dq, dc = CP.apply(r, ledger, None if r.kind == "dividend" else close(r.ex_date).get(r.symbol))
            if rows:
                ledger = pd.concat([ledger, pd.DataFrame(rows, columns=ledger.columns)], ignore_index=True)
                held[r.symbol] = held.get(r.symbol, 0) + dq; cash += dc
                done.append((r, dq, dc)); print(f"{r.kind} {r.symbol} ex {r.ex_date}: {rows[0][3]} @ {r.value}")
        return done

    for r, dq, dc in settle(last):  # learned late: restate the marks since the ex-date
        m = daily["date"] >= str(r.ex_date)
        daily.loc[m, "nav"] = [round(n + dc + dq * close(x).get(r.symbol, 0.0), 2)
                               for n, x in zip(daily.loc[m, "nav"], daily.loc[m, "date"])]
    rows = []
    while d <= upto:
        df = fetch_day(d, s)
        ix = index_close(d, s) if df is not None else None
        if df is not None and ix is not None:
            px = closes[d.isoformat()] = eq_close(df)
            settle(d.isoformat())
            miss = [k for k in held if k not in px]
            nav = cash + sum(q * px.get(k, float("nan")) for k, q in held.items())
            rows.append(dict(date=d.isoformat(), nav=round(nav, 2), index_price=ix,
                             missing=";".join(miss)))
        d += dt.timedelta(days=1)
    out = pd.concat([daily, pd.DataFrame(rows)])
    if fetch_tri:
        T.update_all(upto)
    try:
        out = attach_tri(out, T.read_ref("nifty200mom30_tri"))
    except FileNotFoundError:
        print("TRI reference missing; index_tri left blank")
        out["index_tri"] = out.get("index_tri")
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    out[["date", "nav", "index_price", "index_tri", "missing"]].to_csv(STATE / "daily.csv", index=False)
    ledger.to_csv(STATE / "ledger.csv", index=False)
    pd.DataFrame({"symbol": [*sorted(held), "CASH"],
                  "shares": [float(held[k]) for k in sorted(held)] + [round(cash, 2)]}).to_csv(
        STATE / "positions.csv", index=False)
    soon = acts[(acts["ex_date"].astype(str) > upto.isoformat()) & acts["symbol"].isin(held)]
    for r in soon.itertuples():
        print(f"upcoming: {r.symbol} {r.kind} ex {r.ex_date} ({r.purpose})")
    print(f"added {len(rows)} day(s); last NAV {rows[-1]['nav']:,.0f}" if rows else "nothing new")


if __name__ == "__main__":
    main()
