"""Fetch / update the NSE equity bhavcopy store (data/bhav/, gitignored).

    python build_bhav.py                 incremental, 2004 → yesterday
    python build_bhav.py 2015-01-01      from a later start
"""
import sys

from obs.bhavcopy import update

if __name__ == "__main__":
    n = update(sys.argv[1] if len(sys.argv) > 1 else "2004-01-01")
    print(f"done: {n:,} rows added")
