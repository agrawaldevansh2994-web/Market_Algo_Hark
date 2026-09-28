# Phase 3 Direction — Decisions & Roadmap

*Decided 2026-09-28. Closes the open decisions in `CLAUDE.md` §5. Decisions 1, 2, 4 and 5 are Devansh's; 3 and 6 were delegated to Claude and are reasoned out below — **interject if either is off.** Amend this file when direction changes; do not let it drift silently.*

---

## 1. The decisions

| # | Decision | Answer | Decided by |
|---|---|---|---|
| 1 | Market / asset class | **Indian equities, equity derivatives, and IPOs** | Devansh |
| 2 | Learning vs earning | **Learning vehicle now**, shifting gradually toward earning | Devansh |
| 3 | Horizon / turnover | **Low turnover** — daily data, monthly-to-semi-annual rebalancing, no intraday. §2 | Claude (delegated) |
| 4 | Time budget / cadence | **Platform build** — a real dashboard and a real algo | Devansh |
| 5 | Real capital | **Yes, later**, via a graduated path. §4 | Devansh |
| 6 | Build vs adopt | **Per-layer** (`research/03`), applied to this direction in §3 | Claude (delegated) |

---

## 2. Decision 3 — turnover (delegated call)

### 2.1 The call

> **Low turnover.** Daily bars for data; decisions made at most weekly; portfolios rebalanced **monthly or slower**. **No intraday trading.** Derivatives traded at the same horizon — held, never scalped.

### 2.2 Why — the arithmetic

STT alone, per full round trip, from `research/01` §5.2 (rates in force from 1 Apr 2026):

| Instrument | STT per round trip |
|---|---|
| Delivery equity | 0.1% buy + 0.1% sell = **0.20%** |
| Index futures | 0.05% sell side only = **0.05%** |

Annual drag if the whole portfolio turns over at each rebalance — **estimate, STT only**; brokerage, exchange charges, stamp duty, GST, SEBI fees, spread and market impact all come on top:

| Rebalance frequency | Delivery equity | Index futures |
|---|---|---|
| Daily (~250/yr) | **~50%/yr** | ~12.5%/yr |
| Weekly (52/yr) | **~10.4%/yr** | ~2.6%/yr |
| Monthly (12/yr) | ~2.4%/yr | ~0.6%/yr |
| Semi-annual (2/yr) | ~0.4%/yr | ~0.1%/yr — but see roll cost below |

Compare with what a strategy can realistically earn. `CLAUDE.md` §4.6: realistic live Sharpe for a solo systematic trader is **0.5–1.0**. At an assumed 15% volatility — *an estimate* — Sharpe 0.5 is roughly **7.5%/yr** of excess return.

> **In plain terms:** a stock strategy that rotates its holdings every week pays more in STT alone (~10%/yr) than the entire edge a good solo trader can realistically expect (~7.5%/yr). It is dead before its first trade. Monthly rotation hands about a third of that edge to the exchequer. Semi-annual keeps nearly all of it.

**Futures carry a floor.** Holding a futures position continuously means rolling it at every monthly expiry, and each roll is a round trip: ~**0.6%/yr** in STT regardless of strategy turnover.

**Futures are also capital-gated.** The minimum contract value is ₹15–20 lakh notional (`research/01` §5.3). Until decision 5 arrives, futures strategies are **paper-only**.

### 2.3 Why — everything else points the same way

| Factor | Points to |
|---|---|
| **Tax** (`research/01` §5.4) | Delivery held >12 months → LTCG 12.5%; <12 months → STCG 20%; F&O → business income at slab rates; intraday → speculative income. Irrelevant while learning, material once earning — and only low turnover keeps LTCG treatment available |
| **Evidence** (`CLAUDE.md` §4.2) | What survived replication — momentum, quality, low-risk, trend — operates at monthly-ish horizons |
| **Data** | Daily data is free and already piped (Layer 0). Intraday is paid, messy, and needs infrastructure this project does not have |
| **Learning** | Fewer trades → fewer execution effects mistakable for alpha → attention stays on the research process, which is what is being learned |
| **Regulation** (`research/01` §5.1) | The 10 orders/sec threshold is trivially satisfied, so it never becomes a design constraint |
| **Policy risk** | STT has moved against turnover twice in two years. Low turnover is insulated from the next move |

### 2.4 What this rules out, and when to revisit

**Ruled out:** intraday equity, options scalping, weekly-expiry options trading, anything whose edge is measured per trade in basis points.

