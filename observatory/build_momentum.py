"""Step 5 — Nifty200 Momentum 30 decomposed replication. Writes reports/mom30/
and reports/corpactions/ (text, committed) for the dashboard.

    python build_bhav.py          # once: NSE bhavcopy store (gitignored)
    python build_momentum.py      # ~2 min; refreshes F&O lists + corporate actions if missing

Every approximation is listed in obs/momentum.py's header (A–E).
"""

from __future__ import annotations

import io
import json
import sys
import time as _time

import numpy as np
import pandas as pd
import requests

from obs import bhavcopy as B
from obs import corpactions as CA
from obs import momentum as M
from obs import size as S
from obs.flows import UA
from obs.store import DATA_ROOT, RAW
from obs.textstore import read_split, write_split

ROOT = DATA_ROOT.parent
OUT = ROOT / "reports" / "mom30"
OUT_CA = ROOT / "reports" / "corpactions"
REF = DATA_ROOT / "reference"
CANDIDATE_TOP = 300      # a stock enters the price panel if ever this liquid at a review
PROXY_N = 200


def log(msg):
    print(msg, flush=True)


# ------------------------------------------------------------------ inputs

def load_panel():
    bh = B.load(columns=["date", "symbol", "series", "close", "prevclose", "turnover"])
    bh["series"] = pd.Categorical(bh["series"], ["EQ", "BE"], ordered=True)
    bh = bh.sort_values(["date", "symbol", "series"]).drop_duplicates(["date", "symbol"])  # EQ wins
    changes = CA.load_symbol_changes()
    bh["cid"] = CA.canonical_symbols(bh, changes).values
    bh = bh.drop_duplicates(["date", "cid"])
    # ETFs and other fund units trade in series EQ too (NIFTYBEES, GOLDBEES …) and
    # top the turnover ranking. Their ISINs start INF; drop every cid that ever had one.
    isin = B.load(columns=["symbol", "isin"]).dropna().drop_duplicates()
    funds = set(isin.loc[isin["isin"].astype(str).str.startswith("INF"), "symbol"])
    funds = to_cid(funds, pd.Timestamp("1990-01-01"), changes) | funds
    bh = bh[~bh["cid"].isin(funds)]
    return bh, changes


def fo_lists(cutoffs: list[pd.Timestamp]) -> dict[pd.Timestamp, set[str]]:
    path = REF / "fo_stocks"
    have = read_split(path, parse_dates=["date"]) if path.exists() else pd.DataFrame(columns=["date", "symbol"])
    done = set(have["date"])
    s = requests.Session()
    s.headers.update(UA)
    new = []
    for d in cutoffs:
        if d in done:
            continue
        syms = B.fo_stocks(d.date(), s)
        if syms is None:
            raise RuntimeError(f"no F&O bhavcopy for trading day {d.date()}")
        new += [{"date": d, "symbol": x} for x in sorted(syms)]
        _time.sleep(0.3)
    if new:
        have = pd.concat([have, pd.DataFrame(new)]).sort_values(["date", "symbol"])
        write_split(have, path, "date")
    return {d: set(g["symbol"]) for d, g in have.groupby("date")}


def to_cid(symbols: set[str], when: pd.Timestamp, changes: pd.DataFrame) -> set[str]:
    out = set()
    for s in symbols:
        for old, new, d in changes[["old", "new", "date"]].itertuples(index=False):
            if s == old and when < d:
                s = new
        out.add(s)
    return out


def actual_list(key: str) -> tuple[set[str], str] | tuple[None, None]:
    folder = RAW / f"constituents_{key}"
    files = sorted(folder.glob("*.parquet"))
    if not files:
        return None, None
    df = pd.read_parquet(files[-1])
    return set(df["symbol"].astype(str).str.strip()), files[-1].stem


# ------------------------------------------------------------------ main

