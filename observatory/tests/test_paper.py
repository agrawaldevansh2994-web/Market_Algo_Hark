from pathlib import Path

import pytest

from paper.engine import Book, execute, orders_for, target_from_selection, turnover

PX = {"A": 100.0, "B": 50.0, "C": 200.0}
HERE = Path(__file__).resolve().parents[1]


def test_initial_buy_weights_and_cost():
    b = Book(1_000_000); t = {"A": .5, "B": .3, "C": .2}
    paid = execute(b, orders_for(b, t, PX), PX, "d")
    assert all(abs(b.pos[k] * PX[k] / 1e6 - w) < .003 for k, w in t.items())
    assert paid == pytest.approx(1_000_000 * .001, rel=.01)
    assert b.cash >= 0 and b.value(PX) == pytest.approx(1_000_000 - paid)


def test_cash_never_negative_when_open_gaps_up():
    b = Book(1_000_000)
    execute(b, orders_for(b, {"A": 1.0}, PX), {"A": 103.0}, "d")
    assert b.cash >= 0


def test_rebalance_sells_dropped_name_first():
    b = Book(1_000_000); t = {"A": .5, "B": .5}
    execute(b, orders_for(b, t, PX), PX, "d")
    again = orders_for(b, t, PX)
    assert again == [] or turnover(again, PX, b.value(PX)) < .001
    o = orders_for(b, {"A": .5, "C": .5}, PX); execute(b, o, PX, "d2")
    assert "B" not in b.pos and "C" in b.pos and o[0][1] < 0


def test_latest_selection_weights():
    t = target_from_selection(HERE / "reports/mom30/selections/2026.csv")
    assert len(t) == 30 and sum(t.values()) == pytest.approx(1) and max(t.values()) <= .0501
