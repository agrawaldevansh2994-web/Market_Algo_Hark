import datetime as dt

import pandas as pd
import pytest

from paper import corp as CP
from paper import run_paper as RP

LEDGER = pd.DataFrame([("2026-10-16", "A", "BUY", 13, 100.0, 1.3), ("2026-10-16", "B", "BUY", 10, 50.0, 0.5)],
                      columns=["date", "symbol", "side", "qty", "price", "cost"])


@pytest.mark.parametrize("purpose,atype,adj,expected", [
    ("Dividend - Rs 0.90 Per Share", "DIVIDEND", 1.0, [("dividend", 0.9)]),
    ("Interim Dividend - Re 1 Per Share", "DIVIDEND", 1.0, [("dividend", 1.0)]),
    ("Final Dividend - Rs 5 Per Share / Special Dividend - Rs 2.50 Per Share", "DIVIDEND", 1.0, [("dividend", 7.5)]),
    ("Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share", "SPLIT", 0.2, [("split", 0.2)]),
    ("Bonus 1:10", "BONUS", 0.9091, [("bonus", 10 / 11)]),
    ("Bonus 1:1/Dividend- Rs 7 Per Share", "BONUS", 0.5, [("bonus", 0.5), ("dividend", 7.0)]),
    ("Sub Division Of Equity Shares", "SPLIT", 0.5, [("split", 0.5)]),        # text unparsed: feed factor
    ("Annual General Meeting", "OTHER", 1.0, []),
])
def test_parse(purpose, atype, adj, expected):
    got = CP.parse(purpose, atype, adj)
    assert [k for k, _ in got] == [k for k, _ in expected]
    assert [v for _, v in got] == pytest.approx([v for _, v in expected])


def test_dividend_credit_uses_shares_held_before_ex():
    led = pd.concat([LEDGER, pd.DataFrame([("2026-10-20", "A", "BUY", 5, 100.0, 0.5)], columns=LEDGER.columns)])
    r = pd.Series(dict(symbol="A", ex_date="2026-10-20", kind="dividend", value=2.5))
    rows, dq, dc = CP.apply(r, led)                                  # the 5 bought on the ex-date don't qualify
    assert rows == [("2026-10-20", "A", "DIVIDEND", 13, 2.5, 0.0)] and dq == 0 and dc == 32.5


def test_split_and_bonus_scale_shares_and_pay_fractions():
    sp = pd.Series(dict(symbol="A", ex_date="2026-10-20", kind="split", value=0.2))
    assert CP.apply(sp, LEDGER, close=20.0)[1:] == (52, 0.0)          # 13 → 65
    bo = pd.Series(dict(symbol="A", ex_date="2026-10-20", kind="bonus", value=2 / 3))   # bonus 1:2
    rows, dq, dc = CP.apply(bo, LEDGER, close=66.0)                  # 13 → 19.5: 19 shares + 0.5 × 66 cash
    assert rows[0][2] == "BONUS" and dq == 6 and dc == 33.0
    after = pd.concat([LEDGER, pd.DataFrame(rows, columns=LEDGER.columns)])
    assert CP.held_on(after, "A", "2026-10-21") == 19
    assert CP.pending(pd.DataFrame([bo]), after, "2026-10-21").empty   # not applied twice


def test_mcp_down_keeps_cache_and_does_not_raise(tmp_path, monkeypatch):
    cache = tmp_path / "corp_actions.csv"
    pd.DataFrame([dict(symbol="A", ex_date="2026-10-20", kind="dividend", value=2.5, purpose="x")]).to_csv(cache, index=False)

    def down(*a, **k):
        raise ConnectionError("no route")
    monkeypatch.setattr(CP, "_Mcp", down)
    out = CP.refresh(cache, ["A", "B"], "2026-10-16", "2027-01-31", log=lambda *_: None)
    assert len(out) == 1 and pd.read_csv(cache)["value"].iloc[0] == 2.5

    class Flaky:                                                     # answers A, always errors on B
        def actions(self, sym, frm, to):
            if sym == "B":
                raise RuntimeError("500")
            return [dict(exDate="2026-11-05", actionType="DIVIDEND", purpose="Dividend - Rs 3 Per Share")]
    rows, failed = CP.fetch(["A", "B"], "2026-10-16", "2027-01-31", client=Flaky(), log=lambda *_: None)
    assert failed == ["B"] and rows["value"].tolist() == [3.0]


def test_runner_credits_late_dividend_and_split_keeps_nav_continuous(tmp_path, monkeypatch):
    LEDGER.to_csv(tmp_path / "ledger.csv", index=False)
    pd.DataFrame({"symbol": ["A", "B", "CASH"], "shares": [13.0, 10.0, 1000.0]}).to_csv(tmp_path / "positions.csv", index=False)
    pd.DataFrame([dict(date="2026-10-16", nav=2800.0, index_price=1.0, missing=None),
                  dict(date="2026-10-19", nav=2800.0, index_price=1.0, missing=None)]).to_csv(tmp_path / "daily.csv", index=False)
    pd.DataFrame([dict(symbol="A", ex_date="2026-10-19", kind="dividend", value=2.0, purpose=""),   # learned late
                  dict(symbol="B", ex_date="2026-10-20", kind="split", value=0.5, purpose="")]).to_csv(
        tmp_path / "corp_actions.csv", index=False)
    px = {"2026-10-16": {"A": 100.0, "B": 50.0}, "2026-10-19": {"A": 100.0, "B": 50.0},
          "2026-10-20": {"A": 100.0, "B": 25.0}}
    monkeypatch.setattr(RP, "STATE", tmp_path)
    monkeypatch.setattr(RP, "fetch_day", lambda d, s: pd.DataFrame(
        {"symbol": list(px[d.isoformat()]), "series": "EQ", "close": list(px[d.isoformat()].values())})
        if d.isoformat() in px else None)
    monkeypatch.setattr(RP, "index_close", lambda d, s: 1.0)
    RP.main(dt.date(2026, 10, 20), fetch_ca=False)
    daily = pd.read_csv(tmp_path / "daily.csv").set_index("date")["nav"]
    assert daily.to_dict() == {"2026-10-16": 2800.0, "2026-10-19": 2826.0, "2026-10-20": 2826.0}
    pos = pd.read_csv(tmp_path / "positions.csv").set_index("symbol")["shares"]
    assert pos["B"] == 20 and pos["CASH"] == 1026.0
    assert set(pd.read_csv(tmp_path / "ledger.csv")["side"]) == {"BUY", "DIVIDEND", "SPLIT"}
    RP.main(dt.date(2026, 10, 20), fetch_ca=False)                   # idempotent
    assert len(pd.read_csv(tmp_path / "ledger.csv")) == 4