def prepare(write_audit: bool = True) -> dict:
    """Everything up to the reviews: price panel, audit, adjusted prices, total returns."""
    OUT.mkdir(parents=True, exist_ok=True)
    OUT_CA.mkdir(parents=True, exist_ok=True)
    if not (DATA_ROOT / "corpactions" / "nse_actions").exists():
        CA.update_actions(log=log)

    log("loading bhavcopy …")
    bh, changes = load_panel()
    dates = pd.DatetimeIndex(sorted(bh["date"].unique()))
    sched = M.rebalance_schedule(dates)
    log(f"{len(dates):,} trading days {dates[0].date()} → {dates[-1].date()}, {len(sched)} reviews")

    # 6-month average daily turnover at each cutoff (non-trading days count as zero)
    turn = bh.pivot(index="date", columns="cid", values="turnover").astype("float32")
    first_seen = turn.notna().idxmax()
    last_seen = turn.notna()[::-1].idxmax()
    adv6 = turn.fillna(0).rolling(126, min_periods=100).mean()
    cand = set()
    for d in sched["cutoff"]:
        cand |= set(adv6.loc[d].nlargest(CANDIDATE_TOP).index)
    for key in ("nifty200", "nifty200_momentum30"):
        s, _ = actual_list(key)
        cand |= (s or set()) & set(turn.columns)
    cand = sorted(cand)
    log(f"candidate stocks: {len(cand)}")
    sub = bh[bh["cid"].isin(cand)]
    close = sub.pivot(index="date", columns="cid", values="close").reindex(dates)
    prevclose = sub.pivot(index="date", columns="cid", values="prevclose").reindex(dates)
    del bh

    # corporate actions: announced ∩ observed
    acts = CA.load_actions()
    acts["cid"] = [next(iter(to_cid({s}, d, changes))) for s, d in zip(acts["symbol"], acts["ex_date"])]
    aud = CA.audit(close, prevclose, acts)
    ask = sorted(set(aud.loc[aud["status"].str.startswith(("applied", "unexplained")), "cid"]))
    aud = CA.second_source(aud, close, CA.fetch_yf_splits(ask, log=log))
    log("yahoo cross-check: " + json.dumps(aud["yf_check"].value_counts().to_dict()))
    if write_audit:
        aud.to_csv(OUT_CA / "audit.csv", index=False, date_format="%Y-%m-%d", float_format="%.5f")
    log("audit: " + json.dumps(aud["status"].value_counts().to_dict()))
    fac = CA.adjustment_factors(close, aud)
    adj = close * fac

    # daily total return: adjusted price change + dividends on ex-date
    divs = acts[(acts["kind"] == "dividend") & acts["cid"].isin(cand)]
    div = pd.DataFrame(0.0, index=dates, columns=close.columns)
    for cid, ex, amt in divs[["cid", "ex_date", "value"]].itertuples(index=False):
        pos = dates.searchsorted(ex)
        if pos < len(dates):
            div.iat[pos, div.columns.get_loc(cid)] += amt * fac.iat[pos, fac.columns.get_loc(cid)]
    adj_ff = adj.ffill()
    tr = (adj + div) / adj_ff.shift(1) - 1
    tr = tr.where(close.notna())
    # a remaining unexplained gap would wreck returns; cap single-day moves at ±60% and count them
    wild = (tr.abs() > 0.6).sum().sum()
    tr = tr.clip(-0.6, 1.5)

    fo = fo_lists(list(sched["cutoff"]))

    return dict(dates=dates, sched=sched, adv6=adv6, cand=cand, first_seen=first_seen, last_seen=last_seen,
                close=close, adj=adj, fac=fac, div=div, tr=tr, wild=int(wild), fo=fo, changes=changes,
                aud=aud, acts=acts)


def run_reviews(ctx: dict, universe=None, size=None) -> tuple[pd.DataFrame, dict, dict]:
    """Selections and target weights at every review. `universe(r, ctx)` may
    return the candidate list for a review (default: turnover top 200);
    `size(r, ctx, chosen)` the weight-size series (default: 6-month turnover)."""
    sched, adv6, cand, fo, changes = ctx["sched"], ctx["adv6"], ctx["cand"], ctx["fo"], ctx["changes"]
    first_seen, last_seen, adj = ctx["first_seen"], ctx["last_seen"], ctx["adj"]

    # reviews
    sel_rows, w_tilt, w_ew, prev = [], {}, {}, None
    for r in sched.itertuples(index=False):
        a6 = adv6.loc[r.cutoff, cand].dropna()
        traded = last_seen[a6.index] >= r.cutoff - pd.Timedelta(days=10)
        proxy200 = a6[traded].nlargest(PROXY_N)
        members = list(proxy200.index) if universe is None else [c for c in universe(r, ctx) if c in adj.columns]
        fo_c = to_cid(fo.get(r.cutoff, set()), r.cutoff, changes)
        elig = [c for c in members if first_seen.get(c, r.cutoff) <= r.cutoff - pd.Timedelta(days=365)
                and c in fo_c]
        sc = M.momentum_scores(adj, r.cutoff, r.p7, r.p13, elig)
        chosen = M.select(sc, prev)
        prev = chosen
        sz = a6.reindex(chosen).fillna(a6.median()).astype(float) if size is None else size(r, ctx, chosen)
        wt = M.capped_weights(sc.loc[chosen, "score"], sz)
        w_tilt[r.effective] = wt
        w_ew[r.effective] = pd.Series(1 / len(chosen), index=chosen)
        for c in chosen:
            sel_rows.append({"review": r.review, "cutoff": r.cutoff.date(), "effective": r.effective.date(),
                             "symbol": c, "rank": int(sc.loc[c, "rank"]), "score": sc.loc[c, "score"],
                             "ret6": sc.loc[c, "ret6"], "ret12": sc.loc[c, "ret12"], "sigma": sc.loc[c, "sigma"],
                             "weight_tilt": wt[c], "weight_ew": 1 / len(chosen),
                             "n_eligible": len(sc)})

    return pd.DataFrame(sel_rows), w_tilt, w_ew


