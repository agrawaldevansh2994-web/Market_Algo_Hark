"""Descriptive analysis — Layers 1 and 2 of the observatory.

Pure functions over the curated panels. Nothing here is fitted: every output is
a description of the sample or the answer to a named scope §3 question.

Conventions that hold throughout (research/02 §4):
  * Each series is used on its own observed days; nothing is forward-filled.
  * A two-series statistic uses the pairwise intersection of their dates.
  * A lag of k means k *observations* of the pairwise-intersected sample, not k
    calendar days — one week on weekly bars, one trading day on daily bars.
  * Nothing looks ahead: a value at date t is a function of data up to t only,
    unless a docstring says it is an in-sample description.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


# ------------------------------------------------------------ Layer 1

def drawdown(close: pd.Series) -> pd.Series:
    """Fractional distance below the running peak; 0 at a new high, −0.2 = 20% down."""
    s = close.dropna()
    return s / s.cummax() - 1


def rolling_vol(logret: pd.Series, window: int = 21, periods: int = TRADING_DAYS) -> pd.Series:
    """Annualised standard deviation of log returns over the trailing window."""
    r = logret.dropna()
    return r.rolling(window, min_periods=window).std() * np.sqrt(periods)


def trailing_percentile(s: pd.Series, window: int = 756, min_periods: int = 252) -> pd.Series:
    """Percentile rank (0–1) of each value within its own trailing window.

    Includes the value itself and uses only past data, so it can be shown live.
    The default window is three years of trading days."""
    s = s.dropna()
    return s.rolling(window, min_periods=min_periods).apply(lambda a: (a <= a[-1]).mean(), raw=True)


def period_returns(close: pd.DataFrame) -> pd.DataFrame:
    """Price return over standard look-backs, each series measured to its own last date.

    Series publish on different calendars (FRED lags by days), so the as-of date
    is returned alongside rather than assuming everything ends together."""
    offsets = {
        "1W": pd.DateOffset(days=7),
        "1M": pd.DateOffset(months=1),
        "3M": pd.DateOffset(months=3),
        "1Y": pd.DateOffset(years=1),
    }
    rows = {}
    for col in close.columns:
        s = close[col].dropna()
        if len(s) < 2:
            continue
        last_date, last = s.index[-1], float(s.iloc[-1])
        row: dict[str, float | pd.Timestamp] = {"as_of": last_date, "last": last,
                                                "1D": last / float(s.iloc[-2]) - 1}
        for name, off in offsets.items():
            ref = s.loc[: last_date - off]
            row[name] = last / float(ref.iloc[-1]) - 1 if len(ref) else np.nan
        ytd = s.loc[: f"{last_date.year - 1}-12-31"]
        row["YTD"] = last / float(ytd.iloc[-1]) - 1 if len(ytd) else np.nan
        rows[col] = row
    out = pd.DataFrame(rows).T
    return out[["as_of", "last", "1D", "1W", "1M", "3M", "YTD", "1Y"]]


def summary_stats(close: pd.Series) -> dict[str, float]:
    """Distribution and risk description of one price series on its own calendar."""
    s = close.dropna()
    r = np.log(s).diff().dropna()
    years = (s.index[-1] - s.index[0]).days / 365.25
    return {
        "from": s.index[0], "to": s.index[-1], "n_obs": len(s),
        "cagr": (s.iloc[-1] / s.iloc[0]) ** (1 / years) - 1 if years > 0 else np.nan,
        "ann_vol": r.std() * np.sqrt(TRADING_DAYS),
        "skew": r.skew(),
        "excess_kurtosis": r.kurt(),
        "best_day": r.max(), "worst_day": r.min(),
        "max_drawdown": drawdown(s).min(),
        "pct_down_days": (r < 0).mean(),
    }


def rebase(close: pd.DataFrame, start: pd.Timestamp | None = None) -> pd.DataFrame:
    """Rescale every column to 100 on a shared start date, so different units compare
    on ONE axis (never a dual axis). Default start: the first date all columns have."""
    d = close.dropna(how="any") if start is None else close.loc[start:]
    d = d.dropna(how="any")
    return d / d.iloc[0] * 100


# ------------------------------------------------------------ Layer 2

def rolling_corr(a: pd.Series, b: pd.Series, window: int = 60) -> pd.Series:
    """Rolling correlation on the pairwise intersection of the two series' dates."""
    x = pd.concat({"a": a, "b": b}, axis=1, join="inner").dropna()
    return x["a"].rolling(window, min_periods=window).corr(x["b"])


