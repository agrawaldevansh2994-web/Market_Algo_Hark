"""Paper engine for the Momentum 30 replica. PAPER ONLY: no broker, no real money.

Ledger, whole-share orders to target weights, fills at the next session's open,
cost 0.1% per side (an ESTIMATE, not the harness.costs schedule).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

COST_PER_SIDE = 0.001  # estimate


@dataclass
class Book:
    cash: float
    pos: dict = field(default_factory=dict)     # symbol -> shares (int)
    ledger: list = field(default_factory=list)  # (date, symbol, side, qty, price, cost)

    def value(self, px: dict) -> float:
        return self.cash + sum(q * px[s] for s, q in self.pos.items())


def target_from_selection(csv: Path, review: str | None = None) -> dict:
    """Weights from a committed reports/mom30/selections/<year>.csv (latest review by default)."""
    df = pd.read_csv(csv)
    review = review or df["review"].max()
    w = df[df["review"] == review].set_index("symbol")["weight_tilt"]
    return (w / w.sum()).to_dict()


def orders_for(book: Book, target: dict, ref_px: dict) -> list:
    """Whole-share orders to reach target weights at reference prices. Sells come first."""
    nav = book.value({s: ref_px[s] for s in set(book.pos) | set(target)})
    out = []
    for s in sorted(set(book.pos) | set(target)):
        want = math.floor(target[s] * nav * (1 - 2 * COST_PER_SIDE) / ref_px[s]) if s in target else 0
        d = want - book.pos.get(s, 0)
        if d:
            out.append((s, d))
    return sorted(out, key=lambda x: x[1] > 0)


def execute(book: Book, orders: list, open_px: dict, date: str, cost: float = COST_PER_SIDE) -> float:
    """Fill at the next-session open. Buys are scaled down if cash is short. Returns the total cost paid."""
    paid = 0.0
    for s, d in orders:
        if d < 0:
            px = open_px[s]
            q = min(-d, book.pos.get(s, 0)); c = q * px * cost
            book.cash += q * px - c; book.pos[s] = book.pos.get(s, 0) - q
            if book.pos[s] == 0:
                del book.pos[s]
            book.ledger.append((date, s, "SELL", q, px, c)); paid += c
    for s, d in orders:
        if d > 0:
            px = open_px[s]; q = d
            while q > 0 and q * px * (1 + cost) > book.cash:
                q -= 1
            if q <= 0:
                continue
            c = q * px * cost; book.cash -= q * px + c
            book.pos[s] = book.pos.get(s, 0) + q
            book.ledger.append((date, s, "BUY", q, px, c)); paid += c
    return paid


def turnover(orders: list, px: dict, nav: float) -> float:
    """One-way turnover of an order list."""
    return sum(abs(d) * px[s] for s, d in orders) / 2 / nav
