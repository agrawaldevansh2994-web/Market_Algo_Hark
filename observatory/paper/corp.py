"""Corporate actions for the paper book: cash dividends, splits, bonuses. PAPER ONLY.

Source: NSE's official MCP server (get_corporate_actions; streamable HTTP, no key).
Purposes are parsed with obs.corpactions.parse_subject, the same parser the
backtest uses. Fetched rows are cached in paper/state/corp_actions.csv so marks
are reproducible offline. If the server is down the run logs it and carries on;
the next successful fetch re-asks the whole window, and actions not yet in the
ledger are applied late (run_paper restates the marks they touch).

Dividends are GROSS, pre-TDS, accrued on the ex-date (cash is paid weeks later
in reality). Splits/bonuses/consolidations scale whole shares; a fractional
entitlement is paid as cash at the ex-date close (an estimate of NSE's
sale-of-fractions payout). Rights and schemes are logged, not applied.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import pandas as pd
import requests

from obs.corpactions import parse_subject

MCP_URL = "https://mcp.nseindia.in/bhavcopy/cm/mcp"
PRICE_KINDS = ("split", "bonus", "consolidation")
COLS = ["symbol", "ex_date", "kind", "value", "purpose"]


def parse(purpose: str, action_type: str = "", adj: float | None = None) -> list[tuple[str, float]]:
    """NSE purpose text → [(kind, value)]: dividend = Rs per share (summed when a
    row carries several), split/bonus/consolidation = price factor (shares × 1/factor).
    Falls back to the feed's adjustmentFactor for a SPLIT/BONUS the text parser misses."""
    got = parse_subject(purpose)
    div = sum(v for k, v in got if k == "dividend")
    out = [(k, v) for k, v in got if k in PRICE_KINDS]
    if not out and action_type.upper() in ("SPLIT", "BONUS") and adj and 0 < adj != 1:
        out = [(action_type.lower(), float(adj))]
    if div > 0:
        out.append(("dividend", div))
    out += [(k, float("nan")) for k, _ in got if k in ("rights", "scheme")]
    return out


class _Mcp:
    def __init__(self, url: str = MCP_URL):
        self.url, self.i = url, 0
        self.s = requests.Session()
        self.s.headers.update({"Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
        r = self._post("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                      "clientInfo": {"name": "market-algo-paper", "version": "1"}})
        r.raise_for_status()
        self.s.headers["Mcp-Session-Id"] = r.headers.get("Mcp-Session-Id", "")
        self.s.post(url, json={"jsonrpc": "2.0", "method": "notifications/initialized"}, timeout=30)

    def _post(self, method, params):
        self.i += 1
        return self.s.post(self.url, json={"jsonrpc": "2.0", "id": self.i, "method": method, "params": params},
                           timeout=60)

    def actions(self, symbol: str, frm: str, to: str) -> list[dict]:
        t = self._post("tools/call", {"name": "get_corporate_actions",
                                      "arguments": {"symbol": symbol, "fromDate": frm, "toDate": to}}).text
        if "data:" in t[:30]:
            t = [x[5:] for x in t.splitlines() if x.startswith("data:")][-1]
        res = json.loads(t).get("result")
        if not res or res.get("isError"):
            raise RuntimeError(f"{symbol}: tool call failed")
        body = json.loads(res["content"][0]["text"])
        if body.get("error"):
            raise RuntimeError(f"{symbol}: {body['error']}")
        return body.get("actions", [])


def fetch(symbols, frm: str, to: str, client=None, tries: int = 5, log=print) -> tuple[pd.DataFrame, list]:
    """Rows for every symbol the feed answered, plus the list it did not. Never raises."""
    rows, failed = [], []
    try:
        c = client or _Mcp()
    except Exception as e:  # unreachable: keep the cache, retry next run
        log(f"corporate actions: NSE MCP unreachable ({type(e).__name__}); using cache only")
        return pd.DataFrame(columns=COLS), list(symbols)
    for sym in symbols:
        for _ in range(tries):  # the server throws intermittent 500s
            try:
                acts = c.actions(sym, frm, to)
                break
            except Exception:
                acts = None
                time.sleep(1 if client is None else 0)
        if acts is None:
            failed.append(sym)
            continue
        for a in acts:
            for k, v in parse(a.get("purpose", ""), a.get("actionType", ""), a.get("adjustmentFactor")):
                rows.append(dict(symbol=sym, ex_date=a["exDate"], kind=k, value=v,
                                 purpose=" ".join(str(a.get("purpose", "")).split())))
    if failed:
        log(f"corporate actions: no answer for {len(failed)} symbol(s): {';'.join(failed)} (retry next run)")
    return pd.DataFrame(rows, columns=COLS), failed


def refresh(cache: Path, symbols, frm: str, to: str, **kw) -> pd.DataFrame:
    """Merge a fresh fetch into the cache file. Answered symbols replace their rows in the window."""
    old = pd.read_csv(cache, dtype={"ex_date": str}) if cache.exists() else pd.DataFrame(columns=COLS)
    new, failed = fetch(symbols, frm, to, **kw)
    ok = set(symbols) - set(failed)
    keep = old[~(old["symbol"].isin(ok) & old["ex_date"].between(frm, to))]
    out = pd.concat([keep, new]).drop_duplicates(["symbol", "ex_date", "kind"]).sort_values(["ex_date", "symbol"])
    out.to_csv(cache, index=False)
    return out


def held_on(ledger: pd.DataFrame, symbol: str, ex_date: str) -> int:
    """Shares held at the ex-date open: every ledger row dated before it."""
    sgn = ledger["side"].map({"BUY": 1, "SELL": -1, "SPLIT": 1, "BONUS": 1, "CONSOLIDATION": 1}).fillna(0)
    m = (ledger["symbol"] == symbol) & (ledger["date"].astype(str) < ex_date)
    return int(round((ledger.loc[m, "qty"] * sgn[m]).sum()))


def pending(actions: pd.DataFrame, ledger: pd.DataFrame, upto: str) -> pd.DataFrame:
    """Actions with ex-date ≤ upto not yet in the ledger, oldest first (apply() skips names not held)."""
    done = set(zip(ledger["date"].astype(str), ledger["symbol"], ledger["side"]))
    a = actions[(actions["ex_date"].astype(str) <= upto) & actions["kind"].isin(("dividend",) + PRICE_KINDS)]
    a = a.loc[[(str(d), s, k.upper()) not in done for d, s, k in zip(a["ex_date"], a["symbol"], a["kind"])]]
    return a.sort_values(["ex_date", "symbol"])


def apply(row, ledger: pd.DataFrame, close: float | None = None) -> tuple[list, int, float]:
    """One action → (ledger rows, share delta, cash delta). `close` = ex-date close, used only
    for a fractional entitlement. Ledger: DIVIDEND qty=shares held, price=Rs/share gross;
    SPLIT/BONUS qty=shares added, price=price factor."""
    d, s, k, v = str(row.ex_date), row.symbol, row.kind, float(row.value)
    q = held_on(ledger, s, d)
    if q <= 0:
        return [], 0, 0.0
    if k == "dividend":
        return [(d, s, "DIVIDEND", q, v, 0.0)], 0, round(q * v, 2)
    new = q / v
    whole = math.floor(new + 1e-9)
    cash = round((new - whole) * close, 2) if close and new - whole > 1e-9 else 0.0
    return [(d, s, k.upper(), whole - q, v, 0.0)], whole - q, cash
