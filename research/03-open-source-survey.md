# Open-Source Survey — What to Adopt, What to Build

*Survey run 2026-08-13. Resolves `CLAUDE.md` §5.6 (build vs adopt) per-layer rather than globally. All health metrics queried from the GitHub API on 2026-08-13, not taken from blog posts or memory — re-check before relying on them.*

---

## 1. The question this answers

`CLAUDE.md` §5.6 asks: hand-rolled research stack, or adopt NautilusTrader / QuantConnect LEAN early?

**Framed globally, that question has no good answer.** The four layers of §4.1 have completely different build-vs-adopt economics, and one of them (the validation harness) has an answer that inverts the usual logic. So the survey resolves it layer by layer.

The second question, which turned out to matter more: **does anything open-source close the three Indian data gaps** in `research/02` §6? Answer: no. Section 5.

---

## 2. Verdict by layer

| Layer | Verdict | Why |
|---|---|---|
| **0 — Data spine** | ✅ **Keep what's built** | Already done, 530 lines, shaped to the question bank. No framework would have produced the §4.5 FX finding — that came from bespoke integrity checks |
| **Validation harness** (§6.3) | ⚠️ **Adopt as oracle, implement the core** | See §4. The crux of this survey |
| **Backtest engine** | ⏸️ **Defer — do not choose yet** | Nothing to backtest. The choice forks on open decisions §5.1/§5.3 |
| **Portfolio construction** | ⏸️ **Defer** | `skfolio` or `Riskfolio-Lib` when there is something to size |
| **Execution / live** | ⛔ **Out of scope** | Adopting a live-trading platform now *is* the scope drift `research/02` §4.4 warns about |
| **India data** | 🔨 **Build small fetchers** | Nothing open-source covers it — §5 |

---

## 3. The landscape, measured

Health as of **2026-08-13**. "Push" is last commit to default branch — the single best staleness tell.

### 3.1 Full frameworks

