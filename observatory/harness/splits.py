"""Train/test splitters that respect time (gate 5).

Naive k-fold leaks on time series: a training row whose label window overlaps
the test window has already seen the test outcome. Purging drops those rows;
the embargo drops a buffer after each test window to cover serial correlation.
(López de Prado, AFML ch. 7; research/01 §3.2.)

All splitters yield integer positions into a sorted DatetimeIndex.
`label_end` maps each row to the last date its label depends on — for a
20-day forward return, label_end[t] = date at t+20.
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd


def walk_forward(n: int, train: int, test: int, step: int | None = None, expanding: bool = True):
    """Sequential splits. Expanding window by default; rolling if expanding=False."""
    step = step or test
    start = 0
    while train + start + test <= n:
        tr_end = train + start
        tr_start = 0 if expanding else start
        yield np.arange(tr_start, tr_end), np.arange(tr_end, tr_end + test)
        start += step


def _purge(train_idx: np.ndarray, test_idx: np.ndarray, label_end: np.ndarray, embargo: int, n: int):
    t0, t1 = test_idx.min(), test_idx.max()
    test_label_end = label_end[test_idx].max()
    keep = []
    for i in train_idx:
        # label of i overlaps the test span → leaks
        if i < t0 and label_end[i] >= t0:
            continue
        # starts inside the test labels' reach, or in the embargo that follows it
        # (AFML: the embargo is added to the end of the test labels' span)
        if t1 < i <= test_label_end + embargo:
            continue
        keep.append(i)
    return np.array(keep, dtype=int)


def _label_end_pos(index: pd.DatetimeIndex, label_end: pd.Series | None, horizon: int) -> np.ndarray:
    n = len(index)
    if label_end is None:
        return np.minimum(np.arange(n) + horizon, n - 1)
    pos = index.searchsorted(pd.DatetimeIndex(label_end.reindex(index).values), side="right") - 1
    return np.clip(pos, np.arange(n), n - 1)


def purged_kfold(index: pd.DatetimeIndex, k: int = 5, horizon: int = 0,
                 label_end: pd.Series | None = None, embargo_pct: float = 0.01):
    n = len(index)
    le = _label_end_pos(index, label_end, horizon)
    embargo = int(round(n * embargo_pct))
    folds = np.array_split(np.arange(n), k)
    for f in folds:
        train = np.setdiff1d(np.arange(n), f)
        yield _purge(train, f, le, embargo, n), f


def cpcv(index: pd.DatetimeIndex, n_groups: int = 6, k_test: int = 2, horizon: int = 0,
         label_end: pd.Series | None = None, embargo_pct: float = 0.01):
    """Combinatorial Purged CV: every choice of k_test groups as the test set.

    Yields (train_pos, test_pos, test_groups). C(n_groups, k_test) splits; each
    group appears in C(n_groups-1, k_test-1) test sets, which is the number of
    full backtest paths the splits can be stitched into.
    """
    n = len(index)
    le = _label_end_pos(index, label_end, horizon)
    embargo = int(round(n * embargo_pct))
    groups = np.array_split(np.arange(n), n_groups)
    for combo in itertools.combinations(range(n_groups), k_test):
        test = np.concatenate([groups[g] for g in combo])
        train = np.setdiff1d(np.arange(n), test)
        for g in combo:  # purge around each test group separately
            train = _purge(train, groups[g], le, embargo, n)
        yield train, test, combo