def lead_lag(x: pd.Series, y: pd.Series, lags=range(-5, 6)) -> pd.DataFrame:
    """corr(x_t, y_{t+k}) for each lag k, on the pairwise-intersected sample.

    k > 0: x leads y by k observations. k < 0: x lags y. k = 0 is the
    contemporaneous correlation. `band` is the rough ±1.96/√n noise band under no
    relationship — a guard against reading structure into small wiggles."""
    df = pd.concat({"x": x, "y": y}, axis=1, join="inner").dropna()
    rows = []
    for k in lags:
        m = pd.concat([df["x"], df["y"].shift(-k)], axis=1).dropna()
        n = len(m)
        rows.append({"lag": k, "corr": m.iloc[:, 0].corr(m.iloc[:, 1]) if n > 2 else np.nan,
                     "n": n, "band": 1.96 / np.sqrt(n) if n > 0 else np.nan})
    return pd.DataFrame(rows).set_index("lag")


def regime_labels(level: pd.Series, calm_q: float = 0.5, stress_q: float = 0.9) -> pd.Series:
    """Label each date calm / elevated / stress from the series' own quantiles.

    IN-SAMPLE description: the quantile cut-offs use the whole history, so this
    is for studying the past, not for a live signal (use trailing_percentile
    for that). Returns an ordered categorical."""
    lv = level.dropna()
    lo, hi = lv.quantile(calm_q), lv.quantile(stress_q)
    lab = pd.Series(np.where(lv >= hi, "stress", np.where(lv <= lo, "calm", "elevated")), index=lv.index)
    return pd.Series(pd.Categorical(lab, categories=["calm", "elevated", "stress"], ordered=True),
                     index=lv.index, name="regime")


def corr_by_regime(returns: pd.DataFrame, regime: pd.Series, lag_regime: bool = True,
                   min_obs: int = 60) -> dict[str, pd.DataFrame]:
    """Correlation matrix of returns within each regime (question D3).

    With lag_regime=True (default) a day is classified by the regime at the
    PREVIOUS observation's close. That matters: conditioning on same-day
    volatility mechanically inflates correlations (Forbes & Rigobon, 2002), so a
    "stress" correlation measured that way would partly be an artefact of the
    selection. Pairwise-complete observations within each regime."""
    reg = regime.dropna()
    if lag_regime:
        reg = reg.shift(1).dropna()
    reg = reg.reindex(returns.index).dropna()
    out: dict[str, pd.DataFrame] = {}
    for label in reg.cat.categories if hasattr(reg, "cat") else sorted(reg.unique()):
        idx = reg.index[reg == label]
        out[str(label)] = returns.loc[idx].corr(min_periods=min_obs)
    return out


# -------------------------------------------------------------- flows

def nsdl_to_trade_date(flow: pd.Series, trading_days: pd.DatetimeIndex) -> pd.Series:
    """Re-date NSDL flows from reporting date to the trading day they describe.

    NSDL's own footnote: a reporting date covers trades "on and up to the
    previous trading day" (research/02 §4.8; measured in market_patterns.md).
    Each row moves to the last trading day strictly before its reporting date.
    Rows that land on the same trading day are summed, so cumulative flow is
    preserved exactly. Rows with no earlier trading day are dropped."""
    td = pd.DatetimeIndex(trading_days).sort_values().unique()
    f = flow.dropna()
    pos = td.searchsorted(f.index, side="left") - 1
    keep = pos >= 0
    out = pd.Series(f.to_numpy()[keep], index=td[pos[keep]], name=flow.name)
    return out.groupby(level=0).sum()


def cumulative(flow: pd.Series) -> pd.Series:
    return flow.dropna().cumsum()
