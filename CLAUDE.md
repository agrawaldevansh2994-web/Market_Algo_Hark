# CLAUDE.md — Algo_Finance

*Working brain for this project. Read this first, every session. Keep it current — correct stale facts directly; check before changing design decisions.*

---

## 1. What this project is

Devansh has a long-standing interest in markets — equities, trading, commodities, some crypto, some FX — that predates his move into AI. The premise of this project is to bring the AI/engineering capability back to that interest and build a **technical structure for systematic trading**.

**Explicitly stated at kickoff (2026-08-11):**
- There is **no specific use case chosen yet**. No instrument, no market, no strategy.
- There is **no intention to start trading real money yet**.
- The goal is to *learn how this is actually done*, build, observe how the algorithm performs, and let the direction emerge from that.
- Sequence is deliberate: **study the established industry approach first**, then blend it with his own goals and original ideas. Not rigid curriculum-following, not improvising blind.

**So the current phase is: research and scoping. Not design. Not build.**

---

## 2. How to work here

`profile.md` in this folder is Devansh's working-style profile — hard rules, defaults, judgment calls. **It is authoritative and takes precedence over anything in this file.** Do not duplicate it here; read it.

The ones that bind hardest on *this* project:

- **Never write or modify code until told to proceed with an explicit go-ahead.** Propose and plan; wait.
- **Do not extrapolate his domain judgment.** Working-style patterns say nothing about risk tolerance, capital, or what "good enough" means in a field he is new to. Anything with real money behind it is his call — surface it, don't infer it.
- Structured formats (tables, numbered flows, callouts) over prose walls. Standing rule for this whole project.
- Translate technical findings into **plain-language real-world impact** before asking for approval.
- Record decisions durably **in files next to the finding they resolve**, not in chat history.
- Scope sessions to what can actually finish; defer the rest to a tracked file.
- Two failure modes he asked to have flagged rather than accommodated: accepting a plausible premise without checking it, and over-applying a valid-but-low-priority principle.

**Project-specific guardrail:** this is a domain where confident-sounding wrong answers are cheap and expensive. Every quantitative claim in this project gets a source or gets labelled as an estimate. Backtest numbers are claims, not evidence — see §4.

---

## 3. State of the project

| | |
|---|---|
| **Phase** | 2 — Market Observatory (descriptive analysis). Phase 1 research complete. |
| **Code written** | Layer 0 data spine only — observation infrastructure, no strategy logic |
| **Strategy chosen** | None |
| **Market/instrument chosen** | None committed. Observatory covers Indian equities, commodities, FX — deliberately, to *inform* §5.1 rather than pre-empt it |
| **Capital committed** | None |
| **Last updated** | 2026-08-12 |

### Files

```
Algo_Finance/
├── CLAUDE.md                           # this file
├── research/
│   ├── 01-industry-landscape.md        # Phase 1 findings, fully sourced
│   └── 02-observatory-scope.md         # Phase 2 scope, question bank, data-quality findings
└── observatory/
    ├── config/instruments.yaml         # 27 instruments — the only place tickers live
    ├── obs/{registry,store,fetch,panel}.py
    ├── build.py                        # fetch + rebuild curated panels
    ├── checks.py                       # data integrity — run after every build
    └── data/{raw,curated}/             # snapshot-dated parquet
```

