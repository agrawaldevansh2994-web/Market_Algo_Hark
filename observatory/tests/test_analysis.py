"""Every test builds data whose correct answer is known before running."""

import numpy as np
import pandas as pd
import pytest

from obs import analysis as A


def series(values, start="2020-01-01", freq="B", name=None):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq=freq), name=name,
                     dtype=float)


# ---------------------------------------------------------------- Layer 1

def test_drawdown_known_path():
    dd = A.drawdown(series([100, 110, 99, 120, 90]))
    assert dd.round(6).tolist() == [0.0, 0.0, -0.1, 0.0, -0.25]


def test_drawdown_never_positive():
    rng = np.random.default_rng(0)
    assert (A.drawdown(series(np.exp(np.cumsum(rng.normal(0, 0.01, 500))))) <= 0).all()


def test_rolling_vol_recovers_known_sigma():
    rng = np.random.default_rng(1)
    r = series(rng.normal(0, 0.01, 20000))
    est = A.rolling_vol(r, window=5000).dropna().iloc[-1]
    assert est == pytest.approx(0.01 * np.sqrt(252), rel=0.05)


def test_trailing_percentile_extremes():
    s = series(list(range(1, 301)))                      # strictly rising
    p = A.trailing_percentile(s, window=100, min_periods=50)
    assert p.dropna().eq(1.0).all()                      # always the max of its window
    p2 = A.trailing_percentile(series(list(range(300, 0, -1))), window=100, min_periods=50)
    assert p2.dropna().iloc[-100:].eq(0.01).all()        # full window, always the min: 1 of 100
    assert p2.dropna().iloc[0] == pytest.approx(1 / 50)  # first computed window is only 50 long


def test_trailing_percentile_has_no_lookahead():
    """Appending the future must not change any past value."""
    rng = np.random.default_rng(2)
    full = series(rng.normal(size=600).cumsum())
    past = full.iloc[:400]
    a = A.trailing_percentile(past, window=100, min_periods=50)
    b = A.trailing_percentile(full, window=100, min_periods=50).iloc[:400]
    pd.testing.assert_series_equal(a, b)


def test_period_returns_known_values():
    idx = pd.to_datetime(["2025-12-31", "2026-08-28", "2026-09-23", "2026-09-30"])
    close = pd.DataFrame({"x": [100.0, 110.0, 120.0, 132.0]}, index=idx)
    r = A.period_returns(close).loc["x"]
    assert r["1D"] == pytest.approx(132 / 120 - 1)
    assert r["1W"] == pytest.approx(132 / 120 - 1)       # last obs on/before 2026-09-23
    assert r["1M"] == pytest.approx(132 / 110 - 1)       # last obs on/before 2026-08-30 is 08-28
    assert r["3M"] == pytest.approx(132 / 100 - 1)       # last obs on/before 2026-06-30 is 2025-12-31
    assert r["YTD"] == pytest.approx(132 / 100 - 1)
    assert pd.isna(r["1Y"])                              # history shorter than a year


def test_period_returns_uses_each_series_own_last_date():
    a = pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2026-09-28", "2026-09-29", "2026-09-30"]))
    b = pd.Series([10.0, 20.0], index=pd.to_datetime(["2026-09-28", "2026-09-29"]))
    r = A.period_returns(pd.DataFrame({"a": a, "b": b}))
    assert r.loc["a", "as_of"] == pd.Timestamp("2026-09-30")
    assert r.loc["b", "as_of"] == pd.Timestamp("2026-09-29")
    assert r.loc["b", "1D"] == pytest.approx(1.0)


def test_summary_stats_cagr_and_drawdown():
    idx = pd.to_datetime(["2020-01-01", "2021-01-01", "2022-01-01"])
    st = A.summary_stats(pd.Series([100.0, 200.0, 100.0], index=idx))
    assert st["max_drawdown"] == pytest.approx(-0.5)
    assert st["cagr"] == pytest.approx(0.0, abs=1e-3)
    assert st["n_obs"] == 3


def test_rebase_starts_at_100_on_common_date():
    a = series([10, 20, 40], start="2020-01-01")         # Wed, Thu, Fri
    b = series([5, 10], start="2020-01-02")              # Thu, Fri: starts a day later
    out = A.rebase(pd.concat({"a": a, "b": b}, axis=1))
    assert out.iloc[0].tolist() == [100.0, 100.0]
    assert out.index[0] == pd.Timestamp("2020-01-02")
    assert out.iloc[-1].tolist() == [200.0, 200.0]


# ---------------------------------------------------------------- Layer 2

def test_rolling_corr_extremes():
    rng = np.random.default_rng(3)
    x = series(rng.normal(size=300))
    assert A.rolling_corr(x, x, 60).dropna().round(9).eq(1.0).all()
    assert A.rolling_corr(x, -x, 60).dropna().round(9).eq(-1.0).all()


def test_rolling_corr_uses_pairwise_intersection_not_fill():
    rng = np.random.default_rng(4)
    x = series(rng.normal(size=200))
    y = x.copy()
    y.iloc[50:60] = np.nan                                # a gap in one series
    rc = A.rolling_corr(x, y, 30)
    # no forward-fill: dates inside the gap are absent from the result entirely
    assert not rc.index.isin(x.index[50:60]).any()