LIVE_FROM = "2020-08-25"   # index launch; everything earlier is NSE's back-calculation


def mcap_rules(ctx: dict):
    """Universe and weight-size callables for run_reviews using the estimated
    market cap (obs.size): 6-month average adjusted price × today's share count,
    turnover-imputed for stocks that no longer trade."""
    cand, adj, adv6, last_seen = ctx["cand"], ctx["adj"], ctx["adv6"], ctx["last_seen"]
    if "shares" not in ctx:
        ctx["shares"] = S.fetch_shares(cand, log=log).set_index("cid")["shares"]
    avgpx = adj[cand].rolling(126, min_periods=100).mean()
    cache = {}

    def at(d):
        if d not in cache:
            ok = (last_seen[cand] >= d - pd.Timedelta(days=10)).values
            cache[d] = S.mcap_estimate(avgpx.loc[d][ok], adv6.loc[d, cand][ok], ctx["shares"])
        return cache[d]

    def universe(r, _ctx):
        return list(at(r.cutoff)[0].nlargest(PROXY_N).index)

    def size(r, _ctx, chosen):
        mc = at(r.cutoff)[0]
        return mc.reindex(chosen).fillna(mc.median())

    return universe, size, at


def main() -> int:
    ctx = prepare()
    (dates, sched, adv6, cand, first_seen, last_seen, close, adj, fac, div, tr, wild, fo, changes, aud, acts) = (
        ctx[k] for k in ("dates", "sched", "adv6", "cand", "first_seen", "last_seen", "close", "adj", "fac",
                         "div", "tr", "wild", "fo", "changes", "aud", "acts"))
    uni, size, mcap_at = mcap_rules(ctx)
    sel, w_tilt, w_ew = run_reviews(ctx, universe=uni, size=size)
    _, w_turn, _ = run_reviews(ctx)          # the first-pass turnover proxy, kept for comparison

    rep_tilt = M.drifting_portfolio(tr, w_tilt)
    rep_ew = M.drifting_portfolio(tr, w_ew)
    rep_turn = M.drifting_portfolio(tr, w_turn)
    tri = pd.read_csv(REF / "nifty200mom30_tri.csv", parse_dates=["date"]).set_index("date")["tri"]
    n200 = pd.read_csv(REF / "nifty200_tri.csv", parse_dates=["date"]).set_index("date")["tri"]
    bench = tri.pct_change().reindex(rep_tilt.index)
    n200r = n200.pct_change().reindex(rep_tilt.index)
    daily = pd.DataFrame({"replica_tilt": rep_tilt, "replica_ew": rep_ew, "replica_turnover": rep_turn,
                          "nifty200mom30_tri": bench, "nifty200_tri": n200r}).dropna()
    write_split(daily, OUT / "daily_returns", float_format="%.6f")

    # turnover between reviews (one-way), from target weights
    tos = []
    keys = sorted(w_tilt)
    for a, b in zip(keys[:-1], keys[1:]):
        wa, wb = w_tilt[a], w_tilt[b]
        u = wa.index.union(wb.index)
        tos.append({"effective": b.date(), "names_changed": len(set(wb.index) - set(wa.index)),
                    "one_way_turnover": 0.5 * (wb.reindex(u, fill_value=0) - wa.reindex(u, fill_value=0)).abs().sum()})
    pd.DataFrame(tos).to_csv(OUT / "turnover.csv", index=False, float_format="%.4f")

    # tracking by year and overall
    per = []
    for y, g in daily.groupby(daily.index.year):
        st = M.tracking_stats(g["replica_tilt"], g["nifty200mom30_tri"])
        ste = M.tracking_stats(g["replica_ew"], g["nifty200mom30_tri"])
        per.append({"year": y, "replica_tilt": (1 + g["replica_tilt"]).prod() - 1,
                    "replica_ew": (1 + g["replica_ew"]).prod() - 1,
                    "replica_turnover": (1 + g["replica_turnover"]).prod() - 1,
                    "replica_turnover": (1 + g["replica_turnover"]).prod() - 1,
                    "index_tri": (1 + g["nifty200mom30_tri"]).prod() - 1,
                    "nifty200_tri": (1 + g["nifty200_tri"]).prod() - 1,
                    "te_tilt": st["tracking_error"], "te_ew": ste["tracking_error"]})
    pd.DataFrame(per).to_csv(OUT / "by_year.csv", index=False, float_format="%.4f")

    # validation anchors: the actual lists captured on file
    anchors = []
    act30, stamp30 = actual_list("nifty200_momentum30")
    act200, stamp200 = actual_list("nifty200")
    last = sched.iloc[-1]
    if act30:
        ours = set(sel.loc[sel["review"] == last.review, "symbol"])
        anchors.append({"check": f"Momentum 30 selection, {last.review} review vs actual list captured {stamp30}",
                        "overlap": len(ours & act30), "of": len(act30),
                        "ours_only": " ".join(sorted(ours - act30)), "actual_only": " ".join(sorted(act30 - ours))})
    if act200:
        snap = pd.Timestamp(stamp200)
        dlast = adv6.index[adv6.index <= snap][-1]
        a6 = adv6.loc[dlast, cand].dropna()
        ours200 = set(a6[last_seen[a6.index] >= dlast - pd.Timedelta(days=10)].nlargest(PROXY_N).index)
        ours_mc = set(mcap_at(dlast)[0].nlargest(PROXY_N).index)
        anchors.append({"check": f"Nifty 200 proxy (estimated-mcap top 200 on {dlast.date()}) vs actual list captured {stamp200}",
                        "overlap": len(ours_mc & act200), "of": len(act200),
                        "ours_only": " ".join(sorted(ours_mc - act200)), "actual_only": " ".join(sorted(act200 - ours_mc))})
        anchors.append({"check": f"First-pass proxy (turnover top 200 on {dlast.date()}) vs actual list captured {stamp200}",
                        "overlap": len(ours200 & act200), "of": len(act200),
                        "ours_only": " ".join(sorted(ours200 - act200)), "actual_only": " ".join(sorted(act200 - ours200))})
        # isolate the universe approximation: score the REAL Nifty 200 at the last review
        fo_c = to_cid(fo.get(last.cutoff, set()), last.cutoff, changes)
        elig = [c for c in act200 if c in fo_c and c in adj.columns and
                first_seen.get(c, last.cutoff) <= last.cutoff - pd.Timedelta(days=365)]
        sc = M.momentum_scores(adj, last.cutoff, last.p7, last.p13, elig)
        oracle = set(sc.index[:M.TOP_N])
        if act30:
            anchors.append({"check": f"Same scoring on the ACTUAL Nifty 200 (no buffer), {last.review} vs actual Momentum 30",
                            "overlap": len(oracle & act30), "of": len(act30),
                            "ours_only": " ".join(sorted(oracle - act30)),
                            "actual_only": " ".join(sorted(act30 - oracle))})
    pd.DataFrame(anchors).to_csv(OUT / "anchors.csv", index=False)
    write_split(sel, OUT / "selections", "cutoff", float_format="%.5f")

    overall = {k: M.tracking_stats(daily[k], daily["nifty200mom30_tri"])
               for k in ("replica_tilt", "replica_ew", "replica_turnover")}
    live = daily.loc[LIVE_FROM:]
    overall["live_replica_tilt"] = M.tracking_stats(live["replica_tilt"], live["nifty200mom30_tri"])
    overall["live_replica_turnover"] = M.tracking_stats(live["replica_turnover"], live["nifty200mom30_tri"])
    overall["nifty200_vs_mom30"] = M.tracking_stats(daily["nifty200_tri"], daily["nifty200mom30_tri"])
    summary = {"built": str(pd.Timestamp.today().date()), "data_end": str(dates[-1].date()),
               "reviews": len(sched), "candidates": len(cand), "live_from": LIVE_FROM,
               "shares_known": int(ctx["shares"].notna().sum()), "clipped_daily_moves": int(wild),
               "audit": aud["status"].value_counts().to_dict(),
               "yahoo_check": aud["yf_check"].value_counts().to_dict(),
               "tracking": {k: {kk: (str(vv) if kk in ("start", "end") else vv) for kk, vv in v.items()}
                            for k, v in overall.items()}}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=float))
    log(json.dumps(summary, indent=2, default=float))
    log(pd.DataFrame(anchors)[["check", "overlap", "of"]].to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