| Project | Stars | Last push | License | Read |
|---|---|---|---|---|
| [microsoft/qlib](https://github.com/microsoft/qlib) | 47.3k | 2026-07-23 | MIT | AI/ML-first quant platform. Nested backtesting, point-in-time data handling. Heaviest conceptual fit with §6.3, heaviest to learn |
| [nautechsystems/nautilus_trader](https://github.com/nautechsystems/nautilus_trader) | 25.5k | 2026-08-12 | LGPL-3.0 | Rust core, event-driven, backtest and live on identical code paths. Genuinely production-grade. Built for the layer we have explicitly deferred |
| [QuantConnect/Lean](https://github.com/QuantConnect/Lean) | 21.2k | 2026-08-12 | Apache-2.0 | Mature, huge asset coverage, cloud-coupled. Same objection as Nautilus |
| [kernc/backtesting.py](https://github.com/kernc/backtesting.py) | 8.8k | 2026-08-05 | **AGPL-3.0** | Small and readable. AGPL — see §6 |
| [polakowo/vectorbt](https://github.com/polakowo/vectorbt) | 8.7k | 2026-08-02 | Apache + Commons Clause | Fast vectorised sweeps. **The speed is the hazard** — see §4.3 |

### 3.2 Dead or effectively dead — the tutorial trap

These are still the most-recommended names in tutorials and YouTube. All are stale:

| Project | Stars | Last push | Status |
|---|---|---|---|
| [mementum/backtrader](https://github.com/mementum/backtrader) | 22.8k | **2024-08-19** | Unmaintained ~2 years. Still the #1 tutorial recommendation |
| [quantopian/zipline](https://github.com/quantopian/zipline) | 20.0k | **2024-02-13** | Dead with Quantopian; use [zipline-reloaded](https://github.com/stefan-jansen/zipline-reloaded) (1.9k★, 2026-01-06) |
| [quantopian/pyfolio](https://github.com/quantopian/pyfolio) | 6.4k | **2023-12-23** | → [pyfolio-reloaded](https://github.com/stefan-jansen/pyfolio-reloaded) |
| [quantopian/alphalens](https://github.com/quantopian/alphalens) | 4.4k | **2024-02-12** | → [alphalens-reloaded](https://github.com/stefan-jansen/alphalens-reloaded) |
| [hudson-and-thames/mlfinlab](https://github.com/hudson-and-thames/mlfinlab) | 4.9k | **2023-10-02** | **Relicensed closed/commercial.** See §4.1 |

**Star count is a lagging indicator of quality and a useless indicator of maintenance.** backtrader has more stars than every actively-maintained option except qlib and Nautilus.

### 3.3 Analytics and portfolio construction — safe to adopt when needed

| Project | Stars | Last push | License |
|---|---|---|---|
| [PyPortfolioOpt](https://github.com/PyPortfolio/PyPortfolioOpt) | 6.0k | 2026-07-07 | MIT |
| [quantstats](https://github.com/ranaroussi/quantstats) | 7.5k | 2026-07-20 | Apache-2.0 |
| [Riskfolio-Lib](https://github.com/dcajasn/Riskfolio-Lib) | 4.4k | 2026-06-22 | BSD-3 |
| [skfolio](https://github.com/skfolio/skfolio) | 2.1k | 2026-07-31 | BSD-3 |
| [ffn](https://github.com/pmorissette/ffn) / [bt](https://github.com/pmorissette/bt) | 2.6k / 3.0k | 2026-08-12 / 2026-08-07 | MIT |

`skfolio` is the standout: sklearn-native, actively maintained, BSD-3, and **it ships Combinatorial Purged CV and walk-forward CV** — but it is scoped to portfolio optimisation, not backtesting.

---

## 4. The crux: the validation harness

This is where the survey found something that changes the plan.

### 4.1 The canonical implementation is gone

`mlfinlab` was *the* reference implementation of López de Prado's machinery — purged k-fold, embargo, CPCV, DSR, PBO. It was **relicensed as a paid closed-source product**; the GitHub repo has not moved since October 2023. Its sibling `arbitragelab` (686★) is likewise frozen at 2024-05.

The obvious free fallback, [timeseriescv](https://github.com/sam31415/timeseriescv) (289★), has had **no release since 2018**, last commit 2022-02, and carries reported correctness issues.

**So the thing `CLAUDE.md` §6.3 calls "the thing that makes every later result trustworthy" has no mature, maintained, free reference implementation.** That is a genuinely important finding and it was not visible before this survey.

### 4.2 What exists now

| Project | Stars | Created | Last push | License | Covers |
|---|---|---|---|---|---|
| [purged-cross-validation](https://github.com/eslazarev/purged-cross-validation) (`pip install purgedcv`) | **24** | **2026-05-15** | 2026-08-01 | MIT | Purge, embargo, `PurgedKFold`, `CombinatorialPurgedCV`, path reconstruction, PSR, **DSR**, minimum backtest length, **PBO** |
| [skfolio](https://github.com/skfolio/skfolio) | 2.1k | 2022 | 2026-07-31 | BSD-3 | CPCV + walk-forward, portfolio-scoped |
| [pypbo](https://github.com/esvhd/pypbo) | 137 | 2016 | 2026-07-06 | **AGPL-3.0** | PBO / CSCV only |

`purgedcv` covers the whole §6.3 surface in one MIT-licensed package, is on PyPI and conda-forge, has CI, a test suite and an accompanying JOSS paper. On paper it is exactly what this project needs.

**It is also 24 stars old and three months old.**

### 4.3 The recommendation, and why it is not "just pip install it"

Adopting a three-month-old, 24-star library *as the trust anchor for every result the project will ever produce* is self-undermining. The harness's whole purpose is that you can believe its verdicts; an unvetted dependency at that position just relocates the trust problem out of sight. Conversely, hand-writing DSR and PBO from the papers is exactly the kind of subtle-numerical-error work where a silent bug is invisible and flattering.

**Proposed resolution — use both, and require agreement:**

1. **Implement the closed-form statistics ourselves** — PSR, DSR, minimum backtest length, Harvey-Liu haircut. These are a few hundred lines of algebra straight from the papers, and writing them *is* the §1 learning goal ("learn how this is actually done"), not a detour from it.
2. **Install `purgedcv` (pinned) as an independent oracle.** Require our numbers and its numbers to agree to tolerance, in a test.
3. **Take CPCV splitting from a library** rather than writing it — the combinatorial path bookkeeping is fiddly and offers little learning value. Cross-check `purgedcv` against `skfolio`, which is independently written and far better established.
4. If the two disagree, that is a finding — record it the way `research/02` §4.5 was recorded.

This is the same principle `observatory/checks.py` already runs on: **assert a relationship whose answer is known in advance, from two independent directions.** It worked on the data layer; it should govern the harness layer too.

### 4.4 One trap worth naming

`vectorbt` can evaluate tens of thousands of parameter combinations in seconds. Under `CLAUDE.md` §4.2 and the Deflated Sharpe result — *with enough trials, no observed Sharpe is high enough to reject the null of no skill* — **that speed is a liability, not a feature.** Any tool that makes trials cheap must be paired with a trial counter that makes them costly. If vectorbt is ever adopted, DSR trial-counting is a precondition, not a follow-up.

---

## 5. India data — no library closes the gap

`research/02` §6 lists three open Indian data items. Checked directly:

| Need | Blocks | Best open-source option | Verdict |
|---|---|---|---|
| **FII/DII daily net flows** | E1, E2 | [nsepython](https://github.com/aeron7/nsepython) `nse_fiidii()` — 362★, GPL-3.0, push 2026-03-07 | ⚠️ **Latest day only, no history.** Solves the going-forward capture, not the backfill |
| **India 10Y G-Sec daily** | A4 | FRED [`INDIRLTLT01STM`](https://fred.stlouisfed.org/series/INDIRLTLT01STM) is **monthly** (OECD). CCIL is the daily source, no free API | ❌ **Open.** Daily needs CCIL/scraping |
| **Real MCX prices** | C5 | Nothing found | ❌ **Open** |
| NSE stock/index/F&O/bhavcopy | — | [jugaad-data](https://github.com/jugaad-py/jugaad-data) — 552★, push 2026-08-07, actively maintained, **public domain** | ✅ Good. *Update 2026-09-28: now needed — adopted for Phase 3 data expansion (`research/04` §3)* |

Also checked and rejected: [nsepy](https://github.com/swapniljariwala/nsepy) (805★, dead since 2023-12, 164 open issues), [pynse](https://github.com/raaghulr/pynse) (7★, dead 2021), [nse-tools](https://github.com/dhruvitdiyora/nse-tools) (3★, dead 2023, unlicensed).

**Operational consequence — this one is time-sensitive.** If FII/DII is available only as a latest-day endpoint, then **every day that passes without a snapshot is history that has to be backfilled from somewhere else later.** A tiny daily capture job has a cost that rises the longer it is deferred. That is an argument for doing it soon, and it is independent of every open decision in §5 — it does not commit the project to any market, strategy or horizon.

---

## 6. Licensing — matters more than it looks

The repo is private today. `CLAUDE.md` §3 treats commit history as the anti-data-snooping trial record, which is an argument it may one day be shown to someone.

| License | Projects | Implication |
|---|---|---|
| **MIT / BSD-3 / Apache-2.0** | purgedcv, skfolio, qlib, LEAN, PyPortfolioOpt, Riskfolio-Lib, quantstats | Clean. No constraint |
| **Public domain** | jugaad-data | Clean. GitHub's API reports "no license" because the file is a nonstandard `LICENSE.YOLO.md`; its text reads "jugaad-data is in public domain. Do whatever you want with it." *(checked 2026-09-28)* |
| **LGPL-3.0** | nautilus_trader | Fine as an imported dependency; do not vendor modified source |
| **GPL-3.0** | nsepython, backtrader | Fine to *use* privately. Copying code into this repo makes the repo GPL on distribution |
| **AGPL-3.0** | pypbo, backtesting.py | Strictest. Triggers on *network* use, not just distribution. Avoid vendoring |
| **Apache + Commons Clause** | vectorbt | Free to use, including commercially, for your own trading. Cannot sell it as a product. Not a constraint here |

**Rule for this project:** import via `requirements.txt`, never copy source into the repo. That keeps every option above safe and keeps the pinned-version provenance intact.

---

## 7. What this changes

1. **§5.6 is resolved** — per-layer, above. It was never one decision.
2. **§6.3 gets harder and more interesting.** The harness is not a pip install; the canonical implementation went commercial. Plan is §4.3: implement the statistics, adopt the splitters, cross-check the two.
3. **A new near-term action appears that blocks nothing:** start capturing FII/DII daily before more history is lost (§5).
4. **Do not choose a backtest engine yet.** Nothing to backtest; the choice forks on decisions not yet made; and every serious candidate pulls toward execution, which is out of scope.

---

## 8. Open items

| # | Item | Status |
|---|---|---|
| 1 | Read `purgedcv`'s DSR/PBO source before trusting it — 24★, 3 months old, unvetted by anyone | open |
| 2 | Confirm `skfolio` CPCV and `purgedcv` CPCV agree on a synthetic case | open |
| 3 | Backfill source for FII/DII history — NSE archives? Broker? | open |
| 4 | Daily G-Sec: CCIL scrape feasibility + terms of use | open |
| 5 | Re-run these health metrics before any adoption decision — they age | standing |

---

## 9. Log

| Date | Entry |
|---|---|
| 2026-08-13 | Survey run. ~35 repos health-checked via GitHub API. Key findings: `mlfinlab` (the canonical López de Prado implementation) has gone closed-source, leaving no mature free validation library — resolution is implement-plus-oracle (§4.3); no open-source project closes the three India data gaps, and FII/DII is latest-day-only so history is being lost daily (§5); backtrader/zipline/pyfolio/alphalens are all dead despite dominating tutorials (§3.2). Build-vs-adopt (`CLAUDE.md` §5.6) resolved per-layer. No code written, nothing adopted yet. |
| 2026-09-28 | §5.6 delegated to Claude and closed as recommended here, applied to the chosen direction in `research/04` §3. jugaad-data's license checked: public domain, not "none"; moved from "not needed" to adopted. |
</content>