**Still in:** delivery equity at monthly-or-slower rebalancing; index futures held for weeks or more; options studied descriptively now (implied vs realised vol via India VIX), and traded later only as held, defined-risk positions; IPOs, which are low-frequency by nature.

**Revisit trigger:** once the validation harness (§6 step ④) can measure a specific strategy's edge per trade net of the full cost stack. A strategy that proves an edge larger than its costs at higher frequency earns the right to trade faster. The default does not move without that evidence.

---

## 3. Decision 6 — build vs adopt, applied to this direction

`research/03` resolved this per-layer in the abstract. With India, derivatives and a dashboard now chosen:

| Component | Call | Why |
|---|---|---|
| **Data spine** | **Keep** Layer 0; **adopt [jugaad-data](https://github.com/jugaad-py/jugaad-data)** for NSE equities, F&O bhavcopy and index history | Now needed rather than optional. Actively maintained. **Public domain** (its `LICENSE.YOLO.md`: "jugaad-data is in public domain") — the "none" flag in `research/03` was a false alarm |
| **Validation harness** | **Implement the statistics; adopt `purgedcv` and `skfolio` as oracles** | Unchanged from `research/03` §4.3 |
| **Backtester** | **Build our own thin, vectorised, daily-bar backtester** | Low turnover and daily bars make vectorised sufficient; no event-driven engine is needed until execution. The Indian cost stack is a policy variable that must be owned and date-stamped (see §6 step ④). And building it is the learning goal |
| **Dashboard** | **Streamlit** | Python-native — the same stack and the same parquet store, zero frontend work. A solo research dashboard does not need a web framework. Reversible if it is outgrown |
| **Execution / live** | **Defer to the capital stage** | Re-evaluate broker APIs (e.g. [pykiteconnect](https://github.com/zerodha/pykiteconnect), MIT, active) and whether an event-driven engine is worth adopting for backtest–live parity, at that point and not before |

---

## 4. What "learning now, earning later" and "capital later" mean in practice

**Learning now, earning later.** The harness reports **net-of-cost and net-of-tax** results from its first run, even while nobody is optimising for them. The switch to earning then changes *which number is optimised*, not the infrastructure. Retrofitting costs and tax into a gross-return system is exactly how strategies acquire an edge they never had.

**Capital later — a graduated path.** Real money is handled the way any autonomous agent is onboarded: prove it in trial, extend bounded autonomy, widen as performance earns it.

| Stage | What runs | Gate to move on |
|---|---|---|
| **1. Paper** | Strategy runs live against real prices, orders simulated | Pre-registered evaluation criteria met over a pre-set minimum period |
| **2. Small capital** | Real orders, capped exposure | Live-vs-paper divergence within tolerance; no risk-limit breaches |
| **3. Scaled** | Exposure widened incrementally | Continued performance against the same criteria |

**The gate criteria are Devansh's to set, not Claude's** — this is the real-money line in `CLAUDE.md` §2. They should be written down **before** stage 1 begins, so that they cannot be tuned to fit whatever results stage 1 happens to produce.

Stage 2 triggers the SEBI retail algo requirements (`research/01` §5.1): static IP registered with the broker, OAuth + 2FA with daily forced logout, market-price protection, empanelled broker API.

---

## 5. Consequences for the observatory

- **Subjects narrow:** Indian equities (index, sector, breadth), India VIX and equity derivatives, institutional flows, IPOs.
- **Commodities, FX and global context become context, not subjects.** Kept, not removed — they still answer questions that matter to an Indian equity book (D2 global vol beta, C3 crude sensitivity, G1 what is genuinely uncorrelated).
- **Two new question sections** added to `research/02` §3: **H — equity derivatives** and **I — IPOs**.
- **Observatory Layer 4 ("a weekly report that gets read") becomes the first half of the dashboard.** The descriptive dashboard ships first, carries zero overfitting risk, and the strategy-monitoring half is added once there is a strategy to monitor.

---

## 6. Phase 3 roadmap

Each step needs its own go-ahead before code is written (`CLAUDE.md` §2).

| Step | What | Unlocks | Depends on |
|---|---|---|---|
| **① Housekeeping** | Commit the pending docs; refresh the data snapshot (stale since 2026-08-12) | Clean base | — |
| **② Data expansion** | F&O bhavcopy + equity universe via jugaad-data; **daily FII/DII capture** (time-sensitive, `research/03` §5); point-in-time Nifty 200 constituents | H questions, E1/E2, step ⑤ | ① |
| **③ Observatory Layers 1–2 + dashboard v0** | Returns, vol, drawdowns, rolling correlations, lead-lag — in Streamlit | A, D, H questions; a dashboard you can open | ②, partly |
| **④ Validation harness** | Indian cost model, walk-forward + purged CV, DSR/PBO with oracles, trial log | Any strategy work | ① |
| **⑤ Reference strategy** | Replicate **Nifty200 Momentum 30** from its published rules (§7) | Proof the harness is honest | ②, ④ |
| **⑥ Dashboard v1** | Add strategy monitoring: positions, P&L net of cost and tax, drift from backtest | Paper trading | ③, ⑤ |
| **⑦ Paper → capital** | The graduated path in §4 | Earning | ⑥, plus Devansh's gate criteria |
| **∥ IPO track** | Study first — how IPO research is done professionally, plus the Indian specifics (mainboard vs SME, subscription categories, anchor lock-ins, grey-market premium) — then source a dataset and answer the I questions | IPO strategies, later | Runs in parallel from ① |
| **∥ Reading** | Narang → Chan → Grinold & Kahn → López de Prado, with its criticisms (carried over from Phase 1's plan) | Judgment behind every step | Runs in parallel |

**Step ④ — one non-obvious requirement.** The cost model must be **date-stamped**: STT changed in Oct 2024 and again in Apr 2026, so a backtest over 2015–2026 must charge the rate in force on each trade date. Forward-looking evaluation should use today's rates, since that is what a live strategy will actually pay. Both numbers get reported.

---

## 7. Why Nifty200 Momentum 30 is the reference strategy

`CLAUDE.md` §6 calls for a "deliberately boring reference strategy" reproduced end-to-end, where the goal is *a correct replication, not a good return*. This index fits unusually well.

| Property | Detail |
|---|---|
| **Published rules** | Top 30 of the Nifty 200 by a normalised momentum score built from 6- and 12-month returns adjusted for daily volatility. Weight = free-float market cap × score, capped at the lower of 5% or 5× the stock's free-float weight. Rebalanced **semi-annually, June and December** ([UTI MF](https://www.utimf.com/articles/what-is-nifty-200-momentum-30-index-and-how-it-works), [Axis Max Life](https://www.axismaxlife.com/blog/investments/what-is-nifty-200-momentum-30-index)) |
| **A known answer** | NSE publishes the index and its TRI. The replication either matches or it doesn't — no room to talk yourself into a result |
| **A second known answer** | Index funds and ETFs track it. Their tracking difference against the TRI is the *real-world* cost of implementing it — a benchmark for our cost model. *Idea, to verify* |
| **A surviving factor** | Momentum is on the replicated-factor list (`CLAUDE.md` §4.2) |
| **Low turnover** | Two rebalances a year — consistent with §2. Still a substantial reshuffle: ~20 of 30 stocks changed in June 2025 ([Business Standard](https://www.business-standard.com/amp/markets/stock-market-news/nifty200-momentum-30-index-to-see-20-stock-changes-on-june-27-125062600872_1.html)) |
| **Self-testing for survivorship** | Replicating it needs point-in-time Nifty 200 membership. Get that wrong — use today's constituents for 2018 — and the replication diverges from the published index. **The harness catches its own data bug** |

**The published TRI is gross of costs.** Replication is judged against the TRI gross; the cost model is then applied on top to get what an investor actually receives.

**To confirm before building:** the exact normalised-score formula from the official methodology document on niftyindices.com. The secondary sources above summarise it but are not the rulebook.

---

## 8. Open items

| # | Item | Owner | Blocks |
|---|---|---|---|
| 1 | Gate criteria for the graduated capital path (§4) | **Devansh** | ⑦ |
| 2 | Source for point-in-time Nifty 200 constituents — the hardest data problem in the plan | Claude | ⑤ |
| 3 | Official Nifty200 Momentum 30 methodology PDF | Claude | ⑤ |
| 4 | IPO dataset source (mainboard + SME, subscription by category, listing prices, anchor lock-in dates) | Claude, after study pass | IPO track |
| 5 | Current F&O lot sizes and margin requirements, for realistic paper sizing | Claude | futures strategies |

---

## 9. Log

| Date | Entry |
|---|---|
| 2026-09-28 | `CLAUDE.md` §5 closed. Devansh: Indian equities + derivatives + IPOs; learning-first shifting to earning; platform build; capital later. Delegated to Claude and decided here: low turnover (STT arithmetic, §2) and per-layer build-vs-adopt applied to this direction (§3). Phase 3 roadmap proposed with Nifty200 Momentum 30 as the reference replication. jugaad-data confirmed public domain. No code written. |
