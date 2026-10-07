"""Tests for the validation harness (step ④).

The statistics are checked against independent computations — simulation for
E[max SR] and PSR coverage, brute force for purging — rather than against
re-typed copies of the same formula.
"""

import math

import numpy as np
import pandas as pd
import pytest

from harness import backtest as bt
from harness import splits, stats
from harness.costs import CostModel
from harness.trials import HoldoutSeal, TrialLog

RNG = np.random.default_rng(7)


def _prices(n=600, k=2, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2019-01-01", periods=n)
    r = rng.normal(0.0004, 0.01, size=(n, k))
    return pd.DataFrame(100 * np.cumprod(1 + r, axis=0), idx, [f"A{i}" for i in range(k)])


# ------------------------------------------------------------------ costs

def test_stt_schedule_is_date_stamped():
    f = CostModel("futures")
    assert f.at("2023-03-31").stt_sell == pytest.approx(0.0001)
    assert f.at("2023-04-01").stt_sell == pytest.approx(0.000125)
    assert f.at("2024-10-01").stt_sell == pytest.approx(0.0002)
    assert f.at("2026-04-01").stt_sell == pytest.approx(0.0005)
    o = CostModel("options")
    assert o.at("2026-04-01").stt_sell == pytest.approx(0.0015)


def test_delivery_round_trip_matches_hand_calc():
    s = CostModel("delivery").at("2026-10-07")
    fees = (0.0000307 + 1e-6) * 1.18
    assert s.round_trip == pytest.approx(0.001 + 0.001 + 0.00015 + 2 * fees)


def test_vectorised_rates_match_scalar():
    m = CostModel("futures")
    d = pd.DatetimeIndex(["2022-01-03", "2023-04-03", "2024-10-01", "2026-05-04"])
    v = m.statutory_rates(d)
    for day in d:
        assert v.loc[day, "sell"] == pytest.approx(m.at(day).per_side("sell"))


# --------------------------------------------------------------- backtest

def test_lag_zero_is_refused():
    p = _prices()
    with pytest.raises(ValueError):
        bt.run(p, pd.DataFrame(0.5, index=p.index[:1], columns=p.columns), lag=0)


def test_buy_and_hold_equals_asset_minus_one_buy():
    p = _prices(k=1)
    tgt = pd.DataFrame({"A0": [1.0]}, index=p.index[:1])
    res = bt.run(p, tgt, CostModel("delivery", spread_bps=0), lag=1)
    asset = p["A0"].pct_change().iloc[2:]
    held = res.gross.iloc[2:]
    np.testing.assert_allclose(held.values, asset.values, rtol=1e-10, atol=1e-12)
    assert res.costs.sum(axis=1).iloc[1] == pytest.approx(CostModel("delivery").at(p.index[1]).per_side("buy"))
    assert res.turnover.sum() == pytest.approx(0.5)


def test_no_lookahead_future_prices_do_not_change_past():
    p = _prices()
    tgt = pd.DataFrame(np.where(p.pct_change(20) > 0, 1.0, 0.0) / p.shape[1], p.index, p.columns)
    a = bt.run(p, tgt).net
    p2 = p.copy()
    p2.iloc[400:] *= 1.5
    tgt2 = pd.DataFrame(np.where(p2.pct_change(20) > 0, 1.0, 0.0) / p.shape[1], p.index, p.columns)
    b = bt.run(p2, tgt2).net
    pd.testing.assert_series_equal(a.iloc[:400], b.iloc[:400])


def test_after_tax_never_exceeds_pre_tax():
    r = pd.Series(RNG.normal(0.0006, 0.01, 1500), pd.bdate_range("2017-01-02", periods=1500))
    t = bt.after_tax(r)
    assert ((1 + t).prod()) <= ((1 + r).prod()) + 1e-12


# ------------------------------------------------------------------ stats

def test_expected_max_sharpe_matches_simulation():
    n_trials, v = 50, 0.01
    sim = RNG.normal(0, math.sqrt(v), size=(20000, n_trials)).max(axis=1).mean()
    assert stats.expected_max_sharpe(n_trials, v) == pytest.approx(sim, rel=0.03)


def test_psr_is_calibrated_under_the_null():
    # with true SR = 0, PSR(0) should be ~uniform → about 5% above 0.95
    hits = [stats.psr(RNG.normal(0, 0.01, 500)) > 0.95 for _ in range(2000)]
    assert 0.03 < np.mean(hits) < 0.07


def test_min_track_record_hits_target_confidence():
    r = RNG.normal(0.001, 0.01, 3000)
    n_star = stats.min_track_record(r, confidence=0.95)
    # PSR on exactly n_star obs with the same moments should be ~0.95
    sr = stats.sharpe(r)
    n, g3, g4 = stats._moments(r)
    z = sr * math.sqrt(n_star - 1) / math.sqrt(stats._sr_se_term(sr, g3, g4))
    assert z == pytest.approx(1.6449, rel=1e-3)


def test_dsr_falls_as_trials_rise():
    r = RNG.normal(0.0006, 0.01, 1500)
    d10 = stats.dsr(r, 10, var_sr=0.0004)["dsr"]
    d1000 = stats.dsr(r, 1000, var_sr=0.0004)["dsr"]
    assert d1000 < d10


def test_pbo_is_high_for_noise_low_for_real_edge():
    idx = pd.bdate_range("2015-01-01", periods=2000)
    # a single noise draw can land anywhere; averaged over draws PBO ≈ 0.5
    vals = [stats.pbo(pd.DataFrame(RNG.normal(0, 0.01, (2000, 10)), idx), n_blocks=8)["pbo"] for _ in range(30)]
    assert 0.4 < np.mean(vals) < 0.6
    noise = pd.DataFrame(RNG.normal(0, 0.01, (2000, 20)), idx)
    edge = noise.copy()
    edge[0] += 0.002
    assert stats.pbo(edge, n_blocks=10)["pbo"] < 0.1


def test_haircut_grows_with_tests():
    a = stats.haircut_sharpe(1.0, 10, 1)
    b = stats.haircut_sharpe(1.0, 10, 100)
    assert b["haircut_sr_ann"] < a["haircut_sr_ann"] == pytest.approx(1.0)


# ----------------------------------------------------------------- splits

def test_purged_kfold_has_no_label_overlap():
    idx = pd.bdate_range("2020-01-01", periods=300)
    h = 10
    for tr, te in splits.purged_kfold(idx, k=5, horizon=h, embargo_pct=0.02):
        for i in tr:
            span = set(range(i, min(i + h, 299) + 1))
            assert not span & set(te), "train label overlaps test"


def test_cpcv_count_and_disjoint():
    idx = pd.bdate_range("2020-01-01", periods=240)
    out = list(splits.cpcv(idx, n_groups=6, k_test=2, horizon=5))
    assert len(out) == 15
    for tr, te, _ in out:
        assert not set(tr) & set(te)


def test_walk_forward_is_sequential():
    for tr, te in splits.walk_forward(100, train=50, test=10):
        assert tr.max() < te.min()


# ----------------------------------------------------------------- trials

def test_trial_log_enforces_registration_and_one_unlock(tmp_path):
    log = TrialLog(tmp_path / "log.jsonl")
    with pytest.raises(ValueError):
        log.record("x", {}, {}, "2010-01-01", "2015-01-01")
    log.register("x", "h", "+", {"a": [1]}, holdout_start="2020-01-01", universe="u")
    with pytest.raises(ValueError):
        log.register("x", "h", "+", {"a": [1]}, holdout_start="2020-01-01", universe="u")
    log.record("x", {"a": 1}, {"sr": 1.0}, "2010-01-01", "2019-12-31")
    with pytest.raises(ValueError):
        log.record("x", {"a": 1}, {"sr": 1.0}, "2010-01-01", "2021-01-01")
    seal = HoldoutSeal("x", log)
    s = pd.Series(1.0, pd.bdate_range("2019-12-25", periods=10))
    assert seal.dev(s).index.max() < pd.Timestamp("2020-01-01")
    seal.unlock(s, "final test", {"a": 1})
    with pytest.raises(PermissionError):
        seal.unlock(s, "again", {"a": 2})
    assert log.n_trials("x") == 1


def test_cpcv_matches_skfolio_oracle():
    """Oracle check (research/04 §3): our purge/embargo vs skfolio's implementation."""
    skf = pytest.importorskip("skfolio.model_selection")
    n = 240
    idx = pd.bdate_range("2020-01-01", periods=n)
    for h, e in [(5, 0.0), (5, 0.05), (0, 0.03), (12, 0.02)]:
        emb = int(round(n * e))
        ref = skf.CombinatorialPurgedCV(n_folds=6, n_test_folds=2, purged_size=h, embargo_size=emb)
        ours = list(splits.cpcv(idx, 6, 2, horizon=h, embargo_pct=e))
        theirs = list(ref.split(np.zeros((n, 1))))
        assert len(ours) == len(theirs)
        for (tr_a, _), (tr_b, _, _) in zip(theirs, ours):
            assert set(tr_a) == set(tr_b)


def test_sensitivity_flags_isolated_peak_not_plateau():
    from harness.gates import sensitivity
    plateau = pd.Series([0.5, 0.6, 0.62, 0.6, 0.55], index=[1, 2, 3, 4, 5])
    peak = pd.Series([0.1, 0.1, 0.8, 0.1, 0.1], index=[1, 2, 3, 4, 5])
    assert sensitivity(plateau)["ok"] is True
    assert sensitivity(peak)["ok"] is False
