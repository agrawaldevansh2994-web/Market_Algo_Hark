"""Thin vectorised daily backtester (gate 4).

Design choices, all deliberate (research/04 §3):

* **Weights in, returns out.** A strategy is a DataFrame of *target* weights
  indexed by the date the decision was made (using data up to that close).
  Rows that are all-NaN mean "no rebalance". The backtester never sees a
  signal, so the signal layer cannot leak into sizing (research/01 §1.1).
* **Lag is enforced, not optional.** A decision at close t is executed at close
  t+lag, with lag ≥ 1. It then earns returns from t+lag to t+lag+1 onward.
  `lag=0` raises.
* **Weights drift** between rebalances, so turnover is measured against what is
  actually held, not against yesterday's target.
* **Costs are charged on the execution date** using the schedule in force that
  day (or today's schedule, for the forward-looking number). Spread and
  √-law impact on top when ADV and volatility are supplied.
* **Net-of-tax** is an approximation, labelled as such: see `after_tax`.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .costs import CostModel

TRADING_DAYS = 252


@dataclass
class BacktestResult:
    gross: pd.Series            # daily portfolio return before any cost
    net: pd.Series              # after statutory + spread + impact costs
    costs: pd.DataFrame         # per-day cost by component, fraction of equity
    turnover: pd.Series         # one-way traded fraction of equity, per day
    weights: pd.DataFrame       # weights held over each day (post-trade, pre-drift)
    meta: dict = field(default_factory=dict)

    @property
    def annual_turnover(self) -> float:
        yrs = len(self.net) / TRADING_DAYS
        return float(self.turnover.sum() / yrs) if yrs else float("nan")

    @property
    def annual_cost(self) -> float:
        yrs = len(self.net) / TRADING_DAYS
        return float(self.costs.sum(axis=1).sum() / yrs) if yrs else float("nan")

    def slice(self, start=None, end=None) -> "BacktestResult":
        """The same run, reported over a sub-window (e.g. after every trial is warmed up)."""
        sl = slice(start, end)
        return BacktestResult(self.gross.loc[sl], self.net.loc[sl], self.costs.loc[sl],
                              self.turnover.loc[sl], self.weights.loc[sl], {**self.meta, "window": [str(start), str(end)]})

    def summary(self) -> dict:
        return {
            "start": str(self.net.index[0].date()),
            "end": str(self.net.index[-1].date()),
            "cagr_gross": cagr(self.gross),
            "cagr_net": cagr(self.net),
            "vol": float(self.net.std() * np.sqrt(TRADING_DAYS)),
            "sharpe_net": ann_sharpe(self.net),
            "max_dd_net": max_drawdown(self.net),
            "turnover_per_yr": self.annual_turnover,
            "cost_drag_per_yr": self.annual_cost,
        }


def run(
    prices: pd.DataFrame,
    target: pd.DataFrame,
    cost: CostModel | None = None,
    lag: int = 1,
    cash_rate: float = 0.0,
    adv_value: pd.DataFrame | None = None,
    capital: float = 1_000_000.0,
    frozen_rates_at=None,
) -> BacktestResult:
    """Simulate a target-weight strategy on daily closes.

    prices      wide close panel (index = trading dates, columns = assets)
    target      wide target-weight panel; index ⊆ prices.index; NaN row = hold
    lag         bars between decision and execution (≥ 1)
    cash_rate   annual return on uninvested cash (0 by default — conservative)
    adv_value   average daily traded value per asset, same units as `capital`;
                enables √-law impact. Without it impact is 0 and meta says so.
    frozen_rates_at  charge one date's statutory rates throughout (e.g. today)
    """
    if lag < 1:
        raise ValueError("lag must be ≥ 1: a decision at close t cannot trade at close t")
    cost = cost or CostModel()
    prices = prices.sort_index()
    cols = list(prices.columns)
    target = target.reindex(columns=cols)
    if not target.index.isin(prices.index).all():
        raise ValueError("target has dates not in the price calendar")

    rets = prices.pct_change(fill_method=None).fillna(0.0).to_numpy()
    dates = prices.index
    n, k = rets.shape

    # execution schedule: decision row at position p executes at p+lag
    exec_tgt = np.full((n, k), np.nan)
    pos = dates.get_indexer(target.index)
    rows = target.to_numpy()
    for p, row in zip(pos, rows):
        if np.isnan(row).all() or p + lag >= n:
            continue
        exec_tgt[p + lag] = np.nan_to_num(row)

    rates = cost.statutory_rates(dates, frozen_at=frozen_rates_at).to_numpy()
    vol = pd.DataFrame(rets, index=dates).rolling(63, min_periods=20).std().shift(1).bfill().to_numpy()
    adv = None if adv_value is None else adv_value.reindex(index=dates, columns=cols).shift(1).to_numpy()
    spread = cost.spread_bps / 1e4
    daily_cash = (1 + cash_rate) ** (1 / TRADING_DAYS) - 1

    w = np.zeros(k)
    equity = 1.0
    gross = np.zeros(n)
    net = np.zeros(n)
    c_stat = np.zeros(n)
    c_spread = np.zeros(n)
    c_impact = np.zeros(n)
    turn = np.zeros(n)
    held = np.zeros((n, k))

    for i in range(n):
        # 1) return over (i-1, i] on weights held since close i-1
        if i > 0:
            r = rets[i]
            port = float(w @ r) + (1 - w.sum()) * daily_cash
            gross[i] += port
            net[i] += port
            growth = 1 + port
            if growth > 0:
                w = w * (1 + r) / growth
            equity *= growth
        # 2) trade at close i if a decision executes today
        if not np.isnan(exec_tgt[i]).all():
            tgt = exec_tgt[i]
            trade = tgt - w
            buys, sells = np.clip(trade, 0, None), np.clip(-trade, 0, None)
            stat = float(buys.sum() * rates[i, 0] + sells.sum() * rates[i, 1])
            spr = float(np.abs(trade).sum() * spread)
            imp = 0.0
            if adv is not None:
                tv = np.abs(trade) * equity * capital
                with np.errstate(divide="ignore", invalid="ignore"):
                    per = cost.impact(tv, adv[i], vol[i])
                imp = float(np.nansum(np.abs(trade) * np.where(np.isfinite(per), per, 0.0)))
            total = stat + spr + imp
            c_stat[i], c_spread[i], c_impact[i] = stat, spr, imp
            net[i] = (1 + net[i]) * (1 - total) - 1
            equity *= 1 - total
            turn[i] = float(np.abs(trade).sum()) / 2
            w = tgt.copy()
        held[i] = w

    idx = dates
    res = BacktestResult(
        gross=pd.Series(gross, idx, name="gross"),
        net=pd.Series(net, idx, name="net"),
        costs=pd.DataFrame({"statutory": c_stat, "spread": c_spread, "impact": c_impact}, idx),
        turnover=pd.Series(turn, idx, name="turnover"),
        weights=pd.DataFrame(held, idx, cols),
        meta={
            "lag": lag,
            "segment": cost.segment,
            "spread_bps": cost.spread_bps,
            "impact": "sqrt-law" if adv_value is not None else "not modelled (no ADV supplied)",
            "rates": "frozen at " + str(frozen_rates_at) if frozen_rates_at else "date-stamped",
            "cash_rate": cash_rate,
        },
    )
    return res


# --------------------------------------------------------------- metrics

def cagr(r: pd.Series) -> float:
    r = r.dropna()
    if r.empty:
        return float("nan")
    total = float((1 + r).prod())
    yrs = len(r) / TRADING_DAYS
    return total ** (1 / yrs) - 1 if total > 0 else -1.0


def ann_sharpe(r: pd.Series, rf: float = 0.0) -> float:
    r = r.dropna() - rf / TRADING_DAYS
    sd = r.std()
    return float(r.mean() / sd * np.sqrt(TRADING_DAYS)) if sd > 0 else float("nan")


def max_drawdown(r: pd.Series) -> float:
    eq = (1 + r.fillna(0)).cumprod()
    return float((eq / eq.cummax() - 1).min())


# --------------------------------------------------------------- tax

def _fy(d: pd.Timestamp) -> int:
    """Indian financial year label: FY ending 31 Mar of the returned year."""
    return d.year + 1 if d.month >= 4 else d.year


def equity_tax_rates(fy_end_year: int) -> dict:
    """Listed-equity capital-gains rates (research/01 §5.4; Budget July 2024).

    The July 2024 change took effect mid-FY2025 (23 Jul 2024); this applies the
    new rates to the whole of FY2025 — an approximation, labelled.
    LTCG was exempt before FY2019 (s.10(38)).
    """
    if fy_end_year >= 2025:
        return {"stcg": 0.20, "ltcg": 0.125, "ltcg_exempt": 125_000}
    if fy_end_year >= 2019:
        return {"stcg": 0.15, "ltcg": 0.10, "ltcg_exempt": 100_000}
    return {"stcg": 0.15, "ltcg": 0.0, "ltcg_exempt": 0}


def after_tax(net: pd.Series, capital: float = 1_000_000.0, avg_holding_days: float = 180) -> pd.Series:
    """APPROXIMATE net-of-tax daily returns for a delivery-equity strategy.

    Approximation (stated, not hidden): each Indian FY's mark-to-market P&L is
    treated as realised in that year, taxed as STCG if the strategy's average
    holding period is under 365 days, else LTCG above the exemption. Losses are
    carried forward up to 8 years against later gains. Tax is debited on the
    last trading day of the FY. Surcharge and cess ignored. Good enough to show
    the order of magnitude; not a tax computation.
    """
    net = net.fillna(0.0)
    out = net.copy()
    equity = capital
    fy_start_equity = capital
    carry: list[tuple[int, float]] = []
    dates = net.index
    for i, d in enumerate(dates):
        equity *= 1 + net.iloc[i]
        last_of_fy = i == len(dates) - 1 or _fy(dates[i + 1]) != _fy(d)
        if not last_of_fy:
            continue
        fy = _fy(d)
        pnl = equity - fy_start_equity
        carry = [(y, l) for y, l in carry if fy - y <= 8]
        tax = 0.0
        if pnl > 0:
            for j, (y, l) in enumerate(carry):
                use = min(l, pnl)
                pnl -= use
                carry[j] = (y, l - use)
            carry = [(y, l) for y, l in carry if l > 0]
            rates = equity_tax_rates(fy)
            if avg_holding_days < 365:
                tax = pnl * rates["stcg"]
            else:
                tax = max(pnl - rates["ltcg_exempt"], 0.0) * rates["ltcg"]
        elif pnl < 0:
            carry.append((fy, -pnl))
        if tax > 0 and equity > 0:
            hit = tax / equity
            out.iloc[i] = (1 + out.iloc[i]) * (1 - hit) - 1
            equity -= tax
        fy_start_equity = equity
    return out.rename("after_tax")
