"""Panel construction — alignment, derived series, returns, weekly resampling.

This module is where the scope §4 policies are enforced in code:

  §4.1  each instrument keeps its own local trading date; nothing is shifted
        to fake a common session. Weekly bars are the preferred cross-asset
        frequency because the session mismatch matters far less at that scale.
  §4.2  synthetic INR commodity series are built here and named `*_inr_synth`
        so they can never be mistaken for real MCX prices.
  §4.3  no forward-filling before returns. Missing days stay missing; pairwise
        analysis takes the intersection of the two series involved, never a
        global intersection across all instruments.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .registry import Registry, load_registry
from .store import latest_snapshot, read_raw

WEEKLY_RULE = "W-FRI"


def close_panel(registry: Registry | None = None, snapshot: str | None = None) -> pd.DataFrame:
    """Wide panel of daily closes: index = date, columns = instrument keys.

    The index is the union of all trading calendars, so gaps are explicit NaNs
    rather than silently filled values.
    """
    reg = registry or load_registry()
    series: dict[str, pd.Series] = {}

    for inst in reg.fetchable():
        if latest_snapshot(inst.key) is None:
            continue
        df = read_raw(inst.key, snapshot)
        series[inst.key] = df["Close"].rename(inst.key)

    if not series:
        raise FileNotFoundError("no raw snapshots found — run build.py first")

    panel = pd.concat(series.values(), axis=1).sort_index()
    panel.index.name = "date"
    return add_derived(panel, reg)


def add_derived(panel: pd.DataFrame, registry: Registry | None = None) -> pd.DataFrame:
    """Append derived series (currently the synthetic INR commodity prices).

    Synthetic INR = USD price x USDINR. The absolute level is in INR per COMEX
    contract unit, not the MCX quote convention (INR/10g) — irrelevant for
    return analysis, but it is why these must not be compared to MCX levels.
    """
    reg = registry or load_registry()
    panel = panel.copy()

    for inst in reg.derived():
        parts = [p for p in inst.derived_from if p in panel.columns]
        if len(parts) != len(inst.derived_from):
            continue  # an input is missing; skip rather than emit a partial series
        product = panel[parts[0]].copy()
        for p in parts[1:]:
            product = product * panel[p]
        panel[inst.key] = product

    return panel


def log_returns(panel: pd.DataFrame) -> pd.DataFrame:
    """Log returns, computed per column on that column's own observed days.

    Deliberately does not forward-fill: an injected zero-return day biases
    volatility down and correlation toward zero.
    """
    return np.log(panel.where(panel > 0)).diff()


def to_weekly(panel: pd.DataFrame, rule: str = WEEKLY_RULE) -> pd.DataFrame:
    """Last observation in each week. Preferred frequency for cross-asset work."""
    return panel.resample(rule).last().dropna(how="all")


def pairwise(panel: pd.DataFrame, a: str, b: str) -> pd.DataFrame:
    """Two series on their common trading days only — the §4.3 policy.

    A global dropna across 20+ instruments with different holiday calendars
    discards a large fraction of history; a pairwise intersection does not.
    """
    return panel[[a, b]].dropna()


def coverage(panel: pd.DataFrame) -> pd.DataFrame:
    """Per-instrument data coverage — first/last date, row count, gap count."""
    rows = []
    for col in panel.columns:
        s = panel[col].dropna()
        if s.empty:
            rows.append({"key": col, "rows": 0, "first": None, "last": None, "pct_of_span": 0.0})
            continue
        span = panel.loc[s.index[0]:s.index[-1]]
        rows.append({
            "key": col,
            "rows": len(s),
            "first": s.index[0].date(),
            "last": s.index[-1].date(),
            "pct_of_span": round(100 * len(s) / len(span), 1),
        })
    return pd.DataFrame(rows).set_index("key").sort_values("first")


def common_window(panel: pd.DataFrame, keys: list[str] | None = None) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Latest start and earliest end across the given keys — the usable window."""
    cols = keys or list(panel.columns)
    starts, ends = [], []
    for c in cols:
        s = panel[c].dropna()
        if not s.empty:
            starts.append(s.index[0])
            ends.append(s.index[-1])
    return max(starts), min(ends)
