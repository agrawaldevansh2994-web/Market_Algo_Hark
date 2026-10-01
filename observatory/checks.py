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
import pandas as pd

from obs.flows import INVEST_KEY, NSE_KEY, SUBTOTAL_ROUTES
from obs.fno import IMBALANCE_TOL, PARTICIPANTS, POI_KEY, POI_PAIRS
from obs.registry import load_registry
from obs.store import RAW, read_curated, read_partitions
from obs.universe import INDEX_FILES, members_at, store_key

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


# Observed max 0.20 cr over 4,053 days — rounding. A parse error is hundreds of crore.
NSDL_TOTAL_TOL = 0.5
# NSDL reporting date D covers trades to D-1 (research/02 §4.8). Measured: the
# prior-day correlation beats the same-row one by 0.155-0.40 in every era.
NSDL_PREV_DAY_MARGIN = 0.10
# Long weekends plus a missed run still fit; a week of nothing means capture broke.
STALE_DAYS = 7


def check_flows(daily) -> list[str]:
    """Flow data against identities and conventions its sources imply."""
    failures = []
    print("\nflows (scope §4.8)")

    try:
        inv = read_partitions(INVEST_KEY)
    except FileNotFoundError:
        inv = None
        print("  SKIP  no NSDL data")
    if inv is not None:
        tot = inv[inv["route"] == "Total"].groupby(level=0)["net"].sum()
        leaf = inv[~inv["route"].isin(SUBTOTAL_ROUTES)].groupby(level=0)["net"].sum()
        gap = (leaf.reindex(tot.index) - tot).abs().max()
        ok = gap <= NSDL_TOTAL_TOL
        print(f"  {'ok  ' if ok else 'FAIL'}  NSDL leaf rows vs daily Total   max gap {gap:.2f} cr "
              f"over {len(tot)} days (limit {NSDL_TOTAL_TOL})")
        if not ok:
            failures.append(f"NSDL leaves miss daily Total by {gap:.2f} cr")

        age = (pd.Timestamp.today().normalize() - inv.index.max()).days
        ok = age <= STALE_DAYS
        print(f"  {'ok  ' if ok else 'FAIL'}  NSDL freshness                 newest {inv.index.max().date()} "
              f"({age} days old, limit {STALE_DAYS})")
        if not ok:
            failures.append(f"NSDL data stale: {age} days")

        flows = read_curated("flows_daily")
        f = flows["fpi_equity_exch_nsdl"].dropna()
        nifty = daily["nifty50"].dropna()
        x = f.to_frame("f").join(nifty.shift(1).rename("prev"), how="inner").join(
            nifty.rename("same"), how="inner").dropna()
        prev, same = x["f"].corr(x["prev"]), x["f"].corr(x["same"])
        ok = prev - same >= NSDL_PREV_DAY_MARGIN
        print(f"  {'ok  ' if ok else 'FAIL'}  NSDL date convention (T+1)     vs Nifty prior day "
              f"{prev:+.3f}, same row {same:+.3f}  n={len(x)}")
        if not ok:
            failures.append(f"NSDL no longer aligns to the prior trading day ({prev:+.3f} vs {same:+.3f})")

    try:
        cash = read_partitions(NSE_KEY)
    except FileNotFoundError:
        cash = None
        print("  SKIP  no FII/DII captures yet")
    if cash is not None:
        # The endpoint is latest-day-only, so a missed capture is permanent.
        # Nifty's own trading calendar says which days should exist.
        have = set(cash.index.normalize())
        expected = daily["nifty50"].dropna().loc[cash.index.min():cash.index.max()].index
        lost = [d.date().isoformat() for d in expected if d not in have]
        if lost:
            print(f"  warn  FII/DII captures missing for Nifty trading days {lost} — "
                  "permanent (source serves the latest day only); FPI side recoverable from NSDL")
        else:
            print(f"  ok    FII/DII capture gap-free since {cash.index.min().date()}")
        age = (pd.Timestamp.today().normalize() - cash.index.max()).days
        ok = age <= STALE_DAYS
        print(f"  {'ok  ' if ok else 'FAIL'}  FII/DII capture freshness      newest {cash.index.max().date()} "
              f"({age} days old, limit {STALE_DAYS})")
        if not ok:
            failures.append(f"FII/DII capture stale: {age} days — is the scheduled task running?")
        for tag in ("fii", "dii"):
            resid = (cash[f"{tag}_buy"] - cash[f"{tag}_sell"] - cash[f"{tag}_net"]).abs()
            for source, r in resid.groupby(cash["source"]):
                bad = r[r > 0.05]
                if bad.empty:
                    print(f"  ok    {tag.upper()} buy - sell = net  [{source}]  {len(r)} day(s)")
                elif source == "nse":
                    print(f"  FAIL  {tag.upper()} buy - sell != net  [nse]  {len(bad)} day(s)")
                    failures.append(f"NSE {tag.upper()} components inconsistent on {len(bad)} day(s)")
                else:  # known fallback defect; net is what analysis uses
                    print(f"  warn  {tag.upper()} buy - sell != net  [{source}] on "
                          f"{[d.date().isoformat() for d in bad.index]} — trust net only")

    try:
        poi = read_partitions(POI_KEY)
    except FileNotFoundError:
        poi = None
        print("  SKIP  no participant OI yet")
    if poi is not None:
        sums = poi[poi["participant"].isin(PARTICIPANTS)].groupby(level=0).sum(numeric_only=True)
        worst, imbalanced = 0.0, 0
        for long_col, short_col in POI_PAIRS:
            diff = (sums[long_col] - sums[short_col]).abs()
            imbalanced += int((diff > 0).sum())
            worst = max(worst, (diff / sums[long_col].clip(lower=1)).max())
        ok = worst <= IMBALANCE_TOL
        print(f"  {'ok  ' if ok else 'FAIL'}  participant OI longs = shorts   worst {worst:.2e} of column "
              f"(limit {IMBALANCE_TOL}); {imbalanced} column-days off by any amount, "
              f"{sums.index.nunique()} days")
        if not ok:
            failures.append(f"participant OI long/short imbalance {worst:.2e}")
    return failures


