"""Multiple-testing-aware performance statistics (gates 5 and 9).

Sharpe ratios here are **per-period** (daily) unless a name says `ann`. The
formulas are stated in per-period units in the papers and mixing the two is
the classic way to get a DSR that is silently wrong.

References
----------
* Bailey & López de Prado (2012), "The Sharpe Ratio Efficient Frontier" — PSR, MinTRL.
* Bailey & López de Prado (2014), "The Deflated Sharpe Ratio" — DSR, E[max SR].
* Bailey, Borwein, López de Prado & Zhu (2014/2017), "The Probability of
  Backtest Overfitting" — CSCV / PBO.
* Harvey & Liu (2015), "Backtesting" — haircut Sharpe. Only the Bonferroni
  variant is implemented: the most conservative of their three, and the one
  that needs no assumption about correlation between trials.
"""

from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd
from scipy import stats as st

EULER_GAMMA = 0.5772156649015329
TRADING_DAYS = 252


def sharpe(r) -> float:
    r = np.asarray(pd.Series(r).dropna(), dtype=float)
    sd = r.std(ddof=1)
    return float(r.mean() / sd) if sd > 0 else float("nan")


def _moments(r):
    r = np.asarray(pd.Series(r).dropna(), dtype=float)
    return len(r), float(st.skew(r)), float(st.kurtosis(r, fisher=False))


def _sr_se_term(sr: float, skew: float, kurt: float) -> float:
    return 1 - skew * sr + (kurt - 1) / 4 * sr**2


def psr(r, sr_benchmark: float = 0.0) -> float:
    """Probabilistic Sharpe Ratio: P(true SR > benchmark), non-normality aware."""
    n, g3, g4 = _moments(r)
    sr = sharpe(r)
    denom = math.sqrt(max(_sr_se_term(sr, g3, g4), 1e-12))
    return float(st.norm.cdf((sr - sr_benchmark) * math.sqrt(n - 1) / denom))


def expected_max_sharpe(n_trials: int, var_sr: float) -> float:
    """E[max of n_trials Sharpe estimates] under the null of zero true skill."""
    if n_trials <= 1:
        return 0.0
    z1 = st.norm.ppf(1 - 1 / n_trials)
    z2 = st.norm.ppf(1 - 1 / (n_trials * math.e))
    return float(math.sqrt(var_sr) * ((1 - EULER_GAMMA) * z1 + EULER_GAMMA * z2))


def dsr(r, n_trials: int, trial_sharpes=None, var_sr: float | None = None) -> dict:
    """Deflated Sharpe Ratio.

    The benchmark is the Sharpe you would expect from the best of `n_trials`
    skill-less strategies. Its variance comes from the Sharpes of the trials
    actually run (`trial_sharpes`, per-period) — which is why the trial log
    matters: forget a trial and the DSR flatters you.
    """
    if var_sr is None:
        if trial_sharpes is None or len(trial_sharpes) < 2:
            raise ValueError("need the per-period Sharpes of the trials (or var_sr)")
        var_sr = float(np.var(np.asarray(trial_sharpes, dtype=float), ddof=1))
    sr0 = expected_max_sharpe(n_trials, var_sr)
    return {"dsr": psr(r, sr0), "sr0": sr0, "sr0_ann": sr0 * math.sqrt(TRADING_DAYS),
            "n_trials": n_trials, "var_sr": var_sr}


def min_track_record(r, sr_benchmark: float = 0.0, confidence: float = 0.95) -> float:
    """Minimum number of observations for PSR(benchmark) ≥ confidence.

    Returns inf when the observed Sharpe does not exceed the benchmark.
    """
    n, g3, g4 = _moments(r)
    sr = sharpe(r)
    if not sr > sr_benchmark:
        return float("inf")
    z = st.norm.ppf(confidence)
    return float(1 + _sr_se_term(sr, g3, g4) * (z / (sr - sr_benchmark)) ** 2)


def haircut_sharpe(sr_ann: float, years: float, n_tests: int) -> dict:
    """Harvey-Liu haircut Sharpe, Bonferroni adjustment.

    t = SR_ann·√years; the single-test p-value is inflated by the number of
    tests, then mapped back to the Sharpe that would give that p-value alone.
    """
    t = sr_ann * math.sqrt(years)
    p = 2 * (1 - st.norm.cdf(abs(t)))
    p_adj = min(1.0, p * max(n_tests, 1))
    t_adj = st.norm.ppf(1 - p_adj / 2) if p_adj < 1 else 0.0
    hsr = t_adj / math.sqrt(years) * np.sign(sr_ann)
    return {"t_stat": t, "p": p, "p_adj": p_adj, "haircut_sr_ann": float(hsr),
            "haircut_pct": float(1 - hsr / sr_ann) if sr_ann else float("nan"),
            "passes_t3": bool(t >= 3.0)}


def pbo(trial_returns: pd.DataFrame, n_blocks: int = 16, metric=sharpe) -> dict:
    """Probability of Backtest Overfitting by Combinatorially Symmetric CV.

    trial_returns: T × N matrix, one column per trial (configuration), the same
    dates for all. Splits time into `n_blocks` (even) contiguous blocks; for
    every choice of half the blocks as in-sample, picks the IS-best trial and
    records its relative rank out-of-sample. PBO = share of splits where the IS
    winner lands in the bottom half OOS (logit ≤ 0).

    Known weakness (research/01 §3.2): sensitive to n_blocks. Report it.
    """
    if n_blocks % 2:
        raise ValueError("n_blocks must be even")
    m = trial_returns.dropna(how="any").to_numpy()
    t, n = m.shape
    if n < 2:
        raise ValueError("PBO needs at least two trials")
    edges = np.linspace(0, t, n_blocks + 1).astype(int)
    blocks = [np.arange(edges[i], edges[i + 1]) for i in range(n_blocks)]
    logits, is_best_perf, oos_perf = [], [], []
    for combo in itertools.combinations(range(n_blocks), n_blocks // 2):
        is_idx = np.concatenate([blocks[b] for b in combo])
        oos_idx = np.concatenate([blocks[b] for b in range(n_blocks) if b not in combo])
        is_m = np.array([metric(m[is_idx, j]) for j in range(n)])
        oos_m = np.array([metric(m[oos_idx, j]) for j in range(n)])
        best = int(np.nanargmax(is_m))
        rank = st.rankdata(oos_m)[best]          # 1 = worst
        w = rank / (n + 1)
        logits.append(math.log(w / (1 - w)))
        is_best_perf.append(is_m[best])
        oos_perf.append(oos_m[best])
    logits = np.array(logits)
    slope = np.polyfit(is_best_perf, oos_perf, 1)[0] if len(set(is_best_perf)) > 1 else float("nan")
    return {"pbo": float((logits <= 0).mean()), "n_splits": len(logits), "n_blocks": n_blocks,
            "n_trials": n, "logits": logits, "degradation_slope": float(slope),
            "is_best": np.array(is_best_perf), "oos_of_best": np.array(oos_perf)}
