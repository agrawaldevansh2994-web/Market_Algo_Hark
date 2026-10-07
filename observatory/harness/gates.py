"""Regime, sensitivity and capacity checks, and the gate report (gates 6–9).

The report is the harness's output: one row per gate from research/01 §3.6,
each PASS / FAIL / NOT RUN with the number behind it. NOT RUN is a legitimate
state and is never rendered as a pass.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import stats
from .backtest import ann_sharpe, cagr, max_drawdown

TRADING_DAYS = 252

# Structurally distinct Indian-equity regimes. Boundaries are descriptive
# conventions chosen before any strategy was run (2026-10-07), not fitted.
INDIA_REGIMES = {
    "GFC crash (Jan 2008 – Mar 2009)": ("2008-01-01", "2009-03-31"),
    "Recovery & taper (Apr 2009 – Dec 2013)": ("2009-04-01", "2013-12-31"),
    "Long bull (2014 – Jan 2020)": ("2014-01-01", "2020-01-31"),
    "COVID crash (Feb – May 2020)": ("2020-02-01", "2020-05-31"),
    "Post-COVID bull (Jun 2020 – Sep 2024)": ("2020-06-01", "2024-09-30"),
    "Oct 2024 → now (FPI selling, STT hikes)": ("2024-10-01", "2099-12-31"),
}


def regime_table(returns: dict[str, pd.Series], regimes: dict = INDIA_REGIMES) -> pd.DataFrame:
    """Annualised return, Sharpe and max drawdown of each series inside each regime."""
    rows = []
    for name, (a, b) in regimes.items():
        row = {"regime": name}
        for label, r in returns.items():
            seg = r.loc[a:b].dropna()
            if len(seg) < 20:
                row[f"{label} CAGR"] = np.nan
                row[f"{label} Sharpe"] = np.nan
                row[f"{label} MaxDD"] = np.nan
                continue
            row[f"{label} CAGR"] = cagr(seg)
            row[f"{label} Sharpe"] = ann_sharpe(seg)
            row[f"{label} MaxDD"] = max_drawdown(seg)
        rows.append(row)
    return pd.DataFrame(rows).set_index("regime")


def sensitivity(metric_by_param: pd.Series, min_ratio: float = 0.8) -> dict:
    """Does performance degrade gracefully around the chosen parameter?

    neighbour_ratio = worst adjacent parameter's metric ÷ the best metric.
    A chosen point whose neighbours keep ≥ 80% of its performance sits on a
    plateau; below that it sits on a peak, and the peak is probably noise.
    Also reports the share of the grid with a positive metric.
    """
    s = metric_by_param.sort_index().dropna()
    if len(s) < 3 or s.max() <= 0:
        return {"neighbour_ratio": float("nan"), "share_positive": float((s > 0).mean()) if len(s) else float("nan"),
                "best_param": s.idxmax() if len(s) else None, "ok": False if len(s) >= 3 else None}
    best_pos = int(np.argmax(s.values))
    nbrs = [s.iloc[j] for j in (best_pos - 1, best_pos + 1) if 0 <= j < len(s)]
    ratio = float(min(nbrs) / s.iloc[best_pos])
    return {"neighbour_ratio": ratio, "share_positive": float((s > 0).mean()),
            "best_param": s.index[best_pos], "ok": bool(ratio >= min_ratio)}


def capacity_sqrt_law(gross_edge_ann: float, statutory_ann: float, annual_turnover: float,
                      adv_value: float, daily_vol: float, impact_k: float = 0.7) -> float:
    """AUM at which √-law impact consumes the whole edge left after statutory costs.

    Per unit traded, impact = k·σ·√(q/ADV); with q ≈ AUM × turnover-per-trade,
    annual impact drag ≈ turnover × k·σ·√(AUM·τ/ADV) where τ is the fraction of
    AUM traded per rebalance (approximated as 1 here — conservative). Solve
    drag = edge for AUM. Returns 0 when nothing is left after statutory costs.
    """
    edge = gross_edge_ann - statutory_ann
    if edge <= 0 or annual_turnover <= 0:
        return 0.0
    per = edge / (annual_turnover * impact_k * daily_vol)
    return float(per**2 * adv_value)


@dataclass
class Gate:
    n: int
    name: str
    status: str   # PASS / FAIL / NOT RUN / INFO
    detail: str


def gate_report(gates: list[Gate]) -> pd.DataFrame:
    return pd.DataFrame([g.__dict__ for g in gates]).set_index("n")


def to_markdown(df: pd.DataFrame, floatfmt: str = ".3f") -> str:
    """Small dependency-free markdown table (tabulate is not in requirements)."""
    cols = [df.index.name or ""] + list(df.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    for idx, row in df.iterrows():
        cells = [str(idx)]
        for v in row:
            if isinstance(v, float):
                cells.append("—" if math.isnan(v) else format(v, floatfmt))
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)
