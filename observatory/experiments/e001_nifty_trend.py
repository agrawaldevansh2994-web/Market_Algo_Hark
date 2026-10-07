"""E001 — harness shakedown on the simplest documented strategy family.

NOT a strategy proposal. Its job is to push a known, boring idea through every
gate of the harness end-to-end so that each gate is exercised on real Indian
data before step ⑤ relies on it.

Pre-registered (see trials/log.jsonl, kind=register) before any result was seen:
  Hypothesis   Nifty 50 time-series trend: hold the index while it closes
               above its N-day simple moving average, else hold cash.
               Decisions only at month-end (low-turnover rule, research/04 §2).
  Expected     Lower drawdown than buy-and-hold; CAGR similar or lower.
               No expectation of a higher Sharpe — the trend literature's
               evidence is mostly diversified futures, not one equity index.
  Grid         N ∈ {50, 75, …, 250} — 9 trials. Plus one assumption check:
               the median N with cash earning 6%/yr (an ESTIMATE of a liquid
               fund yield) instead of 0.
  Costs        Delivery equity (a Nifty ETF), 2 bp half-spread (ESTIMATE),
               statutory stack date-stamped AND frozen at today's rates.
  Holdout      2024-10-01 onward is sealed and NOT unlocked by this script.

Data caveat: `nifty50` is the price index, so both legs miss dividends
(~1.2–1.5%/yr, ESTIMATE). It biases both against cash-free buy-and-hold
equally on held days; trend loses less of it when in cash.

Run from observatory/:  python experiments/e001_nifty_trend.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness import backtest as bt  # noqa: E402
from harness import gates, stats  # noqa: E402
from harness.costs import CostModel  # noqa: E402
from harness.gates import Gate  # noqa: E402
from harness.trials import HoldoutSeal, TrialLog  # noqa: E402
from obs.store import read_raw  # noqa: E402

EXP = "E001-nifty-trend-shakedown"
GRID = [50, 75, 100, 125, 150, 175, 200, 225, 250]
HOLDOUT = "2024-10-01"
OUT = ROOT / "reports" / "e001"


def signal(close: pd.Series, n: int) -> pd.DataFrame:
    """Month-end decisions only; uses data up to and including that close."""
    sma = close.rolling(n, min_periods=n).mean()
    on = (close > sma).astype(float).where(sma.notna())
    month_end = close.groupby(close.index.to_period("M")).tail(1).index
    return on.loc[month_end].dropna().to_frame(close.name)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    log = TrialLog()
    if log.registration(EXP) is None:
        log.register(
            EXP,
            hypothesis="Nifty 50 above its N-day SMA at month-end → hold index, else cash",
            expected_sign="drawdown lower than buy-and-hold; CAGR similar or lower; no Sharpe claim",
            param_grid={"sma_days": GRID, "assumption_check": "median N with cash at 6%/yr (estimate)"},
            holdout_start=HOLDOUT,
            universe="nifty50 price index (yfinance ^NSEI), daily close",
            notes="harness shakedown, not a strategy proposal",
        )
    seal = HoldoutSeal(EXP, log)
    already = log.n_trials(EXP)

    close = read_raw("nifty50")["Close"].rename("nifty50").dropna()
    dev = seal.dev(close)
    prices = dev.to_frame()
    cost = CostModel("delivery", spread_bps=2.0)

    bh_tgt = pd.DataFrame({"nifty50": [1.0]}, index=prices.index[:1])
    bh = bt.run(prices, bh_tgt, cost)

    # Every number is reported on one common window: from the first month-end
    # at which the longest SMA exists, so no trial (and not buy-and-hold) gets
    # credit or blame for a period the others sat out while warming up.
    start = signal(dev, max(GRID)).index[0]
    bh = bh.slice(start)
    results, nets = {}, {}
    for n in GRID:
        res = bt.run(prices, signal(dev, n).loc[start:], cost).slice(start)
        results[n] = res
        nets[n] = res.net
    nets = pd.DataFrame(nets)
    mid = GRID[len(GRID) // 2]
    cash6 = bt.run(prices, signal(dev, mid).loc[start:], cost, cash_rate=0.06).slice(start)

    # ---------------------------------------------------- log trials (once)
    if already == 0:
        for n, res in results.items():
            log.record(EXP, {"sma_days": n, "cash_rate": 0.0}, res.summary(),
                       str(start.date()), str(dev.index[-1].date()))
        log.record(EXP, {"sma_days": mid, "cash_rate": 0.06}, cash6.summary(),
                   str(start.date()), str(dev.index[-1].date()))
    n_trials = log.n_trials(EXP)

    # ---------------------------------------------------- selection + stats
    sr_daily = nets.apply(stats.sharpe)
    best = int(sr_daily.idxmax())
    best_res = results[best]
    r_best = nets[best]
    years = len(r_best) / 252
    d = stats.dsr(r_best, n_trials=n_trials, trial_sharpes=sr_daily.values)
    p = stats.pbo(nets, n_blocks=10)
    hc = stats.haircut_sharpe(stats.sharpe(r_best) * math.sqrt(252), years, n_trials)
    mintrl = stats.min_track_record(r_best)
    bh_win = bh.net
    mintrl_vs_bh = stats.min_track_record(r_best, sr_benchmark=stats.sharpe(bh_win))
    sens = gates.sensitivity(sr_daily * math.sqrt(252))
    today_res = bt.run(prices, signal(dev, best).loc[start:], cost, frozen_rates_at="2026-10-07").slice(start)
    tax = bt.after_tax(best_res.net, avg_holding_days=120)
    regimes = gates.regime_table({"Trend": best_res.net, "Buy&hold": bh.net})

    # ---------------------------------------------------- summary tables
    grid_tbl = pd.DataFrame({
        n: {"CAGR net": results[n].summary()["cagr_net"],
            "Sharpe net": results[n].summary()["sharpe_net"],
            "MaxDD": results[n].summary()["max_dd_net"],
            "Turnover/yr": results[n].annual_turnover,
            "Cost %/yr": results[n].annual_cost * 100}
        for n in GRID}).T
    grid_tbl.index.name = "SMA days"
    bh_s, be_s = bh.summary(), best_res.summary()
    head = pd.DataFrame({
        "Buy & hold": [bh_s["cagr_net"], bh_s["vol"], bh_s["sharpe_net"], bh_s["max_dd_net"], bh.annual_cost * 100],
        f"Trend SMA{best} (dated rates)": [be_s["cagr_net"], be_s["vol"], be_s["sharpe_net"], be_s["max_dd_net"], best_res.annual_cost * 100],
        f"Trend SMA{best} (today's rates)": [bt.cagr(today_res.net), today_res.summary()["vol"], bt.ann_sharpe(today_res.net), bt.max_drawdown(today_res.net), today_res.annual_cost * 100],
        f"Trend SMA{best} after tax (approx.)": [bt.cagr(tax), float(tax.std() * math.sqrt(252)), bt.ann_sharpe(tax), bt.max_drawdown(tax), float("nan")],
    }, index=["CAGR", "Volatility", "Sharpe", "Max drawdown", "Cost %/yr"])
    head.index.name = "Dev sample " + f"{start.date()} → {dev.index[-1].date()}"

    # ---------------------------------------------------- gates
    dd_better = be_s["max_dd_net"] > bh_s["max_dd_net"]
    g = [
        Gate(1, "Data integrity", "INFO", "Index level — no survivorship issue; price index excludes dividends (both legs)"),
        Gate(2, "Pre-registration", "PASS", f"Registered before results; {n_trials} trials logged"),
        Gate(3, "Sealed holdout", "PASS", f"{HOLDOUT} onward never touched"),
        Gate(4, "Cost-realistic", "PASS", f"Dated + today's STT; 2 bp spread (est.); lag 1 bar; {best_res.annual_cost*100:.2f}%/yr drag"),
        Gate(5, "Multiple testing", "PASS" if d["dsr"] >= 0.95 and p["pbo"] < 0.5 else "FAIL",
             f"DSR {d['dsr']:.2f} (need ≥0.95); PBO {p['pbo']:.0%}; t {hc['t_stat']:.2f} (need ≥3); haircut SR {hc['haircut_sr_ann']:.2f}"),
        Gate(6, "Regime stress", "INFO", "6 regimes reported separately (table)"),
        Gate(7, "Parameter sensitivity", "PASS" if sens["ok"] else "FAIL",
             f"Neighbours keep {sens['neighbour_ratio']:.0%} of best Sharpe (need ≥80%); Sharpe>0 in {sens['share_positive']:.0%} of grid"),
        Gate(8, "Capacity", "NOT RUN", "No ETF ADV series yet; an index ETF is not capacity-bound at personal scale"),
        Gate(9, "Min track record", "INFO",
             f"{mintrl/252:.1f} yrs to show SR>0; {('%.0f yrs' % (mintrl_vs_bh/252)) if math.isfinite(mintrl_vs_bh) else 'never'} to show it beats buy & hold"),
        Gate(10, "Unlock holdout", "NOT RUN", "Your call — once only"),
        Gate(11, "Staged live", "NOT RUN", "Needs your gate criteria"),
        Gate(12, "Decay monitoring", "NOT RUN", "Needs a live strategy"),
    ]
    gtbl = gates.gate_report(g)

    # ---------------------------------------------------- chart
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5), dpi=130)
    fig.suptitle(f"E001 · harness shakedown · Nifty 50 trend vs buy & hold · dev sample to {dev.index[-1].date()} (holdout sealed)",
                 fontsize=12, fontweight="bold", x=0.01, ha="left")
    ax = axes[0, 0]
    for lab, r, c in [("Buy & hold", bh.net, "#8a8f98"), (f"Trend SMA{best}, net", best_res.net, "#1f6feb"),
                      (f"Trend SMA{best}, after tax (approx.)", tax, "#d29922")]:
        ax.plot((1 + r).cumprod(), label=lab, color=c, lw=1.4)
    ax.set_yscale("log"); ax.set_title("Growth of ₹1 (log)", loc="left", fontsize=10); ax.legend(fontsize=8, frameon=False)
    ax = axes[0, 1]
    for lab, r, c in [("Buy & hold", bh.net, "#8a8f98"), (f"Trend SMA{best}", best_res.net, "#1f6feb")]:
        eq = (1 + r).cumprod(); ax.fill_between(eq.index, eq / eq.cummax() - 1, 0, color=c, alpha=0.45, label=lab)
    ax.set_title("Drawdown", loc="left", fontsize=10); ax.legend(fontsize=8, frameon=False)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax = axes[1, 0]
    bars = ax.bar([str(n) for n in GRID], sr_daily.values * math.sqrt(252), color=["#1f6feb" if n == best else "#9db8e8" for n in GRID])
    ax.axhline(stats.sharpe(bh_win) * math.sqrt(252), color="#8a8f98", ls="--", lw=1, label="Buy & hold")
    ax.axhline(d["sr0_ann"], color="#cf222e", ls=":", lw=1.2, label=f"Best-of-{n_trials} luck bar (SR₀)")
    ax.set_title("Sharpe by SMA length — all trials shown", loc="left", fontsize=10); ax.set_xlabel("SMA days")
    ax.legend(fontsize=8, frameon=True, loc="lower right", framealpha=0.95)
    ax = axes[1, 1]
    ax.hist(p["logits"], bins=25, color="#9db8e8", edgecolor="white")
    ax.axvline(0, color="#cf222e", lw=1.2)
    ax.set_title(f"PBO: in-sample winner's out-of-sample rank (logit) — PBO {p['pbo']:.0%}", loc="left", fontsize=10)
    ax.set_xlabel("← overfit (winner falls to bottom half)     generalises →")
    for a in axes.flat:
        a.spines[["top", "right"]].set_visible(False); a.tick_params(labelsize=8)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(OUT / "e001_overview.png")

    # ---------------------------------------------------- report
    fmt_head = head.copy()
    md = [f"# E001 — Nifty 50 trend · harness shakedown\n",
          f"*Generated by `experiments/e001_nifty_trend.py`. Dev sample {start.date()} → {dev.index[-1].date()} (common window after warm-up); holdout {HOLDOUT} → sealed.*\n",
          "## Gate report\n", gates.to_markdown(gtbl), "\n## Headline (dev sample)\n", gates.to_markdown(fmt_head),
          "\n## Every trial\n", gates.to_markdown(grid_tbl),
          "\n## Regimes\n", gates.to_markdown(regimes),
          "\n*GFC row is partial: the common window starts 2008-09-30, and the trend rule was in cash throughout it. "
          "The last row is the sealed holdout, so it is empty by design.*\n",
          "\n## Statistics\n", "```", json.dumps({"best_sma": best, "dsr": d["dsr"], "sr0_ann": d["sr0_ann"], "pbo": p["pbo"],
                                                    "pbo_splits": p["n_splits"], "haircut": {k: v for k, v in hc.items()},
                                                    "mintrl_years": mintrl / 252, "mintrl_vs_bh_years": mintrl_vs_bh / 252,
                                                    "sensitivity": {k: (v if not isinstance(v, (np.floating,)) else float(v)) for k, v in sens.items()},
                                                    "expected_vs_observed_drawdown": "lower" if dd_better else "NOT lower"},
                                                   indent=2, default=float), "```"]
    (OUT / "report.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