def check_universe() -> list[str]:
    """Index definitions imply set identities between the constituent lists."""
    failures = []
    print("\nindex constituents (research/04 §7)")
    try:
        got = {i: members_at(i, "2099-01-01") for i in INDEX_FILES}
    except LookupError:
        print("  SKIP  no constituent snapshots yet")
        return failures
    sym = {i: set(df["symbol"]) for i, (df, _) in got.items()}
    dates = {i: d for i, (_, d) in got.items()}

    identities = [
        ("Nifty 100 = Nifty 50 + Next 50", sym["nifty100"], sym["nifty50"] | sym["niftynext50"]),
        ("Nifty 200 = Nifty 100 + Midcap 100", sym["nifty200"], sym["nifty100"] | sym["niftymidcap100"]),
    ]
    for name, left, right in identities:
        ok = left == right
        print(f"  {'ok  ' if ok else 'FAIL'}  {name}"
              + ("" if ok else f"   only-left {sorted(left - right)[:4]} only-right {sorted(right - left)[:4]}"))
        if not ok:
            failures.append(f"constituents: {name} violated")
    ok = sym["nifty200_momentum30"] <= sym["nifty200"]
    print(f"  {'ok  ' if ok else 'FAIL'}  Momentum 30 is a subset of Nifty 200")
    if not ok:
        failures.append("constituents: Momentum 30 not inside Nifty 200")

    print(f"  info  latest snapshots {min(dates.values())} to {max(dates.values())}; "
          f"{len(list((RAW / store_key('nifty200')).glob('*.parquet')))} Nifty 200 snapshots on file")
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
                + check_no_filled_gaps(daily)
                + check_flows(daily)
                + check_universe())
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
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
