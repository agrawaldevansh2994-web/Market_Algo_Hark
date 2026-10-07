"""Date-stamped Indian transaction-cost model (gate 4).

Why date-stamped: STT changed in Apr 2023, Oct 2024 and Apr 2026. A backtest
over 2015–2026 must charge the rate in force on each trade date, while a
forward-looking evaluation must charge today's rate. `CostModel.at(date)`
returns the schedule in force; `CostModel.today()` the current one. Both are
reported (research/04 §6, step ④).

Sources
-------
* STT history: research/01 §5.2 (verified against ClearTax, HDFC Bank,
  1 Finance). Futures 0.01% → 0.0125% (1 Apr 2023) → 0.02% (1 Oct 2024)
  → 0.05% (1 Apr 2026). Options premium 0.05% → 0.0625% → 0.1% → 0.15%.
* Current exchange, SEBI, stamp, GST and brokerage: zerodha.com/charges,
  read 2026-10-07. NSE txn: equity 0.00307%, futures 0.00183%, options
  0.03553% of premium. SEBI ₹10/crore. Stamp (buy side, uniform since
  1 Jul 2020): delivery 0.015%, intraday 0.003%, futures 0.002%, options
  0.003%. GST 18% on brokerage + exchange + SEBI.
* ESTIMATE: exchange transaction charges and stamp duty before their current
  values are taken as today's rates. Together they are < 1.5 bp per side, so
  the error is small next to STT, but it is an approximation and is labelled.

All rates below are fractions of traded value (0.001 = 0.1% = 10 bp).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace
from typing import Literal

import numpy as np
import pandas as pd

Segment = Literal["delivery", "intraday", "futures", "options"]

# (effective_from, sell-side STT, buy-side STT) — options are on premium.
_STT = {
    "delivery": [(dt.date(2004, 10, 1), 0.001, 0.001)],
    "intraday": [(dt.date(2004, 10, 1), 0.00025, 0.0)],
    "futures": [
        (dt.date(2008, 6, 1), 0.0001, 0.0),
        (dt.date(2023, 4, 1), 0.000125, 0.0),
        (dt.date(2024, 10, 1), 0.0002, 0.0),
        (dt.date(2026, 4, 1), 0.0005, 0.0),
    ],
    "options": [
        (dt.date(2016, 6, 1), 0.0005, 0.0),
        (dt.date(2023, 4, 1), 0.000625, 0.0),
        (dt.date(2024, 10, 1), 0.001, 0.0),
        (dt.date(2026, 4, 1), 0.0015, 0.0),
    ],
}

_EXCHANGE = {"delivery": 0.0000307, "intraday": 0.0000307, "futures": 0.0000183, "options": 0.0003553}
_STAMP_BUY = {"delivery": 0.00015, "intraday": 0.00003, "futures": 0.00002, "options": 0.00003}
_SEBI = 10 / 1e7  # ₹10 per crore
_GST = 0.18


@dataclass(frozen=True)
class Schedule:
    """Cost rates in force on one date, for one segment."""

    segment: Segment
    as_of: dt.date
    stt_buy: float
    stt_sell: float
    exchange: float
    stamp_buy: float
    sebi: float
    brokerage: float  # fraction of value; 0 for Zerodha delivery
    gst: float = _GST

    def per_side(self, side: Literal["buy", "sell"]) -> float:
        """Statutory + broker cost of one side, as a fraction of traded value."""
        fees = self.exchange + self.sebi + self.brokerage
        stt = self.stt_buy if side == "buy" else self.stt_sell
        stamp = self.stamp_buy if side == "buy" else 0.0
        return stt + stamp + fees * (1 + self.gst)

    @property
    def round_trip(self) -> float:
        return self.per_side("buy") + self.per_side("sell")


@dataclass(frozen=True)
class CostModel:
    """Full cost of trading one segment: statutory stack + spread + impact.

    spread_bps   half-spread paid on every trade, in basis points. Default 2 bp
                 is an ESTIMATE for Nifty-50 ETFs / large caps; set it per
                 universe.
    impact_k     coefficient of the square-root law, impact = k·σ_daily·√(q/ADV)
                 (research/01 §3.3). 0.5–1.0 is the usual range in the
                 literature; default 0.7 is an ESTIMATE.
    brokerage    fraction of traded value. Default 0 (delivery at a discount
                 broker). For F&O use e.g. 0.0003 capped at ₹20/order.
    """

    segment: Segment = "delivery"
    spread_bps: float = 2.0
    impact_k: float = 0.7
    brokerage: float = 0.0

    def at(self, date) -> Schedule:
        d = pd.Timestamp(date).date()
        rows = [r for r in _STT[self.segment] if r[0] <= d] or [_STT[self.segment][0]]
        _, sell, buy = rows[-1]
        return Schedule(self.segment, d, buy, sell, _EXCHANGE[self.segment],
                        _STAMP_BUY[self.segment], _SEBI, self.brokerage)

    def today(self) -> Schedule:
        return self.at(dt.date.today())

    def with_(self, **kw) -> "CostModel":
        return replace(self, **kw)

    # ---------------------------------------------------------- vectorised
    def statutory_rates(self, dates: pd.DatetimeIndex, frozen_at=None) -> pd.DataFrame:
        """Per-date buy and sell rates. `frozen_at` charges one date's rates throughout."""
        if frozen_at is not None:
            s = self.at(frozen_at)
            return pd.DataFrame({"buy": s.per_side("buy"), "sell": s.per_side("sell")}, index=dates)
        bounds = [r[0] for r in _STT[self.segment]]
        scheds = [self.at(b) for b in bounds]
        idx = np.searchsorted(pd.DatetimeIndex(bounds).values, dates.values, side="right") - 1
        idx = np.clip(idx, 0, len(scheds) - 1)
        out = np.array([[scheds[i].per_side("buy"), scheds[i].per_side("sell")] for i in idx]).reshape(-1, 2)
        return pd.DataFrame(out, index=dates, columns=["buy", "sell"])

    def impact(self, trade_value: pd.DataFrame | float, adv_value, daily_vol) -> pd.DataFrame | float:
        """Square-root-law impact as a fraction of traded value.

        trade_value and adv_value in the same currency units; daily_vol as a
        fraction (0.012 = 1.2%/day). Returns 0 where ADV is unknown — callers
        that want impact must supply ADV; the report says when it was absent.
        """
        ratio = np.abs(trade_value) / adv_value
        return self.impact_k * daily_vol * np.sqrt(ratio)


def stt_history(segment: Segment) -> pd.DataFrame:
    """The STT schedule as a table — for the dashboard and the report."""
    return pd.DataFrame(_STT[segment], columns=["effective_from", "sell", "buy"])
