"""Market Observatory dashboard.   Run from observatory/:  streamlit run dashboard.py

Descriptive only — nothing here is a signal, forecast or backtest (research/02 §4.4).
Every chart answers a named scope §3 question and every chart has a table twin.
Policies enforced in the numbers: pairwise-intersected dates, no forward-fill,
weekly bars for cross-session pairs (§4.1), NSDL flows re-dated to the trading
day they describe (§4.8).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from obs import analysis as A
from obs.flows import NSE_KEY, lost_capture_days
from obs.fno import POI_KEY, positioning_panel
from obs.registry import load_registry
from obs.store import CURATED, DATA_ROOT, RAW, read_curated, read_partitions
from obs.universe import INDEX_FILES, store_key

HERE = Path(__file__).parent
FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"

# ----------------------------------------------------------------- palette
# Reference palette from the dataviz skill; slots 1-4 validated in both modes.
LIGHT = dict(ink="#0b0b0b", ink2="#52514e", muted="#898781", grid="#e1e0d9", axis="#c3c2b7",
             mid="#f0efec", on_strong="#ffffff",
             series=["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"],
             neg="#e34948", pos=["#86b6ef", "#1c5cab"])
DARK = dict(ink="#ffffff", ink2="#c3c2b7", muted="#898781", grid="#2c2c2a", axis="#383835",
            mid="#383835", on_strong="#0b0b0b",
            series=["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
            neg="#e66767", pos=["#256abf", "#6da7ec"])

# Colour follows the entity, never its rank (anti-pattern: recolour-on-filter).
SLOT = {"nifty50": 0, "niftybank": 1, "niftyit": 2, "niftymidcap": 3, "indiavix": 4,
        "fii": 0, "dii": 1, "pro": 2, "client": 3}
NAMES = {"nifty50": "Nifty 50", "niftybank": "Nifty Bank", "niftyit": "Nifty IT",
         "niftymidcap": "Nifty Midcap 50", "indiavix": "India VIX", "sp500": "S&P 500",
         "vix": "CBOE VIX", "usdinr": "USD/INR", "dxy": "US Dollar Index", "brent_usd": "Brent (USD)",
         "wti_usd": "WTI (USD)", "gold_usd": "Gold (USD)", "silver_usd": "Silver (USD)",
         "copper_usd": "Copper (USD)", "usdjpy": "USD/JPY", "eurusd": "EUR/USD", "usdcny": "USD/CNY"}
WINDOWS = {"1Y": 1, "3Y": 3, "5Y": 5, "10Y": 10, "Max": None}


def pal() -> dict:
    try:
        return DARK if st.context.theme.type == "dark" else LIGHT
    except Exception:
        return LIGHT


def color(p: dict, key: str) -> str:
    return p["series"][SLOT[key]]


def mix(a: str, b: str, t: float) -> str:
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


def div_scale(p: dict) -> list:
    """Diverging blue (positive) / red (negative) with a neutral gray midpoint."""
    return [[0.0, p["neg"]], [0.25, mix(p["mid"], p["neg"], 0.5)], [0.5, p["mid"]],
            [0.75, p["pos"][0]], [1.0, p["pos"][1]]]


# -------------------------------------------------------------------- data

def stamp() -> tuple:
    return tuple(sorted((q.name, q.stat().st_mtime) for q in CURATED.glob("*.parquet")))


@st.cache_data(show_spinner=False)
def load(_stamp):
    return (read_curated("close_daily"), read_curated("logret_daily"),
            read_curated("logret_weekly"), read_curated("flows_daily"))


@st.cache_data(show_spinner=False)
def raw_tables(_stamp):
    out = {}
    try:
        out["cash"] = read_partitions(NSE_KEY)
    except FileNotFoundError:
        out["cash"] = None
    try:
        out["poi"] = positioning_panel()
    except FileNotFoundError:
        out["poi"] = None
    return out


def clip(df, window: str):
    years = WINDOWS[window]
    if years is None or df.empty:
        return df
    return df.loc[df.index[-1] - pd.DateOffset(years=years):]


# ------------------------------------------------------------------ figures

def base_fig(p: dict, height: int = 360, rows: int = 1, **kw) -> go.Figure:
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.08, **kw) if rows > 1 else go.Figure()
    fig.update_layout(
        height=height, margin=dict(l=56, r=16, t=30, b=40),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, size=12, color=p["ink2"]), hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(color=p["ink2"])),
        hoverlabel=dict(font_family=FONT),
    )
    fig.update_xaxes(showgrid=False, showline=True, linecolor=p["axis"], ticks="outside", tickcolor=p["axis"],
                     showspikes=True, spikemode="across", spikethickness=1, spikecolor=p["muted"],
                     spikedash="solid", spikesnap="cursor")
    fig.update_yaxes(gridcolor=p["grid"], gridwidth=1, zeroline=False, showline=False)
    return fig


def line(fig, x, y, name, c, row=None, fmt="%{y:,.2f}", width=2):
    kw = dict(row=row, col=1) if row else {}
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name=name, line=dict(color=c, width=width),
                             hovertemplate=f"{name}: {fmt}<extra></extra>"), **kw)


def show(fig):
    st.plotly_chart(fig, theme=None, width="stretch",
                    config={"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]})


def break_gaps(df: pd.DataFrame, max_days: int = 10) -> pd.DataFrame:
    """Insert a NaN row inside every gap longer than max_days, so a line chart breaks
    where data is missing instead of drawing a straight line across it."""
    gap = df.index.to_series().diff().dt.days > max_days
    if not gap.any():
        return df
    filler = pd.DataFrame(np.nan, index=df.index[gap] - pd.Timedelta(days=1), columns=df.columns)
    return pd.concat([df, filler]).sort_index()


def table_twin(df: pd.DataFrame, label: str = "Table view"):
    with st.expander(label):
        st.dataframe(df, width="stretch")


def heat(p: dict, mat: pd.DataFrame, height: int = 330) -> go.Figure:
    fig = go.Figure(go.Heatmap(z=mat.values, x=list(mat.columns), y=list(mat.index), zmin=-1, zmax=1,
                               colorscale=div_scale(p), showscale=True, xgap=2, ygap=2,
                               hovertemplate="%{y} · %{x}: %{z:.2f}<extra></extra>",
                               colorbar=dict(thickness=10, len=0.9, outlinewidth=0, tickfont=dict(color=p["ink2"]))))
    for i, r in enumerate(mat.index):
        for j, c in enumerate(mat.columns):
            v = mat.iloc[i, j]
            if pd.notna(v):
                fig.add_annotation(x=c, y=r, text=f"{v:.2f}", showarrow=False,
                                   font=dict(size=12, color=p["on_strong"] if abs(v) > 0.6 else p["ink"]))
    fig.update_layout(height=height, margin=dict(l=110, r=16, t=40, b=20), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(family=FONT, size=12, color=p["ink2"]))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(showgrid=False, side="top")
    return fig


# -------------------------------------------------------------------- pages

def page_overview(close, rd, window, p):
    st.caption("Where things stand. Each series is measured to its own last observation — FRED publishes "
               "with a lag, so as-of dates differ and are shown.")
    tiles = [("nifty50", "{:,.0f}"), ("niftybank", "{:,.0f}"), ("indiavix", "{:.2f}"),
             ("usdinr", "{:.2f}"), ("brent_usd", "${:.2f}")]
    pr = A.period_returns(close[[k for k, _ in tiles]])
    for col, (k, f) in zip(st.columns(len(tiles)), tiles):
        r = pr.loc[k]
        col.metric(NAMES[k], f.format(r["last"]), f"{r['1D'] * 100:+.2f}%", delta_color="off",
                   help=f"as of {pd.Timestamp(r['as_of']):%Y-%m-%d}")

    four = ["nifty50", "niftybank", "niftyit", "niftymidcap"]
    st.subheader("Indian equity indices, rebased to 100")
    st.caption("One axis; all four start at 100 on the first day all have data in the window.")
    idx = A.rebase(clip(close[four], window))
    fig = base_fig(p)
    for k in four:
        line(fig, idx.index, idx[k], NAMES[k], color(p, k), fmt="%{y:,.1f}")
    show(fig)
    table_twin(idx.round(2))

    st.subheader("Nifty 50 drawdown")
    st.caption("Distance below the running peak, measured from the start of the series (2007) — "
               "so the window changes what you see, not the numbers.")
    dd = clip(A.drawdown(close["nifty50"]), window)
    fig = base_fig(p, height=260)
    line(fig, dd.index, dd * 100, "Nifty 50 drawdown", color(p, "nifty50"), fmt="%{y:.1f}%")
    fig.update_yaxes(ticksuffix="%")
    fig.update_layout(showlegend=False)
    show(fig)
    table_twin((dd * 100).round(2).to_frame("drawdown_%"))

    st.subheader("Returns")
    pr_all = A.period_returns(close[[c for c in NAMES if c in close.columns]])
    view = pr_all.copy()
    view.index = [NAMES[i] for i in view.index]
    for c in ["1D", "1W", "1M", "3M", "YTD", "1Y"]:
        view[c] = view[c].astype(float) * 100
    view["as_of"] = pd.to_datetime(view["as_of"]).dt.strftime("%Y-%m-%d")
    st.dataframe(view, width="stretch", column_config={
        **{c: st.column_config.NumberColumn(c, format="%+.1f%%") for c in ["1D", "1W", "1M", "3M", "YTD", "1Y"]},
        "last": st.column_config.NumberColumn("Last", format="%,.2f")})


def page_structure(close, rd, rw, window, p):
    st.caption("How the Indian market is internally connected, and how that changes with volatility. "
               "Questions A1, D1, D3.")

    st.subheader("A1 · Does Nifty vs Bank Nifty break down in stress?")
    c1, c2 = st.columns(2)
    other = c1.selectbox("Compare Nifty 50 with", ["niftybank", "niftyit", "niftymidcap"],
                         format_func=NAMES.get)
    win = c2.segmented_control("Rolling window (trading days)", [20, 60, 120, 250], default=60) or 60
    rc = clip(A.rolling_corr(rd["nifty50"], rd[other], win), window)
    fig = base_fig(p, height=300)
    line(fig, rc.index, rc, f"Nifty 50 vs {NAMES[other]}", color(p, other), fmt="%{y:.2f}")
    fig.update_yaxes(range=[max(-1.0, np.floor((float(rc.min()) - 0.03) * 10) / 10), 1.0])
    fig.update_layout(showlegend=False)
    show(fig)
    st.caption(f"{win}-day rolling correlation of daily log returns, same exchange session so no timezone "
               f"contamination. Latest {rc.iloc[-1]:.2f}; window min {rc.min():.2f}, max {rc.max():.2f}. "
               "The vertical axis does not start at zero. Sharp steps are single extreme days entering or "
               "leaving the window — e.g. 4 Jun 2024 (Nifty −6.1%, Bank Nifty −8.3%) lifts the 60-day line by "
               "0.09 on the day and drops it 0.12 when it leaves 60 sessions later.")
    table_twin(rc.round(4).to_frame("corr"))

    st.subheader("D1 · What does Nifty do by India VIX regime?")
    vix = close["indiavix"].dropna()
    expanding = st.toggle("No look-ahead: expanding cut-offs (each day uses only VIX history up to that day)",
                          value=False, key="regime_expanding")
    reg = A.regime_labels(vix, expanding=expanding)
    lag = reg.shift(1).reindex(rd.index)
    rows = []
    for lab in ["calm", "elevated", "stress"]:
        r = rd["nifty50"][lag == lab].dropna()
        rows.append({"regime (prior close)": lab, "days": len(r),
                     "mean daily %": r.mean() * 100, "± std. error": r.std() / np.sqrt(len(r)) * 100,
                     "annualised vol %": r.std() * np.sqrt(252) * 100,
                     "worst day %": r.min() * 100, "best day %": r.max() * 100})
    lo, hi = vix.quantile(0.5), vix.quantile(0.9)
    st.dataframe(pd.DataFrame(rows).set_index("regime (prior close)").round(3), width="stretch")
    cut_text = ("Cut-offs are the median and top decile of VIX history *up to each day* (first year unlabelled), "
                "so nothing looks ahead. Each day" if expanding else
                f"Calm: India VIX ≤ {lo:.1f} (median). Stress: ≥ {hi:.1f} (top decile). Cut-offs use the whole "
                "history, so this describes the past; it is not a live signal. Toggle above for the no-look-ahead "
                "version. Each day")
    st.caption(cut_text + " is classified by the "
               "*previous* close. Note the mean-return column: its standard error is larger than the gaps "
               "between regimes — stress differs in variance, not demonstrably in average return.")

    st.subheader("D3 · Do correlations with Nifty converge in stress?")
    st.caption("Correlation with Nifty 50, split by India VIX regime at the previous close. Conditioning on "
               "same-day volatility would inflate correlations mechanically (Forbes & Rigobon 2002), which is "
               "why the lagged classification is used.")
    left, right = st.columns(2)
    inside = ["niftybank", "niftyit", "niftymidcap"]
    out_d = A.corr_by_regime(rd[["nifty50", *inside]], reg)
    tab_d = pd.DataFrame({k: v["nifty50"].drop("nifty50") for k, v in out_d.items()})
    tab_d.index = [NAMES[i] for i in tab_d.index]
    left.markdown("**Within India — daily**  \nSame trading session, so daily bars are clean.")
    left.plotly_chart(heat(p, tab_d, 200), theme=None, width="stretch", config={"displayModeBar": False})

    cross = ["sp500", "usdinr", "dxy", "brent_usd", "gold_usd", "copper_usd"]
    reg_w = A.regime_labels(close["indiavix"].dropna().resample("W-FRI").last().dropna(),
                            expanding=expanding, min_periods=52)
    out_w = A.corr_by_regime(rw[["nifty50", *cross]], reg_w)
    tab_w = pd.DataFrame({k: v["nifty50"].drop("nifty50") for k, v in out_w.items()})
    tab_w.index = [NAMES[i] for i in tab_w.index]
    right.markdown("**Cross-asset — weekly**  \nThese trade outside Indian hours; weekly bars shrink the "
                   "session mismatch (scope §4.1).")
    right.plotly_chart(heat(p, tab_w, 330), theme=None, width="stretch", config={"displayModeBar": False})
    n_w = reg_w.shift(1).reindex(rw.index).value_counts()
    st.caption("Weeks per regime — " + ", ".join(f"{k} {int(n_w.get(k, 0))}" for k in ["calm", "elevated", "stress"])
               + ". Stress cells rest on far fewer observations than calm ones; read small differences as noise.")
    table_twin(pd.concat({"within India (daily)": tab_d, "cross-asset (weekly)": tab_w}).round(3), "Table view — D3")


def page_flows(close, rd, rw, flows, window, p, raw):
    st.caption("Institutional flows. Questions E1 (do FPI flows lead Nifty?) and E3 (derivatives positioning).")
    trading = close["nifty50"].dropna().index
    f_td = A.nsdl_to_trade_date(flows["fpi_equity_exch_nsdl"].dropna(), trading)

    st.subheader("FPI equity flow vs Nifty 50")
    st.caption("Cumulative net FPI investment through the stock exchange (₹ crore, NSDL, custodian-confirmed), "
               "re-dated to the trading day it describes: NSDL's reporting date covers the previous trading day "
               "(scope §4.8). Two panels sharing a time axis — not a dual axis.")
    cum = clip(A.cumulative(f_td), window)
    nif = clip(close["nifty50"].dropna(), window)
    fig = base_fig(p, height=440, rows=2, row_heights=[0.55, 0.45])
    line(fig, nif.index, nif, "Nifty 50", color(p, "nifty50"), row=1, fmt="%{y:,.0f}")
    line(fig, cum.index, cum - cum.iloc[0], "Cumulative FPI flow (₹ cr)", color(p, "niftybank"), row=2, fmt="%{y:,.0f}")
    fig.update_layout(showlegend=True)
    show(fig)
    table_twin(pd.concat({"nifty50": nif, "fpi_cum_flow_cr": cum - cum.iloc[0]}, axis=1).round(1))

    st.subheader("E1 · Do FPI flows lead Nifty, or follow it?")
    freq = st.segmented_control("Frequency", ["Daily", "Weekly"], default="Weekly") or "Weekly"
    if freq == "Daily":
        flow, ret = f_td, rd["nifty50"].dropna()
    else:
        flow, ret = f_td.resample("W-FRI").sum(), rw["nifty50"].dropna()
    ll = A.lead_lag(flow, ret, range(-5, 6))
    fig = base_fig(p, height=320)
    fig.add_trace(go.Bar(x=ll.index, y=ll["corr"], name="correlation", marker_color=color(p, "nifty50"),
                         width=0.45, hovertemplate="lag %{x}: %{y:.3f}<extra></extra>"))
    for sign, show_leg in ((1, True), (-1, False)):
        fig.add_trace(go.Scatter(x=ll.index, y=sign * ll["band_hac"], mode="lines", name="±1.96 HAC noise band",
                                 showlegend=show_leg, line=dict(color=p["muted"], width=1),
                                 hovertemplate="band: %{y:.3f}<extra></extra>"))
    fig.update_xaxes(dtick=1, title=dict(text="lag k  ·  k > 0: flow leads Nifty  |  k < 0: flow follows Nifty",
                                         standoff=12))
    fig.update_yaxes(zeroline=True, zerolinecolor=p["axis"], title="correlation")
    fig.update_layout(margin=dict(l=56, r=16, t=30, b=70))
    show(fig)
    st.caption(f"{freq} bars, {int(ll['n'].iloc[0]):,} observations. The peak at k = 0 and the decay toward k < 0 "
               "mean flows move with the market and follow its recent direction. Bars at k > 0 would "
               "indicate flows *leading* — they stay inside the noise band. The band is Newey-West (HAC): robust to "
               "fat-tailed returns and persistent flows; the naive ±1.96/√n band is too narrow here (it is in the "
               "table as `band`). NSDL data, Dec 2009 onward. Several lags are inspected, so a bar only just "
               "outside the band is still not evidence.")
    table_twin(ll.round(4))

    st.subheader("E3 · Who holds index futures? Participant net positions")
    poi = raw["poi"]
    if poi is None:
        st.info("No participant open-interest data stored yet.")
    else:
        poi = clip(poi, window)
        shown = break_gaps(poi)
        fig = base_fig(p, height=330)
        for key, lab in (("fii", "FII"), ("dii", "DII"), ("pro", "Proprietary"), ("client", "Retail clients")):
            col = f"{key}_idx_fut_net"
            line(fig, shown.index, shown[col], lab, color(p, key), fmt="%{y:,.0f}")
        fig.update_yaxes(title="net contracts")
        show(fig)
        full = raw["poi"]
        weekdays = len(pd.bdate_range(poi.index.min(), poi.index.max()))
        st.caption(f"Net position (long − short) in index futures by participant type, from NSE's daily "
                   f"participant-wise open interest. Coverage in this window: {len(poi):,} of about {weekdays:,} "
                   f"weekdays ({len(poi) / weekdays:.0%}); lines break where data is missing. Stored history "
                   f"{full.index.min():%Y-%m-%d} to {full.index.max():%Y-%m-%d} ({len(full):,} days) — "
                   "the backfill of earlier years is still running. Every contract has a long and a short side, "
                   "so the four lines sum to zero each day.")
        table_twin(poi.round(0))

    st.subheader("Latest FII / DII (NSE provisional)")
    cash = raw["cash"]
    if cash is not None:
        lost = lost_capture_days(cash.index, trading)
        if lost:
            st.warning("No capture for trading day(s) " + ", ".join(f"{d:%Y-%m-%d}" for d in lost) +
                       " — permanent: the source serves only the latest day.", icon=":material/warning:")
        v = cash[["fii_net", "dii_net", "source"]].sort_index(ascending=False).head(15)
        v.index = v.index.strftime("%Y-%m-%d")
        st.dataframe(v.rename(columns={"fii_net": "FII net (₹ cr)", "dii_net": "DII net (₹ cr)"}), width="stretch")
        st.caption("Only the net columns are trusted: MSEI's FII sell value is inconsistent (market_patterns.md).")


def page_health(close, flows, raw, p):
    st.caption("Is the data current, and do the integrity checks pass?")
    reg = load_registry()
    today = pd.Timestamp.today().normalize()
    limits = {"yfinance": 4, "fred": 14}
    rows = []
    for k in close.columns:
        s = close[k].dropna()
        inst = reg.get(k)
        if inst is None or inst.is_derived or s.empty:
            continue
        age = (today - s.index[-1]).days
        lim = limits.get(inst.source, 4)
        rows.append({"series": NAMES.get(k, k), "source": inst.source, "last date": s.index[-1].strftime("%Y-%m-%d"),
                     "age (days)": age, "status": "✓ fresh" if age <= lim else f"! stale (>{lim}d)"})
    for k in flows.columns:
        s = flows[k].dropna()
        age = (today - s.index[-1]).days
        rows.append({"series": k, "source": "flows", "last date": s.index[-1].strftime("%Y-%m-%d"),
                     "age (days)": age, "status": "✓ fresh" if age <= 4 else "! stale (>4d)"})
    if raw["poi"] is not None:
        d = raw["poi"].index.max()
        rows.append({"series": "participant OI", "source": "nse archive", "last date": d.strftime("%Y-%m-%d"),
                     "age (days)": (today - d).days, "status": "✓ fresh" if (today - d).days <= 4 else "! stale (>4d)"})
    st.dataframe(pd.DataFrame(rows).set_index("series"), width="stretch")

    snaps = {k: len(list((RAW / store_key(k)).glob("*.parquet"))) if (RAW / store_key(k)).exists() else 0
             for k in INDEX_FILES}
    st.markdown("**Index membership snapshots** (point-in-time history, scope §4.9): " +
                " · ".join(f"{k} {n}" for k, n in snaps.items()))

    st.subheader("Integrity checks")
    if st.button("Run checks.py"):
        res = subprocess.run([sys.executable, "checks.py"], capture_output=True, text=True, cwd=HERE,
                             encoding="utf-8", errors="replace", timeout=300)
        if res.returncode == 0:
            st.success("All checks passed", icon=":material/check_circle:")
        else:
            st.error("One or more checks FAILED", icon=":material/error:")
        st.code(res.stdout[-8000:] or res.stderr[-4000:], language="text")

    st.subheader("Capture log (latest)")
    log = DATA_ROOT / "capture.log"
    if log.exists():
        st.code("\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]), language="text")
    else:
        st.info("capture.log not found — the scheduled capture has not run on this machine yet.")


# ------------------------------------------------------------ momentum 30

MOM = HERE / "reports" / "mom30"
SER_MOM = {"replica_tilt": ("Replica — score × liquidity weights", 0), "replica_ew": ("Replica — equal weight", 3),
           "nifty200mom30_tri": ("Nifty200 Momentum 30 TRI (the answer key)", 1),
           "nifty200_tri": ("Nifty 200 TRI", 2)}


@st.cache_data(show_spinner=False)
def load_mom(_stamp):
    from obs.textstore import read_split
    if not (MOM / "daily_returns").exists():
        return None
    rd_ = read_split(MOM / "daily_returns", index_col=0)
    out = {"daily": rd_,
           "sel": read_split(MOM / "selections", parse_dates=["cutoff", "effective"]),
           "by_year": pd.read_csv(MOM / "by_year.csv"),
           "anchors": pd.read_csv(MOM / "anchors.csv") if (MOM / "anchors.csv").exists() else pd.DataFrame(),
           "turnover": pd.read_csv(MOM / "turnover.csv"),
           "summary": __import__("json").loads((MOM / "summary.json").read_text())}
    audit_p = HERE / "reports" / "corpactions" / "audit.csv"
    out["audit"] = pd.read_csv(audit_p, parse_dates=["ex_date", "applied_date"]) if audit_p.exists() else None
    return out


def page_mom30(window, p):
    m = load_mom((MOM / "summary.json").stat().st_mtime if (MOM / "summary.json").exists() else 0)
    if m is None:
        st.info("No replication results yet. Run `python build_bhav.py` then `python build_momentum.py`.")
        return
    d, summ = m["daily"], m["summary"]
    tt, te = summ["tracking"]["replica_tilt"], summ["tracking"]["replica_ew"]
    st.subheader("⑤ Nifty200 Momentum 30 — how close does a free-data rebuild get?")
    st.caption("A measured replication of a published index (roadmap step 5), not a strategy signal. The "
               "methodology is NSE's (Sept 2026 document, pp. 187–189); what free data forces us to approximate is "
               "listed at the bottom. Success means an explained gap, not a zero one.")
    k = st.columns(5)
    k[0].metric("Replica CAGR", f"{tt['cagr_rep']:.1%}", help="Score × liquidity weights, total return, gross of costs")
    k[1].metric("Index TRI CAGR", f"{tt['cagr_bench']:.1%}")
    k[2].metric("Gap per year", f"{tt['gap_pa']:+.1%}", help="Replica minus index, annualised")
    k[3].metric("Tracking error", f"{tt['tracking_error']:.1%}", help="Annualised std. dev. of daily return differences")
    k[4].metric("Daily correlation", f"{tt['corr']:.3f}")
    st.caption(f"{tt['start']} → {tt['end']}, {summ['reviews']} semi-annual reviews. Equal-weight replica: "
               f"CAGR {te['cagr_rep']:.1%}, tracking error {te['tracking_error']:.1%}.")

    dd = clip(d, window)
    growth = (1 + dd).cumprod()
    fig = base_fig(p, 380)
    for col, (name, slot) in SER_MOM.items():
        line(fig, growth.index, growth[col], name, p["series"][slot], fmt="%{y:,.2f}×")
    fig.update_yaxes(type="log", title="growth of ₹1 (log)")
    show(fig)
    table_twin(growth.resample("ME").last().round(3), "Monthly values")

    st.subheader("Where the gap comes from, year by year")
    by = m["by_year"].copy()
    by["gap_tilt"] = by["replica_tilt"] - by["index_tri"]
    fig = base_fig(p, 300)
    fig.add_trace(go.Bar(x=by["year"], y=by["gap_tilt"] * 100, name="replica − index, % pts",
                         marker_color=[p["pos"][1] if v >= 0 else p["neg"] for v in by["gap_tilt"]],
                         hovertemplate="%{x}: %{y:+.1f} pts<extra></extra>"))
    fig.update_yaxes(zeroline=True, zerolinecolor=p["axis"], title="% points")
    show(fig)
    show_by = by[["year", "replica_tilt", "replica_ew", "index_tri", "nifty200_tri", "gap_tilt", "te_tilt"]].copy()
    for c in show_by.columns[1:]:
        show_by[c] = (show_by[c] * 100).round(1)
    st.dataframe(show_by.set_index("year").rename(columns={
        "replica_tilt": "replica %", "replica_ew": "replica EW %", "index_tri": "Mom30 TRI %",
        "nifty200_tri": "Nifty 200 TRI %", "gap_tilt": "gap pts", "te_tilt": "tracking error %"}), width="stretch")

    from obs.momentum import tracking_stats
    eras = []
    for a_, b_ in [("2005", "2012"), ("2013", "2017"), ("2018", str(d.index[-1].year))]:
        g = d.loc[a_:b_]
        t_ = tracking_stats(g["replica_tilt"], g["nifty200mom30_tri"])
        eras.append({"era": f"{a_}–{b_}", "replica CAGR %": round(t_["cagr_rep"] * 100, 1),
                     "index CAGR %": round(t_["cagr_bench"] * 100, 1), "gap pts/yr": round(t_["gap_pa"] * 100, 1),
                     "tracking error %": round(t_["tracking_error"] * 100, 1), "correlation": round(t_["corr"], 3)})
    st.dataframe(pd.DataFrame(eras).set_index("era"), width="stretch")
    unx = m["audit"][m["audit"]["status"] == "unexplained"] if m["audit"] is not None else pd.DataFrame(columns=["ex_date"])
    n_unx, n_old = len(unx), int((unx["ex_date"].dt.year <= 2012).sum()) if len(unx) else 0
    st.caption("The gap is concentrated before 2018. That is where NSE's corporate-action feed leaves the most "
               f"price gaps unexplained ({n_old} of {n_unx} fall in 2004–2012) and where the turnover proxy for "
               "Nifty 200 has no anchor to check it against.")

    st.subheader("Validation anchors — the real lists on file")
    if len(m["anchors"]):
        st.dataframe(m["anchors"], width="stretch", hide_index=True)
        st.caption("The first row tests the whole pipeline; the second tests only the universe proxy; the third "
                   "scores the *real* Nifty 200 with our code, so its overlap isolates the scoring from the "
                   "universe approximation. More anchors arrive as the forward capture records each review.")

    st.subheader("Picks at each review")
    sel = m["sel"]
    reviews = sorted(sel["review"].unique())
    rv = st.select_slider("Review", reviews, value=reviews[-1])
    one = sel[sel["review"] == rv].sort_values("rank")
    tab = one[["symbol", "rank", "score", "ret6", "ret12", "sigma", "weight_tilt"]].copy()
    tab[["ret6", "ret12", "sigma", "weight_tilt"]] = (tab[["ret6", "ret12", "sigma", "weight_tilt"]] * 100).round(1)
    tab["score"] = tab["score"].round(2)
    st.dataframe(tab.rename(columns={"ret6": "6M return %", "ret12": "12M return %", "sigma": "volatility %",
                                     "weight_tilt": "weight %"}), width="stretch", hide_index=True)
    r0 = one.iloc[0]
    st.caption(f"Cut-off {r0['cutoff']:%d %b %Y}, effective {r0['effective']:%d %b %Y}; "
               f"{int(r0['n_eligible'])} stocks eligible after the F&O and one-year-listing filters.")
    to = m["turnover"]
    if len(to):
        st.caption(f"Average names changed per review: {to['names_changed'].mean():.1f} of 30; average one-way "
                   f"turnover {to['one_way_turnover'].mean():.0%}.")

    st.subheader("Corporate-action audit")
    a = m["audit"]
    if a is not None:
        counts = a["status"].value_counts().rename("actions").to_frame()
        c1, c2 = st.columns([1, 2])
        c1.dataframe(counts, width="stretch")
        c2.caption("**applied** — NSE announced it and the price gapped by that factor on the ex-date. "
                   "**applied_shifted** — the gap came within 5 sessions of the announced date. "
                   "**no_gap** — announced, but the market never moved by that factor; *not* applied. "
                   "**scheme_market_implied** — demerger or scheme; factor = ex-date gap net of the day's median "
                   "move (an estimate). **unexplained** — a gap beyond −40% / +67% with nothing announced. "
                   "Scope: the stocks that ever reached the liquidity top 300 at a review.")
        pick = st.multiselect("Show status", list(counts.index), default=[x for x in ["no_gap", "unexplained"]
                                                                          if x in counts.index])
        st.dataframe(a[a["status"].isin(pick)].sort_values("ex_date", ascending=False), width="stretch",
                     hide_index=True)

    with st.expander("What free data forces us to approximate"):
        st.markdown(
            "- **A. Universe** — Nifty 200 membership history is not free. Proxy: top 200 by 6-month average "
            "daily turnover (point-in-time by construction). NSE ranks by market cap.\n"
            "- **B. Weights** — free-float market cap history is not free. Proxy: 6-month average turnover × "
            "score, capped at min(5%, 5× base weight). Equal weight shown alongside.\n"
            "- **C. Timing** — portfolio changes at the close of the last trading day of June/December; NSE's "
            "effective date is usually a few sessions earlier.\n"
            "- **D. Prices** — adjusted only where NSE's announcement and the market's own gap agree (audit above).\n"
            "- **E. Mid-period events** — delistings and ad-hoc replacements are not modelled.\n"
            "- Results are **gross of costs**, like the TRI. Single-day moves are clipped at −60% / +150% "
            f"({summ['clipped_daily_moves']} clipped).")


# --------------------------------------------------------------------- main

def main():
    st.set_page_config(page_title="Market Observatory", layout="wide", initial_sidebar_state="collapsed")
    p = pal()
    close, rd, rw, flows = load(stamp())
    raw = raw_tables(stamp())

    st.title("Market Observatory")
    st.caption("Indian equities, derivatives and flows — descriptive analysis, plus the step-5 replication of a "
               "published index; no signals or forecasts. Data through " + f"{close['nifty50'].dropna().index[-1]:%d %b %Y}.")

    nav, win = st.columns([3, 2])
    page = nav.segmented_control("View", ["Overview", "Equity structure", "Flows & positioning", "Momentum 30", "Data health"],
                                 default="Overview") or "Overview"
    window = win.segmented_control("Window", list(WINDOWS), default="5Y") or "5Y"

    if page == "Overview":
        page_overview(close, rd, window, p)
    elif page == "Equity structure":
        page_structure(close, rd, rw, window, p)
    elif page == "Flows & positioning":
        page_flows(close, rd, rw, flows, window, p, raw)
    elif page == "Momentum 30":
        page_mom30(window, p)
    else:
        page_health(close, flows, raw, p)


main()
