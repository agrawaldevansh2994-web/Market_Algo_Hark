"""Step 5b — where does the replica's pre-2018 gap come from?

Each experiment changes ONE approximation and re-measures the gap to the
published TRI by era. Writes reports/mom30/decomposition.csv and
reports/mom30/held_jumps.csv. Run after build_momentum.py (~10 min).

Important framing: the index launched 2020-08-25. Everything earlier in the
TRI is NSE's own back-calculation, with point-in-time Nifty 200 lists and
free-float mcaps we cannot see. A gap there can come from our proxies or from
choices in that back-calculation; this script measures the first kind only.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

import build_momentum as bm
from obs import momentum as M

ERAS = [("2005-07-01", "2012-12-31"), ("2013-01-01", "2017-12-31"), ("2018-01-01", None), (bm.LIVE_FROM, None)]


def era_rows(name: str, rep: pd.Series, bench: pd.Series, note: str) -> list[dict]:
    out = []
    for a, b in ERAS:
        s = M.tracking_stats(rep.loc[a:b], bench.loc[a:b])
        label = "live (since launch)" if a == bm.LIVE_FROM else f"{a[:4]}–{(b or str(rep.index[-1].year))[:4]}"
        out.append({"experiment": name, "era": label, "replica_cagr": s["cagr_rep"], "index_cagr": s["cagr_bench"],
                    "gap_pa": s["gap_pa"], "tracking_error": s["tracking_error"], "corr": s["corr"], "note": note})
    return out


def holdings(tr: pd.DataFrame, weights: dict) -> pd.DataFrame:
    """Start-of-day weights of the drifting portfolio."""
    dates, parts = sorted(weights), []
    for i, d in enumerate(dates):
        end = dates[i + 1] if i + 1 < len(dates) else tr.index[-1]
        seg = tr.loc[(tr.index > d) & (tr.index <= end), weights[d].index].fillna(0.0)
        if seg.empty:
            continue
        g = (1 + seg).cumprod().mul(weights[d], axis=1)
        start = pd.concat([weights[d].to_frame().T.set_index(pd.Index([d])), g.iloc[:-1]])
        start.index = g.index
        parts.append(start.div(start.sum(axis=1), axis=0))
    return pd.concat(parts).fillna(0.0)


def main() -> int:
    if "--ctx" in sys.argv:            # a pickled prepare() result, to skip the ~7-min panel build
        import pickle
        ctx = pickle.load(open(sys.argv[sys.argv.index("--ctx") + 1], "rb"))
    else:
        ctx = bm.prepare(write_audit=False)
    tr, dates = ctx["tr"], ctx["dates"]
    tri = pd.read_csv(bm.REF / "nifty200mom30_tri.csv", parse_dates=["date"]).set_index("date")["tri"].pct_change()
    n200 = pd.read_csv(bm.REF / "nifty200_tri.csv", parse_dates=["date"]).set_index("date")["tri"].pct_change()
    uni, size, mcap_at = bm.mcap_rules(ctx)
    rows = []

    _, w_turn, w_turn_ew = bm.run_reviews(ctx)
    rows += era_rows("A/B. turnover universe + turnover weights (first pass)", M.drifting_portfolio(tr, w_turn), tri,
                     "top 200 by 6-month turnover; weight = turnover × score")
    rows += era_rows("B. turnover universe, equal weight", M.drifting_portfolio(tr, w_turn_ew), tri, "")
    sel, w_mc, w_mc_ew = bm.run_reviews(ctx, universe=uni, size=size)
    rows += era_rows("A/B. estimated-mcap universe + mcap weights (new default)", M.drifting_portfolio(tr, w_mc), tri,
                     "mcap ≈ adjusted price × today's shares; turnover-imputed for delisted names")
    rows += era_rows("B. estimated-mcap universe, equal weight", M.drifting_portfolio(tr, w_mc_ew), tri, "")

    # C. timing: shift every effective date
    for k in (-10, -5, 5):
        w2 = {dates[dates.get_loc(d) + k]: v for d, v in w_mc.items() if 0 <= dates.get_loc(d) + k < len(dates)}
        rows += era_rows(f"C. effective date {k:+d} sessions", M.drifting_portfolio(tr, w2), tri, "")

    # F&O filter off (methodology had it at launch; checks whether the back-calc might not)
    c2 = dict(ctx)
    c2["fo"] = {d: set(ctx["adj"].columns) for d in ctx["fo"]}
    _, w_nofo, _ = bm.run_reviews(c2, universe=uni, size=size)
    rows += era_rows("F&O eligibility filter switched off", M.drifting_portfolio(tr, w_nofo), tri, "")

    # Universe-only check: do the proxy-200 portfolios track the Nifty 200 TRI itself?
    for name, fn in (("turnover", None), ("estimated mcap", "mc")):
        w = {}
        for r in ctx["sched"].itertuples(index=False):
            if fn:
                mc = mcap_at(r.cutoff)[0].nlargest(bm.PROXY_N)
            else:
                a6 = ctx["adv6"].loc[r.cutoff, ctx["cand"]].dropna()
                mc = a6[ctx["last_seen"][a6.index] >= r.cutoff - pd.Timedelta(days=10)].nlargest(bm.PROXY_N)
            w[r.effective] = mc / mc.sum()
        rows += era_rows(f"Universe only: {name} top 200, size-weighted, vs NIFTY 200 TRI",
                         M.drifting_portfolio(tr, w), n200, "benchmark here is the Nifty 200 TRI")

    out = pd.DataFrame(rows)
    out.to_csv(bm.OUT / "decomposition.csv", index=False, float_format="%.4f")

    # D. data: every held day with a move beyond ±20%, its weight and contribution
    H = holdings(tr, w_mc)
    adj, div, close = ctx["adj"], ctx["div"], ctx["close"]
    raw = ((adj + div) / adj.ffill().shift(1) - 1).where(close.notna()).reindex(index=H.index, columns=H.columns)
    big = ((raw.abs() > 0.2) & (H > 0)).stack()
    big = big[big]
    aud = ctx["aud"]
    unx = set(zip(aud.loc[aud["status"] == "unexplained", "cid"], aud.loc[aud["status"] == "unexplained", "ex_date"]))
    jumps = pd.DataFrame([{"date": d.date(), "symbol": c, "raw_move": raw.at[d, c], "weight": H.at[d, c],
                           "contribution": H.at[d, c] * tr.at[d, c], "clipped": abs(raw.at[d, c]) > 0.6,
                           "unexplained_gap": (c, d) in unx} for d, c in big.index])
    jumps.to_csv(bm.OUT / "held_jumps.csv", index=False, float_format="%.4f")
    dy = (H * (div / adj.ffill().shift(1)).reindex(index=H.index, columns=H.columns).fillna(0)).sum(axis=1)
    dy.groupby(dy.index.year).sum().rename("dividend_yield_captured").to_csv(bm.OUT / "dividends_by_year.csv",
                                                                             float_format="%.4f")
    print(out.assign(gap=lambda x: (x.gap_pa * 100).round(1))[["experiment", "era", "gap"]].to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
