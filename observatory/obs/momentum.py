"""Nifty200 Momentum 30 — decomposed replication on free data (roadmap step 5).

Rules from the official methodology (Nifty Indices methodology document,
September 2026, pp. 187–189):

  eligible    Nifty 200 members, listed ≥ 1 year, in the F&O segment
  MR12        [P(M−1) / P(M−13) − 1] / σ        P = last trading day of the month,
  MR6         [P(M−1) / P(M−7) − 1]  / σ        M = rebalance month (June, December)
  σ           annualised std. dev. of daily log returns over 1 year
  z           (MR − mean) / std across the eligible universe, for 6 and 12
  wz          0.5·z12 + 0.5·z6
  score       1 + wz if wz ≥ 0, else 1 / (1 − wz)
  select      top 30 by score; buffer: ranks 1–15 always in, existing members
              ranked beyond 45 always out
  weight      free-float mcap × score, capped at min(5%, 5 × ffmcap weight)

What free data forces us to approximate (each is a named source of gap):

  A. Nifty 200 membership → top 200 by 6-month average daily turnover
     (point-in-time by construction). NSE ranks by free-float/full mcap.
  B. Free-float mcap for weights → 6-month average daily turnover. Also
     reported: equal weight.
  C. Effective date → the portfolio changes at the close of the last trading
     day of June / December. NSE's effective date is usually a few sessions
     earlier.
  D. Adjusted prices → obs.corpactions audit (announced ∩ observed).
  E. Ad-hoc mid-period replacements (delistings, mergers) are not modelled; a
     stock that stops trading is held at its last price until the next review.

All functions are pure: they take wide date × stock frames.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TOP_N = 30
MUST_IN = 15
MUST_OUT = 45
CAP_ABS = 0.05
CAP_MULT = 5.0


# ------------------------------------------------------------------ calendar

def month_ends(index: pd.DatetimeIndex) -> pd.Series:
    """Last trading day of each calendar month present in `index`."""
    s = pd.Series(index, index=index)
    return s.groupby(index.to_period("M")).max()


def rebalance_schedule(index: pd.DatetimeIndex, first: str = "2005-06") -> pd.DataFrame:
    """One row per June / December review: cutoff (last trading day of M−1),
    the M−7 and M−13 price dates, and effective (last trading day of M)."""
    me = month_ends(index)
    rows = []
    for m in me.index:
        if m.month not in (6, 12) or m < pd.Period(first, "M"):
            continue
        need = [m - 1, m - 7, m - 13]
        if not all(p in me.index for p in need):
            continue
        rows.append({"review": str(m), "cutoff": me[m - 1], "p7": me[m - 7], "p13": me[m - 13],
                     "effective": me[m]})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ scoring

def momentum_scores(adj_close: pd.DataFrame, cutoff, p7, p13, eligible) -> pd.DataFrame:
    """Methodology scores for `eligible` stocks as of `cutoff`."""
    elig = [c for c in eligible if c in adj_close.columns]
    px = adj_close[elig]
    window = px.loc[(px.index > cutoff - pd.Timedelta(days=365)) & (px.index <= cutoff)]
    lr = np.log(window / window.shift(1))
    sigma = lr.std() * np.sqrt(252)
    p_m1, p_m7, p_m13 = px.loc[cutoff], px.loc[p7], px.loc[p13]
    df = pd.DataFrame({"ret12": p_m1 / p_m13 - 1, "ret6": p_m1 / p_m7 - 1, "sigma": sigma})
    df = df.dropna()
    df = df[df["sigma"] > 0]
    df["mr12"] = df["ret12"] / df["sigma"]
    df["mr6"] = df["ret6"] / df["sigma"]
    df["z12"] = (df["mr12"] - df["mr12"].mean()) / df["mr12"].std()
    df["z6"] = (df["mr6"] - df["mr6"].mean()) / df["mr6"].std()
    df["wz"] = 0.5 * df["z12"] + 0.5 * df["z6"]
    df["score"] = np.where(df["wz"] >= 0, 1 + df["wz"], 1 / (1 - df["wz"]))
    df["rank"] = df["score"].rank(ascending=False, method="first").astype(int)
    return df.sort_values("rank")


def select(scores: pd.DataFrame, previous: list[str] | None) -> list[str]:
    """Top 30 with the methodology's buffer (15 in / 45 out)."""
    ranked = scores.sort_values("rank")
    if not previous:
        return list(ranked.index[:TOP_N])
    prev = set(previous)
    chosen = list(ranked.index[:MUST_IN])
    keep = [s for s in ranked.index[MUST_IN:MUST_OUT] if s in prev]
    for s in keep:
        if len(chosen) < TOP_N:
            chosen.append(s)
    for s in ranked.index[MUST_IN:]:
        if len(chosen) >= TOP_N:
            break
        if s not in chosen:
            chosen.append(s)
    return chosen


def capped_weights(score: pd.Series, size: pd.Series, cap_abs: float = CAP_ABS,
                   cap_mult: float = CAP_MULT) -> pd.Series:
    """weight ∝ size × score, each capped at min(cap_abs, cap_mult × size weight);
    the excess is redistributed pro rata to uncapped names until none breach."""
    base = size / size.sum()
    cap = np.minimum(cap_abs, cap_mult * base)
    raw = size * score
    w = raw / raw.sum()
    for _ in range(100):
        over = w > cap + 1e-12
        if not over.any():
            break
        excess = (w[over] - cap[over]).sum()
        w[over] = cap[over]
        free = ~over & (w < cap - 1e-12)
        if not free.any():
            break
        w[free] += excess * w[free] / w[free].sum()
    return w / w.sum()


# ------------------------------------------------------------------ returns

def drifting_portfolio(tr: pd.DataFrame, weights: dict[pd.Timestamp, pd.Series]) -> pd.Series:
    """Daily return of a portfolio reset to `weights[d]` at the close of each
    date d and left to drift until the next reset. tr is daily total return
    (NaN treated as 0 — a stock not trading holds its value)."""
    dates = sorted(weights)
    out = []
    for i, d in enumerate(dates):
        end = dates[i + 1] if i + 1 < len(dates) else tr.index[-1]
        seg = tr.loc[(tr.index > d) & (tr.index <= end), weights[d].index].fillna(0.0)
        if seg.empty:
            continue
        growth = (1 + seg).cumprod()
        value = growth.mul(weights[d], axis=1).sum(axis=1)
        prev = pd.concat([pd.Series([1.0], index=[d]), value.iloc[:-1]])
        prev.index = value.index
        out.append(value / prev.values - 1)
    return pd.concat(out) if out else pd.Series(dtype=float)


def tracking_stats(rep: pd.Series, bench: pd.Series) -> dict:
    """Annualised return of each, the gap, tracking error, correlation."""
    df = pd.concat({"rep": rep, "bench": bench}, axis=1).dropna()
    yrs = len(df) / 252
    cagr = lambda r: (1 + r).prod() ** (1 / yrs) - 1
    diff = df["rep"] - df["bench"]
    return {"start": df.index[0].date(), "end": df.index[-1].date(), "days": len(df),
            "cagr_rep": cagr(df["rep"]), "cagr_bench": cagr(df["bench"]),
            "gap_pa": cagr(df["rep"]) - cagr(df["bench"]),
            "tracking_error": diff.std() * np.sqrt(252), "corr": df["rep"].corr(df["bench"])}
