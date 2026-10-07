import numpy as np
import pandas as pd
import pytest

from obs import corpactions as CA
from obs import momentum as M


# ------------------------------------------------------------ corporate actions

@pytest.mark.parametrize("subject,expected", [
    ("Bonus 1:1", [("bonus", 0.5)]),
    ("Bonus 3:4", [("bonus", 4 / 7)]),
    ("Sch Of Agmt- Bonus Deb1:1", []),                       # bonus debentures: no price effect on equity
    ("Fv Split Rs.10 To Re.1", [("split", 0.1)]),
    ("Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share", [("split", 0.2)]),
    ("Bonus 1:1/Dividend- Rs 7 Per Share", [("bonus", 0.5), ("dividend", 7.0)]),
    ("Consolidation Of Shares From Rs 1 To Rs 10", [("consolidation", 10.0)]),
    ("Scheme Of Arrangement And Demerger", [("scheme", None)]),
    ("Int Div Re 0.50 Per Share", [("dividend", 0.5)]),
])
def test_parse_subject(subject, expected):
    got = CA.parse_subject(subject)
    assert [k for k, _ in got] == [k for k, _ in expected]
    for (_, v), (_, e) in zip(got, expected):
        assert (np.isnan(v) and e is None) or v == pytest.approx(e)


def _px(values, start="2024-01-01"):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


def test_audit_applies_confirmed_bonus_and_rejects_phantom():
    a = _px([100, 101, 50.5, 51, 52])                         # real 1:1 bonus on day 2
    b = _px([200, 202, 204, 203, 205])                        # "split" announced, market never moved
    close = pd.DataFrame({"A": a, "B": b})
    acts = pd.DataFrame({"cid": ["A", "B"], "ex_date": [a.index[2], b.index[2]],
                         "kind": ["bonus", "split"], "value": [0.5, 0.5], "subject": ["Bonus 1:1", "split"]})
    aud = CA.audit(close, close, acts).set_index("cid")
    assert aud.loc["A", "status"] == "applied"
    assert aud.loc["B", "status"] == "no_gap"
    adj = close * CA.adjustment_factors(close, aud.reset_index())
    assert adj["A"].iloc[1] == pytest.approx(50.5)            # pre-ex price halved
    assert (adj["B"] == close["B"]).all()                    # phantom action not applied


def test_audit_shifts_to_the_day_the_market_moved():
    a = _px([100, 100, 100, 20, 20, 20])                     # 1:4 split shows up a day late
    close = pd.DataFrame({"A": a})
    acts = pd.DataFrame({"cid": ["A"], "ex_date": [a.index[2]], "kind": ["split"], "value": [0.2], "subject": [""]})
    aud = CA.audit(close, close, acts)
    assert aud.loc[0, "status"] == "applied_shifted" and aud.loc[0, "applied_date"] == a.index[3]


def test_audit_lists_unannounced_gaps():
    close = pd.DataFrame({"A": _px([100, 100, 30, 30])})
    aud = CA.audit(close, close, pd.DataFrame(columns=["cid", "ex_date", "kind", "value", "subject"]))
    assert list(aud["status"]) == ["unexplained"]


def test_canonical_symbols_follow_renames_but_not_reuse():
    bh = pd.DataFrame({"symbol": ["ZOMATO", "ETERNAL", "OLD", "OLD"],
                       "date": pd.to_datetime(["2025-01-01", "2025-05-01", "2020-01-01", "2023-01-01"])})
    ch = pd.DataFrame({"old": ["ZOMATO", "OLD"], "new": ["ETERNAL", "NEW"],
                       "date": pd.to_datetime(["2025-04-09", "2021-01-01"])})
    assert list(CA.canonical_symbols(bh, ch)) == ["ETERNAL", "ETERNAL", "NEW", "OLD"]


# ------------------------------------------------------------------ momentum

def test_schedule_uses_month_before_review():
    idx = pd.bdate_range("2004-01-01", "2006-01-31")
    s = M.rebalance_schedule(idx)
    row = s[s["review"] == "2005-06"].iloc[0]
    assert row["cutoff"] == pd.Timestamp("2005-05-31")
    assert row["p13"] == pd.Timestamp("2004-05-31") and row["p7"] == pd.Timestamp("2004-11-30")
    assert row["effective"] == pd.Timestamp("2005-06-30")


def test_scores_follow_methodology_formula():
    idx = pd.bdate_range("2023-01-02", "2024-06-28")
    rng = np.random.default_rng(1)
    px = pd.DataFrame({c: 100 * np.exp(np.cumsum(rng.normal(mu, 0.003, len(idx))))
                       for c, mu in zip("ABCDE", [0.002, 0.001, 0, -0.001, -0.002])}, index=idx)
    s = M.rebalance_schedule(idx, first="2024-06").iloc[0]
    sc = M.momentum_scores(px, s["cutoff"], s["p7"], s["p13"], list("ABCDE"))
    assert list(sc.index) == list("ABCDE")                   # drift order recovered
    assert sc["z12"].mean() == pytest.approx(0, abs=1e-12)
    wz = sc["wz"]
    expect = np.where(wz >= 0, 1 + wz, 1 / (1 - wz))
    assert np.allclose(sc["score"], expect)
    r = sc.loc["A"]
    assert r["mr12"] == pytest.approx((px.loc[s["cutoff"], "A"] / px.loc[s["p13"], "A"] - 1) / r["sigma"])


def test_select_buffer_rules():
    names = [f"S{i:02d}" for i in range(1, 61)]
    sc = pd.DataFrame({"rank": range(1, 61)}, index=names)
    prev = names[30:60]                                       # previously held ranks 31–60
    chosen = M.select(sc, prev)
    assert len(chosen) == 30
    assert set(names[:15]) <= set(chosen)                     # top 15 forced in
    assert not set(names[45:]) & set(chosen)                  # held but ranked > 45: forced out
    assert set(names[30:45]) <= set(chosen)                   # held and within 45: kept


def test_capped_weights_respect_both_caps():
    size = pd.Series([50.0] + [1.0] * 29, index=[f"S{i}" for i in range(30)])
    score = pd.Series(1.0, index=size.index)
    w = M.capped_weights(score, size)
    base = size / size.sum()
    assert w.sum() == pytest.approx(1)
    assert (w <= np.minimum(0.05, 5 * base) + 1e-9).all()


def test_drifting_portfolio_matches_hand_calc():
    idx = pd.bdate_range("2024-01-01", periods=3)
    tr = pd.DataFrame({"A": [0, 0.10, 0.0], "B": [0, -0.10, 0.10]}, index=idx)
    r = M.drifting_portfolio(tr, {idx[0]: pd.Series({"A": 0.5, "B": 0.5})})
    assert r.iloc[0] == pytest.approx(0.0)
    # after day 1: A 0.55, B 0.45 → day 2 return = 0.45*0.10/1.0
    assert r.iloc[1] == pytest.approx(0.045)
