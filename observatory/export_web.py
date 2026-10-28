"""Export the dashboard's data as compact JSON for the static site in ../web/.

    python export_web.py            # writes ../web/data/*.json (one file per view + meta.json)
    python export_web.py --out DIR

Why: Vercel cannot run Streamlit, and the hosted refresh path can only push text.
This script loads exactly what dashboard.py loads (same curated panels, same obs/*
functions, the dashboard's own helpers such as load_mom / NAMES / SER_MOM) and
writes the numbers each view shows. No strategy or analysis logic lives here: every
statistic is computed by obs.analysis / obs.momentum, with the same arguments the
dashboard passes. Window-dependent views (1Y/3Y/5Y/10Y/Max) ship the full series;
the site clips them in the browser the way dashboard.clip() does.

Descriptive only — nothing here is a signal, forecast or backtest.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import types
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from paper.view import paper_frame

HERE = Path(__file__).parent
DEFAULT_OUT = HERE.parent / "web" / "data"
IST = timezone(timedelta(hours=5, minutes=30))


# ------------------------------------------------------------ reuse dashboard.py

def load_dashboard() -> types.ModuleType:
    """Import dashboard.py's helpers without rendering the Streamlit app.

    dashboard.py ends with a bare `main()` call (Streamlit runs it as a script), so a
    plain import would render the whole app. We execute the same source minus that
    final call, which gives us its constants and data loaders unchanged."""
    import logging
    import os
    os.environ.setdefault("STREAMLIT_LOGGER_LEVEL", "error")   # quiet "No runtime found" cache warnings
    logging.getLogger("streamlit").setLevel(logging.ERROR)
    for name in list(logging.root.manager.loggerDict):
        if name.startswith("streamlit"):
            logging.getLogger(name).setLevel(logging.ERROR)
    src = (HERE / "dashboard.py").read_text(encoding="utf-8")
    lines = src.rstrip().splitlines()
    if lines and lines[-1].strip() == "main()":
        lines = lines[:-1]
    mod = types.ModuleType("dashboard_lib")
    mod.__file__ = str(HERE / "dashboard.py")
    sys.modules["dashboard_lib"] = mod
    exec(compile("\n".join(lines) + "\n", str(HERE / "dashboard.py"), "exec"), mod.__dict__)
    for name in list(logging.root.manager.loggerDict):      # silence "No runtime found" cache warnings
        if name.startswith("streamlit"):
            logging.getLogger(name).setLevel(logging.ERROR)
    return mod


# ------------------------------------------------------------------ encoding

def _num(v, nd):
    if v is None:
        return None
    if isinstance(v, (int, np.integer)) and not isinstance(v, (bool, np.bool_)):
        return int(v)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    if math.isnan(f) or math.isinf(f):
        return None
    r = round(f, nd)
    return int(r) if nd == 0 else r


def series_obj(df: pd.DataFrame | pd.Series, nd: int | dict = 4) -> dict:
    """{'d0': first date, 'dd': [day gaps...], 'c': {col: [values|null...]}}.

    Dates are delta-encoded (days since the previous row; the site rebuilds them) to keep
    the files small; one shared date list per frame."""
    if isinstance(df, pd.Series):
        df = df.to_frame(df.name or "v")
    idx = pd.DatetimeIndex(df.index)
    gaps = (np.diff(idx.values.astype("datetime64[D]").astype(np.int64)).tolist() if len(idx) > 1 else [])
    out = {"d0": idx[0].strftime("%Y-%m-%d") if len(idx) else None, "dd": [int(g) for g in gaps], "c": {}}
    for c in df.columns:
        n = nd.get(c, 4) if isinstance(nd, dict) else nd
        out["c"][str(c)] = [_num(v, n) for v in df[c].to_numpy()]
    return out


def table_obj(df: pd.DataFrame, nd: int | dict = 4, index: str | None = None) -> dict:
    """{'cols': [...], 'rows': [[...]...]}; index (if named) becomes the first column."""
    d = df.reset_index() if index is not None else df.copy()
    if index is not None:
        d = d.rename(columns={d.columns[0]: index})
    rows = []
    for rec in d.itertuples(index=False):
        row = []
        for c, v in zip(d.columns, rec):
            if v is pd.NaT or (isinstance(v, (pd.Timestamp, datetime)) and pd.isna(v)):
                row.append(None)
            elif isinstance(v, (pd.Timestamp, datetime)):
                row.append(pd.Timestamp(v).strftime("%Y-%m-%d"))
            elif isinstance(v, (bool, np.bool_)):
                row.append(bool(v))
            elif isinstance(v, (int, float, np.integer, np.floating)):
                n = nd.get(c, 4) if isinstance(nd, dict) else nd
                row.append(_num(v, n))
            elif v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NaT:
                row.append(None)
            else:
                row.append(None if pd.isna(v) else str(v))
        rows.append(row)
    return {"cols": [str(c) for c in d.columns], "rows": rows}


def write(out: Path, name: str, obj: dict) -> int:
    p = out / f"{name}.json"
    txt = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    p.write_text(txt, encoding="utf-8")
    return len(txt.encode("utf-8"))


def d8(ts) -> str | None:
    return None if ts is None or pd.isna(ts) else pd.Timestamp(ts).strftime("%Y-%m-%d")


# --------------------------------------------------------------------- views

def export_overview(D, close, rd) -> dict:
    A = D.A
    tiles = [("nifty50", "{:,.0f}"), ("niftybank", "{:,.0f}"), ("indiavix", "{:.2f}"),
             ("usdinr", "{:.2f}"), ("brent_usd", "${:.2f}")]
    pr = A.period_returns(close[[k for k, _ in tiles]])
    tile_rows = [{"key": k, "name": D.NAMES[k], "value": f.format(pr.loc[k, "last"]),
                  "last": _num(pr.loc[k, "last"], 4), "d1": _num(pr.loc[k, "1D"], 6),
                  "as_of": d8(pr.loc[k, "as_of"])} for k, f in tiles]
    four = ["nifty50", "niftybank", "niftyit", "niftymidcap"]
    c4 = close[four].dropna(how="all")
    dd = A.drawdown(close["nifty50"])
    pr_all = A.period_returns(close[[c for c in D.NAMES if c in close.columns]])
    view = pr_all.copy()
    view.index = [D.NAMES[i] for i in view.index]
    for c in ["1D", "1W", "1M", "3M", "YTD", "1Y"]:
        view[c] = view[c].astype(float) * 100
    view["as_of"] = pd.to_datetime(view["as_of"]).dt.strftime("%Y-%m-%d")
    view["last"] = view["last"].astype(float)
    return {
        "tiles": tile_rows,
        "names": {k: D.NAMES[k] for k in four},
        # clip anchor: dashboard clips close[four] by the whole panel's last date
        "panel_last": d8(close.index[-1]),
        "close4": series_obj(c4, 2),
        "drawdown": series_obj(dd.rename("nifty50"), 5),
        "returns": table_obj(view, {"last": 2, "1D": 2, "1W": 2, "1M": 2, "3M": 2, "YTD": 2, "1Y": 2}, index="series"),
    }


def export_structure(D, close, rd, rw) -> dict:
    A = D.A
    others = ["niftybank", "niftyit", "niftymidcap"]
    wins = [20, 60, 120, 250]
    rc = {}
    for o in others:
        frames = {f"{o}_{w}": A.rolling_corr(rd["nifty50"], rd[o], w) for w in wins}
        rc[o] = series_obj(pd.concat(frames, axis=1).dropna(how="all"), 3)

    vix = close["indiavix"].dropna()
    out_d1, out_d3 = {}, {}
    inside = ["niftybank", "niftyit", "niftymidcap"]
    cross = ["sp500", "usdinr", "dxy", "brent_usd", "gold_usd", "copper_usd"]
    for expanding in (False, True):
        key = "expanding" if expanding else "full"
        reg = A.regime_labels(vix, expanding=expanding)
        lag = reg.shift(1).reindex(rd.index)
        rows = []
        for lab in ["calm", "elevated", "stress"]:      # same rows as dashboard.page_structure
            r = rd["nifty50"][lag == lab].dropna()
            rows.append({"regime (prior close)": lab, "days": len(r),
                         "mean daily %": r.mean() * 100, "± std. error": r.std() / np.sqrt(len(r)) * 100,
                         "annualised vol %": r.std() * np.sqrt(252) * 100,
                         "worst day %": r.min() * 100, "best day %": r.max() * 100})
        t = pd.DataFrame(rows).set_index("regime (prior close)").round(3)
        out_d1[key] = table_obj(t, 3, index="regime (prior close)")

        out_d = A.corr_by_regime(rd[["nifty50", *inside]], reg)
        tab_d = pd.DataFrame({k: v["nifty50"].drop("nifty50") for k, v in out_d.items()})
        tab_d.index = [D.NAMES[i] for i in tab_d.index]
        reg_w = A.regime_labels(close["indiavix"].dropna().resample("W-FRI").last().dropna(),
                                expanding=expanding, min_periods=52)
        out_w = A.corr_by_regime(rw[["nifty50", *cross]], reg_w)
        tab_w = pd.DataFrame({k: v["nifty50"].drop("nifty50") for k, v in out_w.items()})
        tab_w.index = [D.NAMES[i] for i in tab_w.index]
        n_w = reg_w.shift(1).reindex(rw.index).value_counts()
        out_d3[key] = {"daily": table_obj(tab_d, 3, index="series"), "weekly": table_obj(tab_w, 3, index="series"),
                       "weeks": {k: int(n_w.get(k, 0)) for k in ["calm", "elevated", "stress"]}}
    return {"names": {k: D.NAMES[k] for k in others}, "wins": wins, "rc": rc,
            "cutoffs": {"median": _num(vix.quantile(0.5), 1), "top_decile": _num(vix.quantile(0.9), 1)},
            "d1": out_d1, "d3": out_d3}


def export_flows(D, close, rd, rw, flows, raw) -> dict:
    A = D.A
    trading = close["nifty50"].dropna().index
    f_td = A.nsdl_to_trade_date(flows["fpi_equity_exch_nsdl"].dropna(), trading)
    cum = A.cumulative(f_td)
    out = {"nifty": series_obj(close["nifty50"].dropna().rename("nifty50"), 2),
           "fpi_cum": series_obj(cum.rename("fpi_cum"), 1)}
    ll = {}
    for freq in ("Daily", "Weekly"):
        if freq == "Daily":
            flow, ret = f_td, rd["nifty50"].dropna()
        else:
            flow, ret = f_td.resample("W-FRI").sum(), rw["nifty50"].dropna()
        t = A.lead_lag(flow, ret, range(-5, 6))
        ll[freq] = table_obj(t, 4, index="lag")
    out["lead_lag"] = ll
    poi = raw["poi"]
    if poi is not None:
        cols = ["fii_idx_fut_net", "dii_idx_fut_net", "pro_idx_fut_net", "client_idx_fut_net"]
        out["poi"] = series_obj(poi[cols], 0)
        out["poi_full"] = {"min": d8(poi.index.min()), "max": d8(poi.index.max()), "n": int(len(poi))}
    else:
        out["poi"] = None
    cash = raw["cash"]
    if cash is not None:
        lost = D.lost_capture_days(cash.index, trading)
        v = cash[["fii_net", "dii_net", "source"]].sort_index(ascending=False).head(15)
        v.index = v.index.strftime("%Y-%m-%d")
        v = v.rename(columns={"fii_net": "FII net (₹ cr)", "dii_net": "DII net (₹ cr)"})
        out["cash"] = table_obj(v, 2, index="date")
        out["lost"] = [d8(d) for d in lost]
    else:
        out["cash"], out["lost"] = None, []
    return out


def export_mom30(D) -> dict | None:
    MOM = D.MOM
    m = D.load_mom((MOM / "summary.json").stat().st_mtime if (MOM / "summary.json").exists() else 0)
    if m is None:
        return None
    d, summ = m["daily"], m["summary"]
    d.index = pd.to_datetime(d.index)
    out = {"summary": summ,
           "series": {c: {"name": n, "slot": s} for c, (n, s) in D.SER_MOM.items()},
           "daily": series_obj(d[list(D.SER_MOM)], 6)}
    by = m["by_year"].copy()
    by["gap_tilt"] = by["replica_tilt"] - by["index_tri"]
    show_by = by[["year", "replica_tilt", "replica_ew", "index_tri", "nifty200_tri", "gap_tilt", "te_tilt"]].copy()
    for c in show_by.columns[1:]:
        show_by[c] = (show_by[c] * 100).round(1)
    out["by_year"] = table_obj(show_by.set_index("year").rename(columns={
        "replica_tilt": "replica %", "replica_ew": "replica EW %", "index_tri": "Mom30 TRI %",
        "nifty200_tri": "Nifty 200 TRI %", "gap_tilt": "gap pts", "te_tilt": "tracking error %"}), 1, index="year")
    out["gap_bars"] = {"year": [int(y) for y in by["year"]], "gap": [_num(v * 100, 2) for v in by["gap_tilt"]]}

    from obs.momentum import tracking_stats
    eras = []
    for a_, b_, lab in [("2005", "2012", "2005–2012"), ("2013", "2017", "2013–2017"),
                        ("2018", str(d.index[-1].year), f"2018–{d.index[-1].year}"),
                        (summ.get("live_from", "2020-08-25"), str(d.index[-1].date()), "live (since launch)")]:
        g = d.loc[a_:b_]
        t_ = tracking_stats(g["replica_tilt"], g["nifty200mom30_tri"])
        eras.append({"era": lab, "replica CAGR %": round(t_["cagr_rep"] * 100, 1),
                     "index CAGR %": round(t_["cagr_bench"] * 100, 1), "gap pts/yr": round(t_["gap_pa"] * 100, 1),
                     "tracking error %": round(t_["tracking_error"] * 100, 1), "correlation": round(t_["corr"], 3)})
    out["eras"] = table_obj(pd.DataFrame(eras).set_index("era"), 3, index="era")

    dc = m.get("decomp")
    if dc is not None:
        piv = dc.assign(gap=(dc["gap_pa"] * 100).round(1)).pivot_table(index="experiment", columns="era",
                                                                       values="gap", sort=False)
        te_piv = dc.assign(te=(dc["tracking_error"] * 100).round(1)).pivot_table(index="experiment", columns="era",
                                                                                 values="te", sort=False)
        out["decomp"] = {"gap": table_obj(piv, 1, index="experiment"), "te": table_obj(te_piv, 1, index="experiment")}
        j = m.get("jumps")
        if j is not None and len(j):
            jj = j[pd.to_datetime(j["date"]).dt.year < 2018]
            out["jumps"] = {"n": int(len(jj)), "net": _num(jj["contribution"].sum(), 5),
                            "unexplained": int(jj["unexplained_gap"].sum()),
                            "top": table_obj(jj.sort_values("contribution").head(25), 4)}
    out["anchors"] = table_obj(m["anchors"], 4) if len(m["anchors"]) else None

    sel = m["sel"]
    reviews = sorted(sel["review"].unique())
    picks = {}
    for rv in reviews:
        one = sel[sel["review"] == rv].sort_values("rank")
        tab = one[["symbol", "rank", "score", "ret6", "ret12", "sigma", "weight_tilt"]].copy()
        tab[["ret6", "ret12", "sigma", "weight_tilt"]] = (tab[["ret6", "ret12", "sigma", "weight_tilt"]] * 100).round(1)
        tab["score"] = tab["score"].round(2)
        tab = tab.rename(columns={"ret6": "6M return %", "ret12": "12M return %", "sigma": "volatility %",
                                  "weight_tilt": "weight %"})
        r0 = one.iloc[0]
        picks[str(rv)] = {"table": table_obj(tab, 2), "cutoff": d8(r0["cutoff"]), "effective": d8(r0["effective"]),
                          "n_eligible": int(r0["n_eligible"]), "n": int(len(one))}
    out["reviews"] = [str(r) for r in reviews]
    out["picks"] = picks
    to = m["turnover"]
    out["turnover"] = ({"names_changed": _num(to["names_changed"].mean(), 2),
                        "one_way": _num(to["one_way_turnover"].mean(), 4)} if len(to) else None)
    a = m["audit"]
    if a is not None:
        counts = a["status"].value_counts().rename("actions").to_frame()
        out["audit"] = {"counts": table_obj(counts, 0, index="status"),
                        "rows": table_obj(a.sort_values("ex_date", ascending=False), 5)}
    out["data_end"] = d8(d.index[-1])
    return out


def membership(pos: pd.DataFrame) -> dict | None:
    """Paper holdings vs the latest official Nifty200 Momentum 30 list (captured snapshots)."""
    try:
        from obs import universe as U
        m, as_of = U.members_at("nifty200_momentum30", pd.Timestamp(datetime.now(IST).date()))
    except Exception:  # noqa: BLE001: no snapshot yet; the view just omits the check
        return None
    off = set(m["symbol"].astype(str).str.strip())
    held = set(pos.loc[(pos["symbol"] != "CASH") & (pos["shares"] > 0), "symbol"].astype(str))
    return {"as_of": str(as_of)[:10], "overlap": len(off & held), "of": len(off),
            "held_not_in_index": sorted(held - off), "in_index_not_held": sorted(off - held)}


def export_paper(D) -> dict | None:
    P = D.PAPER
    if not (P / "daily.csv").exists():
        return None
    d = paper_frame(pd.read_csv(P / "daily.csv", parse_dates=["date"]))
    pos = pd.read_csv(P / "positions.csv")
    led = pd.read_csv(P / "ledger.csv")
    t = d.dropna(subset=["Index (TRI)"])
    tri_ret = t["Index (TRI)"].iloc[-1] if len(t) else None
    book_at_tri = t["Paper book"].iloc[-1] if len(t) else None
    dv = led[led["side"].astype(str).str.upper().eq("DIVIDEND")]
    divs = float((dv["qty"] * dv["price"]).sum())
    return {"nav": _num(d["nav"].iloc[-1], 2),
            "ret": _num(d["Paper book"].iloc[-1], 6), "idx_ret": _num(d["Index (price)"].iloc[-1], 6),
            "diff": _num(d["Paper book"].iloc[-1] - d["Index (price)"].iloc[-1], 6),
            "tri_ret": _num(tri_ret, 6), "tri_last": d8(t["date"].iloc[-1]) if len(t) else None,
            "tri_diff": _num(book_at_tri - tri_ret, 6) if len(t) else None,
            "first": d8(d["date"].iloc[0]), "last": d8(d["date"].iloc[-1]),
            "daily": table_obj(d[["date", "nav", "index_tri", "index_price", "Paper book", "Index (TRI)",
                                  "Index (price)"]] if "index_tri" in d else
                               d[["date", "nav", "index_price", "Paper book", "Index (price)"]], 6),
            "positions": table_obj(pos, 4), "ledger": table_obj(led, 4),
            "cost": _num(led["cost"].sum(), 2), "dividends": _num(divs, 2),
            "n_holdings": int(((pos["shares"] > 0) & (pos["symbol"] != "CASH")).sum()),
            "cash": _num(pos.loc[pos["symbol"] == "CASH", "shares"].sum(), 2),
            "membership": membership(pos)}


def export_health(D, close, flows, raw, run_checks: bool = True) -> dict:
    reg = D.load_registry()
    today = pd.Timestamp(datetime.now(IST).date())
    limits = {"yfinance": 4, "fred": 14}
    rows = []
    for k in close.columns:
        s = close[k].dropna()
        inst = reg.get(k)
        if inst is None or inst.is_derived or s.empty:
            continue
        rows.append({"series": D.NAMES.get(k, k), "key": k, "source": inst.source,
                     "last": s.index[-1].strftime("%Y-%m-%d"), "limit": limits.get(inst.source, 4)})
    for k in flows.columns:
        s = flows[k].dropna()
        rows.append({"series": k, "key": k, "source": "flows", "last": s.index[-1].strftime("%Y-%m-%d"), "limit": 4})
    if raw["poi"] is not None:
        rows.append({"series": "participant OI", "key": "participant_oi", "source": "nse archive",
                     "last": raw["poi"].index.max().strftime("%Y-%m-%d"), "limit": 4})
    for r in rows:   # age as of the export (the site also recomputes it in the reader's browser)
        r["age_at_build"] = int((today - pd.Timestamp(r["last"])).days)
    snaps = {k: len(list((D.RAW / D.store_key(k)).glob("*.parquet"))) if (D.RAW / D.store_key(k)).exists() else 0
             for k in D.INDEX_FILES}
    checks = None
    if run_checks:
        res = subprocess.run([sys.executable, "checks.py"], capture_output=True, text=True, cwd=HERE,
                             encoding="utf-8", errors="replace", timeout=300)
        checks = {"ok": res.returncode == 0, "output": (res.stdout[-8000:] or res.stderr[-4000:]),
                  "ran_at": datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")}
    log = D.DATA_ROOT / "capture.log"
    cap = ("\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]) if log.exists() else None)
    return {"today_at_build": d8(today), "rows": rows, "snapshots": snaps, "checks": checks, "capture_log": cap}


def export_meta(D, close, flows, raw, mom, paper) -> dict:
    through = {}
    for k in close.columns:
        s = close[k].dropna()
        if not s.empty:
            through[k] = d8(s.index[-1])
    for k in flows.columns:
        s = flows[k].dropna()
        if not s.empty:
            through[k] = d8(s.index[-1])
    if raw["poi"] is not None:
        through["participant_oi"] = d8(raw["poi"].index.max())
    if raw["cash"] is not None:
        through["nse_fiidii"] = d8(raw["cash"].index.max())
    if mom:
        through["mom30_replication"] = mom["data_end"]
    if paper:
        through["paper_last_mark"] = paper["last"]
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                             cwd=HERE).stdout.strip() or None
    except Exception:
        sha = None
    return {
        "title": "Market Observatory",
        "subtitle": ("Indian equities, derivatives and flows — descriptive analysis, plus the step-5 replication of a "
                     "published index; no signals or forecasts."),
        "data_through": d8(close["nifty50"].dropna().index[-1]),
        "through": through,
        "built_ist": datetime.now(IST).strftime("%Y-%m-%d %H:%M IST"),
        "commit": sha,
        "names": D.NAMES,
        "windows": list(D.WINDOWS),
        "palette": D.DARK,
        "slot": D.SLOT,
        "caveats": {
            "descriptive": "Descriptive only — nothing here is a signal, forecast or backtest.",
            "paper": ("PAPER ONLY, with no broker and no real money. ₹10,00,000 notional, bought at the 16 Oct 2026 open "
                      "at the June 2026 review weights (whole shares, 0.1% per side cost, an estimate). The next "
                      "rebalance is the Dec 2026 review. Benchmark: Nifty200 Momentum 30 Total Return Index (official, "
                      "niftyindices.com); the price index is shown for context. Dividends are credited gross (pre-TDS) "
                      "on the ex-date and splits/bonuses adjust share counts; rights and demergers are not adjusted."),
            "benchmark_label": "Nifty200 Momentum 30 TRI (official, niftyindices.com)",
            "mom30_benchmark": "Nifty200 Momentum 30 TRI (the answer key)",
            "costs": "Costs are estimates (0.1% per side).",
            "mom30_gross": "Replication results are gross of costs, like the TRI.",
            "commodities": ("Commodities and FX are context only: they trade outside Indian hours, so cross-asset "
                            "comparisons use weekly bars (scope §4.1)."),
            "fred_lag": "FRED publishes with a lag, so as-of dates differ by series and are shown.",
            "static": ("Static snapshot: numbers are as of the build time above, refreshed once a day; nothing on "
                       "this page updates live."),
        },
    }


def run(out: Path = DEFAULT_OUT, run_checks: bool = True, ensure: bool = True) -> dict[str, int]:
    D = load_dashboard()
    if ensure:
        D.ensure_curated()    # same guard the hosted app uses: rebuild curated if raw snapshots changed
    close, rd, rw, flows = D.load(D.stamp())
    raw = D.raw_tables(D.stamp())
    out.mkdir(parents=True, exist_ok=True)
    sizes = {}
    sizes["overview"] = write(out, "overview", export_overview(D, close, rd))
    sizes["structure"] = write(out, "structure", export_structure(D, close, rd, rw))
    sizes["flows"] = write(out, "flows", export_flows(D, close, rd, rw, flows, raw))
    mom = export_mom30(D)
    sizes["mom30"] = write(out, "mom30", mom or {"missing": True})
    paper = export_paper(D)
    sizes["paper"] = write(out, "paper", paper or {"missing": True})
    sizes["health"] = write(out, "health", export_health(D, close, flows, raw, run_checks))
    sizes["meta"] = write(out, "meta", export_meta(D, close, flows, raw, mom, paper))
    return sizes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--no-checks", action="store_true", help="skip running checks.py")
    ap.add_argument("--no-ensure", action="store_true",
                    help="trust data/curated as is (use right after build.py; skips the fingerprint rebuild)")
    a = ap.parse_args()
    sizes = run(a.out, run_checks=not a.no_checks, ensure=not a.no_ensure)
    for k, v in sizes.items():
        print(f"{k + '.json':16s} {v / 1024:8.1f} KB")
    print(f"{'total':16s} {sum(sizes.values()) / 1024:8.1f} KB  -> {a.out}")
    big = [k for k, v in sizes.items() if v > 1_000_000]
    return 1 if big else 0


if __name__ == "__main__":
    sys.exit(main())
