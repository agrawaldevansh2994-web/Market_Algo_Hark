"""Approximate point-in-time market capitalisation (step-5 gap decomposition).

Free data has no history of shares outstanding. But backward-adjusted prices
already carry every split and bonus, so

    mcap(t) ≈ adj_close(t) × shares_today

is exact for a company whose share count changed only through splits and
bonuses. It is wrong by the amount of later issuance (QIPs, rights, mergers,
ESOPs) or buybacks — usually a modest fraction for large caps, but it can be
2× over two decades. Labelled an ESTIMATE wherever used.

Stocks that no longer trade (delisted, merged) have no current share count on
Yahoo. Their mcap is imputed from turnover: adv6 × the median mcap/adv6 ratio of
stocks with a known count on the same date — the turnover proxy again, for
those names only, and flagged.

shares_today is cached in data/reference/shares_now.csv (cid, shares, asof).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from .store import DATA_ROOT

SHARES = DATA_ROOT / "reference" / "shares_now.csv"


def fetch_shares(cids: list[str], workers: int = 8, log=print) -> pd.DataFrame:
    import yfinance as yf
    have = pd.read_csv(SHARES) if SHARES.exists() else pd.DataFrame(columns=["cid", "shares", "asof"])
    todo = sorted(set(cids) - set(have["cid"]))

    def one(c):
        try:
            v = yf.Ticker(f"{c}.NS").fast_info.get("shares")
        except Exception:
            v = None
        return {"cid": c, "shares": float(v) if v else np.nan, "asof": str(pd.Timestamp.today().date())}

    if todo:
        with ThreadPoolExecutor(workers) as ex:
            rows = list(ex.map(one, todo))
        have = pd.concat([have, pd.DataFrame(rows)], ignore_index=True).sort_values("cid")
        SHARES.parent.mkdir(parents=True, exist_ok=True)
        have.to_csv(SHARES, index=False)
        log(f"shares: asked {len(todo)}, known {int(have['shares'].notna().sum())} of {len(have)}")
    return have


def mcap_estimate(adj_close: pd.Series, adv6: pd.Series, shares: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Cross-section on one date. Returns (mcap estimate, imputed flag)."""
    idx = adj_close.dropna().index.intersection(adv6.dropna().index)
    px, a6 = adj_close[idx], adv6[idx]
    sh = shares.reindex(idx)
    mc = px * sh
    known = mc.notna() & (a6 > 0)
    ratio = (mc[known] / a6[known]).median()
    imputed = ~known
    mc[imputed] = a6[imputed] * ratio
    return mc, imputed
