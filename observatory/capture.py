"""Nightly capture of daily-published series — schedule after ~20:00 IST.

    python capture.py              latest NSE FII/DII + recent months of the rest
    python capture.py --backfill   also fill every missing month of history

NSE's FII/DII endpoint serves only the latest trade date, so a missed night
loses that day's DII figure permanently. NSDL and participant OI come from
persistent archives, so recent months are rescanned and gaps heal themselves.
Each run appends to data/capture.log. Exit code is non-zero if anything failed.
"""

from __future__ import annotations

import datetime as dt
import sys

import pandas as pd

from obs.flows import NSDL_START, capture_fiidii, update_nsdl
from obs.fno import POI_START, update_participant_oi
from obs.store import DATA_ROOT
from obs.universe import backfill_wayback, capture_constituents

LOG = DATA_ROOT / "capture.log"
CATCHUP_BUDGET = 600  # archive requests per day spent on old participant-OI history


def log(msg: str) -> None:
    line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def main(backfill: bool = False) -> int:
    log("capture start")  # a run killed mid-way (machine slept) must still leave a trace
    failures = 0
    try:
        log(capture_fiidii())
    except Exception as exc:
        failures += 1
        log(f"FII/DII: FAILED {type(exc).__name__}: {exc}")

    try:
        failures += capture_constituents(log=log)
    except Exception as exc:
        failures += 1
        log(f"constituents: FAILED {type(exc).__name__}: {exc}")

    if backfill:
        failures += backfill_wayback(log=log)

    recent = str(pd.Period(dt.date.today(), "M") - 1)
    failures += update_nsdl(start=NSDL_START if backfill else recent, log=log)
    try:
        failures += update_participant_oi(start=POI_START if backfill else recent, log=log)
        # Once a day (the late run), spend part of the archive host's request
        # allowance on filling older history. Resumes where the last run stopped.
        if not backfill and dt.datetime.now().hour >= 22:
            failures += update_participant_oi(start=POI_START, pause=1.0, log=log, budget=CATCHUP_BUDGET)
    except Exception as exc:  # e.g. NSE session refused
        failures += 1
        log(f"participant OI: FAILED {type(exc).__name__}: {exc}")

    log(f"done, {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    # Under Task Scheduler stdout is redirected and defaults to cp1252; one
    # stray non-cp1252 character in a log line must not kill a capture run.
    # Under pythonw.exe (the scheduled task, no console window) stdout is None.
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main(backfill="--backfill" in sys.argv))