`profile.md` is referenced in §2 but is not present in this folder — the working-style
rules are loaded from `C:\Users\agraw\Harnessing brain\` instead.

**Run it:** `.venv\Scripts\python.exe build.py` then `checks.py`, from `observatory/`.

---

## 4. Load-bearing findings from Phase 1

*Full detail and sources in `research/01-industry-landscape.md`. These are the conclusions that should shape every later decision.*

### 4.1 "An algorithm" is four separable systems, not one

| Layer | Answers | Common mistake |
|---|---|---|
| Alpha / signal | What will outperform what? | Confusing a signal with a strategy |
| Portfolio construction | How much of each do I hold? | Letting the signal size positions directly |
| Execution | How do I get from here to target? | Assuming fills at the signal price |
| Risk | What must never happen? | Making it part of the strategy instead of an independent veto |

Keeping these separate is *the* architectural lesson of the field (Grinold & Kahn → Narang). It is what makes live-vs-backtest divergence diagnosable: attribution tells you which layer broke.

### 4.2 The backtest is the enemy, not the tool

The single most important thing on this project. A backtest is a **claim**, produced by a process (a human iterating on a dataset) structurally biased toward producing good-looking claims whether or not any edge exists.

- Engineers are trained to iterate until something passes. **On market data that is precisely the overfitting procedure.**
- Deflated Sharpe Ratio result to internalise: **with enough trials, no observed Sharpe is high enough to reject the null of no skill.** More backtests should reduce confidence in a good result, not raise it.
- Harvey-Liu: the conventional t > 2.0 bar guarantees false positives given how much has been mined. Use **t ≥ 3.0**.
- Hou-Xue-Zhang: **over half of ~450 published anomalies failed to replicate.** What survived: value, momentum, quality/profitability, low-risk, carry, trend.
- López de Prado's rule: *if a strategy backtests badly, do not tweak it until it looks good — investigate how the research process misled you. Fix the process, not the strategy.*

**Operating consequence for this project:** the validation protocol (12 gates, §3.6 of the research doc) is not optional polish added at the end. It gets built into the workflow from the first experiment, or the whole exercise is theatre.

### 4.3 Costs kill more strategies than bad signals do

Spread + market impact (√-law: impact ∝ √(size/ADV) × vol) + financing. A large share of published "profitable" retail *and academic* strategies go marginal or negative under realistic costs. Costs are modelled **in from the start**, never as a post-hoc haircut.

### 4.4 The India cost stack moved against high-turnover trading — twice in two years

**STT, effective 1 April 2026** (verified against multiple sources):

| | Pre-Oct 2024 | Oct 2024 | **From 1 Apr 2026** |
|---|---|---|---|
| Equity futures (sell) | 0.0125% | 0.02% | **0.05%** |
| Equity options | 0.0625% premium | 0.1% premium | **0.15%**, premium *and* exercise |
| Equity delivery / intraday | 0.1% / 0.025% | unchanged | unchanged |

Futures STT is now **4x** its pre-Oct-2024 level. Plus exchange charges, stamp duty, GST, SEBI turnover fees.

**This is structural, not incremental.** Any Indian derivatives strategy whose per-trade edge is smaller than the round-trip cost stack is dead on arrival — and the cost stack is a *policy variable that has moved twice against high-turnover traders.* Low-turnover approaches (delivery equity, multi-day holds) are far less exposed.

### 4.5 SEBI's retail algo framework is live and binding (since 1 April 2026)

| Activity | Position |
|---|---|
| Research / backtest only | **No regulatory trigger.** This is where we are |
| Own self-written algo, own capital, **<10 orders/sec** | Allowed, no exchange registration — but requires **static IP whitelisting**, OAuth + daily-forced-logout 2FA, mandatory market-price-protection, via an empanelled broker API |
| **>10 orders/sec** | Exchange registration + unique algo ID required |
| **Sharing or selling a strategy to others** | Line moves sharply — algo-provider empanelment, Indian server hosting, 5-yr audit logs; possible IA/RA registration overlap, **genuinely unsettled** |

### 4.6 What is realistically open to a solo builder

**Closed:** latency arbitrage / HFT (colocation + FPGA + microwave; retail broker round-trips are 50–500ms), regulated-venue market making, most alt-data edges (data cost).

**Open, with documented evidence:** trend following (best-documented, lowest infra barrier), cross-sectional equity factors, daily-bar mean reversion / pairs, systematic event-driven (PEAD), carry — and capacity-constrained corners big funds structurally cannot fit into (small/micro-cap systematic, narrow cointegration pairs, small-deal event-driven).

**Realistic live Sharpe for a competent solo systematic trader: 0.5–1.0.** Backtest Sharpe should be treated as an upper bound and discounted 30–60%.

**The one genuine free lunch:** combining structurally uncorrelated strategies raises portfolio Sharpe with **no additional edge discovery required.** Trend in particular tends to perform when equity factors and carry don't.

### 4.7 Base rates, stated plainly

SEBI: **93% of individual F&O traders lost money FY22–FY24** (>₹1.8 lakh crore); **91% in FY25** (₹1.06 lakh crore, up 41% YoY). Brazil B3: of those who persisted day-trading 300+ days, **97% lost money**. Taiwan: **<1% persistently profit** — though that minority shows real year-over-year skill persistence, so success is rare and durable rather than random.

These measure *discretionary/short-horizon* trading, not systematic strategies — but the arithmetic they expose (costs are real, counterparties are better informed, the base rate of "found an edge" is low) is exactly what any backtest is implicitly competing against.

---

## 5. Open decisions — Devansh's call, do not assume

Per `profile.md`, these turn on domain judgment and personal circumstance that has not been demonstrated. Surface them; do not infer.

1. **Market / asset class.** Indian equities & derivatives? US equities (better data, cleaner research, no STT)? Crypto (24/7, free data, brutal 30%-no-loss-offset tax for an Indian resident)? Each implies a completely different data and infrastructure path.
2. **Learning vehicle vs. earning vehicle.** Optimising to *understand the machine* and optimising for *net-of-tax returns* point at different first projects. He has said this is exploratory — worth confirming that framing holds before scoping anything.
3. **Horizon / turnover class.** The single biggest fork given §4.4. Low-turnover survives the Indian cost stack; high-turnover mostly doesn't.
4. **Time budget and cadence.** Determines whether this is a build-a-platform project or a run-a-few-experiments project.
5. **Whether real capital is ever in scope**, and if so at what scale. Changes what "done" means at every stage.
6. **Build vs adopt** — hand-rolled research stack vs adopting NautilusTrader / QuantConnect LEAN early.

---

## 6. Proposed next phase (not started — awaiting go-ahead)

Sequenced so that nothing depends on a decision that hasn't been made yet.

1. **Close the open decisions above** — at minimum #1, #2 and #3, since everything downstream forks on them.
2. **Foundational reading, prioritised.** Narang's *Inside the Black Box* first (the four-layer architecture, accessibly), then Chan for the practical solo view, Grinold & Kahn for depth, López de Prado for validation machinery — with its criticisms noted.
3. **Build the validation harness before building any strategy.** Deliberately inverted from the intuitive order: the harness (point-in-time data handling, cost model, purged CV, DSR/PBO, sealed holdout, research log) is the thing that makes every later result trustworthy. Building it first also means the first strategy cannot be graded by a harness that was tuned to flatter it.
4. **One deliberately boring reference strategy** — a well-documented, published, unexciting strategy reproduced end-to-end purely to validate the harness and learn the pipeline. The goal is *a correct replication*, not a good return. If the harness can honestly reproduce a known result, it can be trusted on an unknown one.
5. **Only then**, original ideas.

---

## 7. Log

| Date | Entry |
|---|---|
| 2026-08-11 | Project kickoff. `profile.md` supplied. Phase 1 research completed across 5 tracks (lifecycle, strategy families, stack, failure modes, India context) → `research/01-industry-landscape.md`. STT hike and SEBI algo framework independently re-verified. No code written. Awaiting decisions in §5. |
| 2026-08-12 | **Phase 2 opened: the Market Observatory.** Descriptive cross-asset analysis of Indian equities, commodities and FX — chosen deliberately as a no-overfitting-risk first build whose data layer doubles as the foundation of the §6.3 validation harness. Scope locked in `research/02-observatory-scope.md`: 27 instruments, a 20-question bank, and written policies for the three traps (session contamination, commodity denomination, scope drift). **Layer 0 built and verified.** Two real data faults found and fixed by the integrity checks — Yahoo `=X` spot FX is unusable at daily frequency (moved to FRED H.10), and apparent data gaps proved to be genuine pegged-currency history. 24 series, 2008-03-03 → 2026-08-07. No analysis run yet; Layers 1–4 not started. |
