"""Build the data spine: fetch raw snapshots, then write curated panels.

    python build.py            fetch fresh + rebuild panels
    python build.py --no-fetch rebuild panels from the latest existing snapshot
"""

from __future__ import annotations

import sys

from obs import panel as P
from obs.fetch import fetch_all
from obs.flows import flows_panel
from obs.registry import load_registry
from obs.store import write_curated


def main(fetch: bool = True) -> int:
    reg = load_registry()
    print(f"registry: {len(reg)} instruments "
          f"({len(reg.fetchable())} fetchable, {len(reg.derived())} derived, "
          f"{len(reg.unresolved())} unresolved)\n")

    if fetch:
        written, failed = fetch_all(reg)
        print(f"fetched {len(written)} instruments")
        for key, err in failed.items():
            print(f"  FAILED {key}: {err}")
        if failed:
            print()

    daily = P.close_panel(reg)
    weekly = P.to_weekly(daily)

    write_curated("close_daily", daily)
    write_curated("close_weekly", weekly)
    write_curated("logret_daily", P.log_returns(daily))
    write_curated("logret_weekly", P.log_returns(weekly))

    # Flows are levels, not prices: their own panel, never log-returned.
    # Their data arrives via capture.py, not this build.
    try:
        flows = flows_panel()
        write_curated("flows_daily", flows)
        print("flows: " + ", ".join(
            f"{c} {flows[c].first_valid_index().date()}→{flows[c].last_valid_index().date()}"
            for c in flows.columns) + "\n")
    except FileNotFoundError as exc:
        print(f"flows: skipped — {exc}\n")

    cov = P.coverage(daily)
    print(cov.to_string())

    subjects = [i.key for i in reg.values()
                if i.role == "subject" and i.key in daily.columns]
    start, end = P.common_window(daily, subjects)
    print(f"\ncommon window across subjects: {start.date()} -> {end.date()}")
    print(f"daily rows {len(daily)}, weekly rows {len(weekly)}")

    unresolved = reg.unresolved()
    if unresolved:
        print(f"\nunresolved sources ({len(unresolved)}) — scope §6:")
        for i in unresolved:
            print(f"  {i.key:16} {i.name}  [blocks {', '.join(i.answers)}]")

    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main(fetch="--no-fetch" not in sys.argv))
