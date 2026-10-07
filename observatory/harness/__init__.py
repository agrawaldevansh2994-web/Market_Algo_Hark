"""Validation harness — roadmap step ④ (research/04 §6).

Every strategy result in this project passes through here. The modules map to
the 12 ordered gates of research/01 §3.6:

    costs.py     gate 4   date-stamped Indian cost stack + √-law impact
    backtest.py  gate 4   thin vectorised daily backtester, ≥1-bar lag enforced
    splits.py    gate 5   walk-forward, purged k-fold with embargo, CPCV
    stats.py     gates 5, 9   PSR, DSR, MinTRL, Harvey-Liu haircut, PBO (CSCV)
    trials.py    gates 2, 3, 10   pre-registration, append-only trial log, sealed holdout
    gates.py     gates 6, 7, 8   regimes, parameter sensitivity, capacity, the report

Nothing here chooses a strategy. It only decides how much a result should be
believed.
"""
