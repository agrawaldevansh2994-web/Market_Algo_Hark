"""Data integrity checks — run after every build.

The principle: assert relationships whose sign and rough magnitude are known
*before* looking at the data. A panel that is silently misaligned still
produces numbers; it does not produce numbers that pass these.

This file caught the yfinance `=X` FX defect recorded in scope §4.5. Add a
check here whenever a new source or derived series is introduced.

    python checks.py
"""

from __future__ import annotations

import sys

import numpy as np

from obs.registry import load_registry
from obs.store import read_curated

# (a, b, lower, upper, why) — bounds are deliberately wide. These catch
# broken alignment, not subtle changes in market structure.
EXPECTED = [
    ("nifty50", "niftybank", 0.75, 0.98, "same market, bank is the high-beta sector"),
    ("nifty50", "niftyit", 0.40, 0.85, "same market, different sector"),
    ("gold_usd", "silver_usd", 0.60, 0.92, "precious metals complex"),
    ("brent_usd", "wti_usd", 0.75, 0.99, "two quotes of the same barrel"),
    ("eurusd", "dxy", -0.95, -0.70, "EUR is ~58% of DXY, inverted"),
    ("nifty50", "indiavix", -0.75, -0.30, "vol spikes when equities fall"),
    ("sp500", "vix", -0.85, -0.55, "same, US"),
    ("usdinr", "dxy", 0.10, 0.60, "INR weakens as the dollar broadly strengthens"),
]


def _corr(df, a, b):
    x = df[[a, b]].dropna()
    return len(x), (x[a].corr(x[b]) if len(x) > 100 else float("nan"))


def check_known_relationships(daily) -> list[str]:
    failures = []
    print("known relationships (daily log returns)")
    for a, b, lo, hi, why in EXPECTED:
        if a not in daily.columns or b not in daily.columns:
            print(f"  SKIP  {a} / {b} — not in panel")
            continue
        n, r = _corr(daily, a, b)
        ok = lo <= r <= hi
        print(f"  {'ok  ' if ok else 'FAIL'}  {a:16} {b:16} r={r:+.3f}  "
              f"expect [{lo:+.2f},{hi:+.2f}]  n={n:5}  {why}")
        if not ok:
            failures.append(f"{a}/{b}: r={r:+.3f} outside [{lo:+.2f},{hi:+.2f}] — {why}")
    return failures


def check_derived_reconcile(daily) -> list[str]:
    """Synthetic INR series must equal USD x FX exactly in log space."""
    failures = []
    print("\nderived series reconciliation")
    for inst in load_registry().derived():
        cols = [inst.key, *inst.derived_from]
        if any(c not in daily.columns for c in cols):
            continue
        x = daily[cols].dropna()
        resid = (x[inst.key] - x[list(inst.derived_from)].sum(axis=1)).abs().max()
        ok = resid < 1e-10
        print(f"  {'ok  ' if ok else 'FAIL'}  {inst.key:18} max residual {resid:.2e}")
        if not ok:
            failures.append(f"{inst.key}: reconciliation residual {resid:.2e}")
    return failures


# The observatory's usable window opens with India VIX (Mar 2008). Zero-return
# checks are scoped to it deliberately: before 2005 the CNY was hard-pegged at
# 8.2765 and the RBI managed the rupee far more tightly, so ~30% and ~20%
# zero-return days respectively are the *correct* representation of those
# regimes, not a data fault. Scoped to the analysis window, the check fires on
# real bugs rather than on real history.
ANALYSIS_START = "2008-03-03"
ZERO_RETURN_LIMIT = 0.10


def check_no_filled_gaps(daily) -> list[str]:
    """Forward-filled prices show up as suspiciously many exact-zero returns."""
    failures = []
    print(f"\nzero-return share since {ANALYSIS_START} (fill tell; scope §4.3)")
    window = daily.loc[ANALYSIS_START:]
    for col in window.columns:
        s = window[col].dropna()
        if len(s) < 500:
            continue
        zeros = (s == 0).mean()
        if zeros > ZERO_RETURN_LIMIT:
            print(f"  FAIL  {col:18} {zeros:.1%} exact-zero returns")
            failures.append(f"{col}: {zeros:.1%} zero returns — check for filled gaps")
    if not failures:
        print(f"  ok    no series exceeds the {ZERO_RETURN_LIMIT:.0%} threshold")
    return failures


def check_session_contamination(daily) -> None:
    """Informational: how much same-day 'signal' is really the later US session."""
    print("\nsession contamination (scope §4.1) — informational, not a failure")
    reg = load_registry()
    for key in ("sp500", "dxy", "gold_usd"):
        if key not in daily.columns or "nifty50" not in daily.columns:
            continue
        x = daily[["nifty50", key]].dropna()
        same = x["nifty50"].corr(x[key])
        prev = x["nifty50"].corr(x[key].shift(1))
        nxt = x["nifty50"].corr(x[key].shift(-1))
        print(f"  nifty50 vs {key:10} same-day {same:+.3f}   prior-day {prev:+.3f}   "
              f"next-day {nxt:+.3f}   [{reg[key].session}]")


def main() -> int:
    daily = read_curated("logret_daily")
    weekly = read_curated("logret_weekly")
    print(f"panel: {daily.shape[1]} series, {len(daily)} daily rows, "
          f"{len(weekly)} weekly rows\n")

    failures = (check_known_relationships(daily)
                + check_derived_reconcile(daily)
                + check_no_filled_gaps(daily))
    check_session_contamination(daily)

    print()
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