def test_lead_lag_finds_planted_lead():
    rng = np.random.default_rng(5)
    x = series(rng.normal(size=3000))
    y = x.shift(2)                                        # y_t = x_{t-2}: x leads y by 2
    ll = A.lead_lag(x, y, lags=range(-4, 5))
    assert ll["corr"].idxmax() == 2
    assert ll.loc[2, "corr"] == pytest.approx(1.0, abs=1e-9)
    assert ll.loc[0, "corr"] == pytest.approx(0.0, abs=0.1)


def test_lead_lag_sign_convention_reversed():
    rng = np.random.default_rng(6)
    x = series(rng.normal(size=3000))
    y = x.shift(-3)                                       # y_t = x_{t+3}: x LAGS y by 3
    assert A.lead_lag(x, y, lags=range(-5, 6))["corr"].idxmax() == -3


def test_lead_lag_band_shrinks_with_n():
    rng = np.random.default_rng(7)
    small = A.lead_lag(series(rng.normal(size=100)), series(rng.normal(size=100)), [0])
    big = A.lead_lag(series(rng.normal(size=10000)), series(rng.normal(size=10000)), [0])
    assert big.loc[0, "band"] < small.loc[0, "band"]
    assert small.loc[0, "band"] == pytest.approx(1.96 / 10, rel=1e-6)


def test_regime_labels_quantile_cuts():
    lv = series(range(1, 101))
    lab = A.regime_labels(lv, 0.5, 0.9)
    assert (lab == "stress").sum() == 11 or (lab == "stress").sum() == 10
    assert lab.iloc[0] == "calm" and lab.iloc[-1] == "stress" and lab.iloc[70] == "elevated"
    assert list(lab.cat.categories) == ["calm", "elevated", "stress"]


def test_corr_by_regime_recovers_planted_structure():
    """Correlation 0.1 on calm days, 0.9 on stress days — conditional matrices must show it."""
    rng = np.random.default_rng(8)
    n = 6000
    regime = pd.Series(np.where(np.arange(n) % 2 == 0, "calm", "stress"),
                       index=pd.date_range("2000-01-03", periods=n, freq="B"))
    z1, z2 = rng.normal(size=n), rng.normal(size=n)
    rho = np.where(regime == "calm", 0.1, 0.9)
    r = pd.DataFrame({"a": z1, "b": rho * z1 + np.sqrt(1 - rho**2) * z2}, index=regime.index)
    cat = pd.Series(pd.Categorical(regime, categories=["calm", "stress"], ordered=True), index=regime.index)
    out = A.corr_by_regime(r, cat, lag_regime=False)
    assert out["calm"].loc["a", "b"] == pytest.approx(0.1, abs=0.06)
    assert out["stress"].loc["a", "b"] == pytest.approx(0.9, abs=0.04)


def test_corr_by_regime_lag_uses_previous_close():
    """With lagging, a day is classified by the day before; the first day has no label."""
    idx = pd.date_range("2020-01-01", periods=6, freq="B")
    cat = pd.Series(pd.Categorical(["calm", "calm", "stress", "stress", "calm", "calm"],
                                   categories=["calm", "stress"], ordered=True), index=idx)
    r = pd.DataFrame({"a": np.arange(6.0), "b": np.arange(6.0) ** 2}, index=idx)
    out = A.corr_by_regime(r, cat, lag_regime=True, min_obs=1)
    # stress-labelled-by-prior-day days are idx[3] and idx[4]
    assert out["stress"].loc["a", "b"] == pytest.approx(1.0)
    assert not (out["stress"].shape == (0, 0))


# ------------------------------------------------------------------ flows

def test_nsdl_shift_to_previous_trading_day():
    trading = pd.to_datetime(["2026-09-24", "2026-09-25", "2026-09-28", "2026-09-29"])   # Fri then Mon
    flow = pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2026-09-25", "2026-09-28", "2026-09-29"]))
    out = A.nsdl_to_trade_date(flow, trading)
    assert out.index.tolist() == pd.to_datetime(["2026-09-24", "2026-09-25", "2026-09-28"]).tolist()
    assert out.tolist() == [1.0, 2.0, 3.0]


def test_nsdl_shift_over_weekend_and_holiday_sums_collisions():
    # Reporting dates Wed 9/30 and Thu 10/1; Wed is a market holiday, so BOTH describe Tue 9/29.
    trading = pd.to_datetime(["2026-09-28", "2026-09-29", "2026-10-02"])
    flow = pd.Series([5.0, 7.0], index=pd.to_datetime(["2026-09-30", "2026-10-01"]))
    out = A.nsdl_to_trade_date(flow, trading)
    assert out.loc["2026-09-29"] == 12.0
    assert out.sum() == flow.sum()                        # cumulative flow preserved exactly


def test_nsdl_shift_drops_rows_before_first_trading_day():
    trading = pd.to_datetime(["2026-09-29", "2026-09-30"])
    flow = pd.Series([1.0, 2.0], index=pd.to_datetime(["2026-09-29", "2026-09-30"]))
    out = A.nsdl_to_trade_date(flow, trading)
    assert out.index.tolist() == [pd.Timestamp("2026-09-29")] and out.tolist() == [2.0]
