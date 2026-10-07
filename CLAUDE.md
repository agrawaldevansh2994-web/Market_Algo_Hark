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

**Updated 2026-09-28:** the §5 decisions are closed — Indian equities, derivatives and IPOs; learning first; a real dashboard and algo. The project is now moving into **Phase 3, a platform build** (`research/04-direction.md`). Each build step still needs its own explicit go-ahead.

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
| **Phase** | **3 — platform build, in progress.** Steps ①, ③, ④ done; ② largely done; ⑤ first pass built 2026-10-07 — `research/04-direction.md` §6 |
| **Code written** | Data layer (prices, flows, participant OI, index-membership snapshots, capture, checks) + observatory dashboard + **validation harness** (`observatory/harness/`) + **NSE equity bhavcopy store, corporate-action audit and the Nifty200 Momentum 30 replication** (step ⑤). One harness shakedown experiment (E001); no strategy proposed |
| **Strategy chosen** | None live. Reference replication **Nifty200 Momentum 30** — first pass: 28/30 of the June 2026 picks match; returns track within +1.6 pts/yr since 2018, −4.4 pts/yr over 2005–2026 (`observatory/reports/mom30/report.md`) |
| **Market/instrument chosen** | **Indian equities, equity derivatives, IPOs** (decided 2026-09-28). Commodities/FX/global stay in the observatory as context |
| **Turnover class** | **Low** — monthly-or-slower rebalance, no intraday |
| **Capital committed** | None. In scope later via a graduated path — gate criteria are Devansh's to set |
| **Last updated** | 2026-10-07 (step ⑤ first pass) |

### Files

```
Algo_Finance/
├── CLAUDE.md                           # this file
├── research/
│   ├── 01-industry-landscape.md        # Phase 1 findings, fully sourced
│   ├── 02-observatory-scope.md         # Phase 2 scope, question bank, data-quality findings
│   ├── 03-open-source-survey.md        # build-vs-adopt, resolved per-layer; §5.6
│   ├── 04-direction.md                 # Phase 3: §5 decisions, turnover call, roadmap
│   └── market_patterns.md              # dated log of empirical findings (data + market)
└── observatory/
    ├── config/instruments.yaml         # 29 instruments — the only place tickers live
    ├── obs/{registry,store,fetch,panel}.py
    ├── obs/flows.py                    # FII/DII (NSE, MSEI fallback) + NSDL FPI since 1999
    ├── obs/fno.py                      # NSE participant-wise open interest since 2012
    ├── obs/universe.py                 # index constituent snapshots + members_at() — point-in-time membership
    ├── obs/bhavcopy.py                 # NSE equity bhavcopy 2004→ (legacy + UDiFF formats) → data/bhav/ (gitignored, ~195 MB)
    ├── obs/corpactions.py              # NSE corporate-action feed + Yahoo splits → audited adjustment factors
    ├── obs/momentum.py                 # Nifty200 Momentum 30 rules (official methodology pp.187–189), buffer, capping, drift
    ├── obs/textstore.py                # per-year CSV split (keeps committed text files < 128 KB)
    ├── obs/analysis.py                 # Layers 1–2: drawdown, vol, rolling corr, lead-lag, regimes, NSDL re-dating (unit-tested)
    ├── dashboard.py                    # Streamlit dashboard v0 — `streamlit run dashboard.py` from observatory/ → localhost:8501
    ├── harness/                        # step ④ validation harness — costs, backtest, splits, stats, trials, gates
    ├── experiments/                    # one script per pre-registered experiment (E001 = harness shakedown)
    ├── reports/                        # generated experiment reports (markdown + chart), committed
    ├── trials/log.jsonl                # append-only trial log — registrations, trials, holdout unlocks. NEVER edit by hand
    ├── tests/                          # pytest: `python -m pytest -q` from observatory/ (69 tests)
    ├── build.py                        # fetch prices + rebuild curated panels
    ├── build_bhav.py                   # fetch/update the bhavcopy store (incremental)
    ├── build_momentum.py               # step ⑤: audit + replication → reports/mom30/, reports/corpactions/
    ├── capture.py                      # nightly capture — scheduled 21:30 + 23:30 IST
    ├── checks.py                       # data integrity — run after every build
    └── data/{raw,curated}/             # snapshot-dated + month-partitioned parquet
```

**Run it:** from `observatory/` — `..\.venv\Scripts\python.exe build.py` then `checks.py`; dashboard: `..\.venv\Scripts\python.exe -m streamlit run dashboard.py`. `capture.py` runs itself nightly (Task Scheduler `AlgoFinance-NightlyCapture`; log in `data/capture.log`); `capture.py --backfill` refills any missing history.

### Version control

- **Repo:** [agrawaldevansh2994-web/Algo_Finance](https://github.com/agrawaldevansh2994-web/Algo_Finance) (private). Under git since 2026-08-12.
- **What's tracked:** research docs, observatory code/config, and `data/raw/` snapshots (point-in-time, not regenerable — the reproducibility record). **Ignored:** `.venv/` (rebuild from `requirements.txt`) and `data/curated/` (rebuild via `build.py`).
- **Everyday loop:** `git add -A && git commit -m "…" && git push`.
- **Accounts (re-checked 2026-09-28):** the GitHub MCP ("git dashboard") and the `gh` CLI's active account are both `agrawaldevansh2994-web`, the repo owner — the earlier `Devansh-AIprojects` mismatch is resolved. `gh` also holds `Devansh-AIprojects` as an inactive second login; if pushes ever 403, check `gh auth status` for which account is active.
- **Git as epistemic record, not just backup:** the anti-data-snooping defence (research/01 §3.1) needs a tamper-evident log of what was tried and when. Commit history *is* that trial count — keep experiments in their own commits.

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

## 5. Decisions — closed 2026-09-28

Full reasoning in `research/04-direction.md`. #3 and #6 were delegated to Claude; the rest are Devansh's. **Anything touching real money remains his call** — in particular the gate criteria for the capital path.

| # | Decision | Answer | By |
|---|---|---|---|
| 1 | Market / asset class | **Indian equities, equity derivatives, IPOs** | Devansh |
| 2 | Learning vs earning | **Learning now**, shifting gradually to earning. The harness reports net-of-cost and net-of-tax from day one, so the switch needs no rework | Devansh |
| 3 | Horizon / turnover | **Low** — monthly-or-slower rebalance, no intraday, derivatives held not scalped. Weekly rotation of a stock portfolio costs ~10%/yr in STT alone, more than the realistic solo edge (estimate; `04` §2) | Claude |
| 4 | Time budget / cadence | **Platform build** — a real dashboard + algo | Devansh |
| 5 | Real capital | **Yes, later** — graduated: paper → small capital → scaled, gate criteria set by Devansh *before* paper trading starts | Devansh |
| 6 | Build vs adopt | **Per-layer.** Keep Layer 0 + adopt jugaad-data; implement harness statistics with `purgedcv`/`skfolio` as oracles; own thin vectorised daily backtester; Streamlit dashboard; defer execution tooling to the capital stage | Claude |

**Revisit trigger for #3:** a strategy whose edge per trade, measured net of the full cost stack by the harness, justifies trading faster.

---

## 6. Phase 3 roadmap (proposed — each step needs its own go-ahead)

Detail in `research/04-direction.md` §6. The ordering principles from Phase 1 still hold: **harness before any strategy**, then **a boring replication with a known answer**, and **only then** original ideas.

| Step | What |
|---|---|
| ① Housekeeping | ✅ done 2026-09-28 — docs committed, data refreshed |
| ② Data expansion | **Mostly done.** ✅ FII/DII capture, NSDL FPI history, participant OI, index-constituent snapshots, ✅ **equity bhavcopy 2004→ + audited corporate actions (2026-10-07)**. **Left:** full F&O bhavcopy ingest (H2/H3; only per-review F&O stock lists so far) |
| ③ Observatory L1–2 + dashboard v0 | **Built 2026-10-01** — `obs/analysis.py` + `dashboard.py` (Overview, Equity structure, Flows & positioning, Data health; light and dark mode checked in a browser). First findings in `market_patterns.md`. Still to add: A2–A4, B, C, F, G1 views; F&O (H) and IPO (I) views once their data exists |
| ④ Validation harness | ✅ **Built 2026-10-07** (`observatory/harness/`): date-stamped cost model, lag-enforced vectorised backtester, walk-forward / purged k-fold / CPCV (matches `skfolio` oracle), PSR/DSR/MinTRL/Harvey-Liu/PBO, pre-registration + trial log + one-time holdout seal, regime/sensitivity/capacity gates. Shakedown E001 run. **Still to add:** ADV data for capacity (gate 8), F&O cost path exercised on real data, net-of-tax for F&O (business income) |
| ⑤ Reference strategy | Replicate **Nifty200 Momentum 30**, **re-scoped 2026-10-01**: free data has no point-in-time membership and bhavcopy prices are unadjusted, so this becomes a *measured, decomposed* replication on a liquidity-ranked proxy universe (`research/04` §7.1). Goal: an explained gap to the published index, not an exact match. **First pass built 2026-10-07** — dashboard *Momentum 30* view; selection 28/30 on the June 2026 review; gap concentrated pre-2018, causes listed in `reports/mom30/report.md` §Leading hypotheses — **next: decompose that gap** |
| ⑥ Dashboard v1 | Strategy monitoring — positions, P&L net of cost and tax, drift from backtest |
| ⑦ Paper → capital | Graduated path; needs Devansh's gate criteria first |
| ∥ IPO track | Study-first, then dataset, then the IPO question bank (`research/02` §3 I) |
| ∥ Reading | Narang → Chan → Grinold & Kahn → López de Prado (with its criticisms) |

---

## 7. Log

| Date | Entry |
|---|---|
| 2026-08-11 | Project kickoff. Phase 1 research completed across 5 tracks (lifecycle, strategy families, stack, failure modes, India context) → `research/01-industry-landscape.md`. STT hike and SEBI algo framework independently re-verified. No code written. Awaiting decisions in §5. |
| 2026-08-12 | **Phase 2 opened: the Market Observatory.** Descriptive cross-asset analysis of Indian equities, commodities and FX — chosen deliberately as a no-overfitting-risk first build whose data layer doubles as the foundation of the §6.3 validation harness. Scope locked in `research/02-observatory-scope.md`: 27 instruments, a 20-question bank, and written policies for the three traps (session contamination, commodity denomination, scope drift). **Layer 0 built and verified.** Two real data faults found and fixed by the integrity checks — Yahoo `=X` spot FX is unusable at daily frequency (moved to FRED H.10), and apparent data gaps proved to be genuine pegged-currency history. 24 series, 2008-03-03 → 2026-08-07. No analysis run yet; Layers 1–4 not started. |
| 2026-08-12 | **Git initialised, pushed to private GitHub repo** ([agrawaldevansh2994-web/Algo_Finance](https://github.com/agrawaldevansh2994-web/Algo_Finance)). `requirements.txt` pinned; `data/raw/` tracked, `.venv/`+`curated/` ignored. MCP-account-mismatch caveat recorded in §3 — use the `git` CLI, not MCP GitHub tools, on this repo. |
| 2026-08-13 | **Open-source survey → `research/03-open-source-survey.md`.** ~35 repos health-checked live via the GitHub API. Three findings that change the plan: (1) **`mlfinlab`, the canonical López de Prado validation implementation, has gone closed-source** — §6.3 has no mature free reference implementation, so the harness becomes implement-the-statistics + adopt-a-library-as-oracle; (2) **no open-source project closes the India data gaps**, and NSE FII/DII is latest-day-only, so history is being lost every day it goes uncaptured — a near-term action that blocks on none of §5; (3) backtrader, zipline, pyfolio and alphalens are all **dead** despite dominating tutorials. §5.6 resolved per-layer, pending sign-off. Nothing adopted, no code written. |
| 2026-08-13 | **`research/market_patterns.md` created** — a dated, standalone log for empirical findings (as opposed to `02-observatory-scope.md`, which is policy/methodology). Populated with the two Layer 0 findings already on record: Yahoo `=X` FX unusable daily, and pegged-currency zero-return days being real history. Will accumulate actual market-behaviour findings once Layers 1–4 run. |
| 2026-09-28 | **§5 decisions closed → `research/04-direction.md`.** Resumed after ~6 weeks idle (no drift: repo exactly as left 2026-08-13, three files uncommitted). Devansh chose Indian equities + derivatives + IPOs, learning-first, platform build, capital later. Claude, on delegation: **low turnover** (STT arithmetic: weekly stock rotation costs more than the realistic edge) and **per-layer build-vs-adopt** (own backtester, Streamlit, jugaad-data, oracle-checked harness). Phase 3 roadmap proposed; reference replication = Nifty200 Momentum 30 (published rules, semi-annual, known TRI, self-tests for survivorship). Observatory re-prioritised: H (derivatives) and I (IPO) questions added to `research/02`. jugaad-data license confirmed public domain. No code written. |
| 2026-09-28 | **Phase 3 build started (Devansh: "I will let you handle as of now"; real money stays his).** GitHub accounts re-checked — MCP and `gh` both on `agrawaldevansh2994-web`. Step ①: data refreshed to 2026-09-28; fixed a Layer 0 bug that froze mid-session US bars into snapshots (up to 0.9% off). Step ②: **flows layer** — NSDL FPI daily history 1999 → today; nightly FII/DII capture (NSE, MSEI fallback) scheduled 21:30 + 23:30 IST; NSE participant OI from 2012 (new question E3). Measured the NSDL T+1 reporting convention (prior-day r +0.26 vs same-row +0.04) — a naive join would have decided E1 by accident. New checks; one malformed 2013 NSE file rejected by the long = short identity. Findings in `market_patterns.md`. Remaining in ②: F&O bhavcopy, point-in-time Nifty 200 constituents. |
| 2026-10-01 | **Resumed; ② nearly complete; ⑤ re-scoped.** (1) **A capture night was lost** (2026-09-28 DII flow — permanent; machine was off for the 24 h window) → scheduled task now fires 09:00/13:00/21:30/23:30 IST, `checks.py` reports lost days + staleness, backfills have circuit breakers. (2) **No free point-in-time index membership exists** — forward capture of six constituent lists started 2026-10-01 (`obs/universe.py`), Internet Archive anchors pulled best-effort; index definitions verified as exact set identities. (3) **Tested and refuted** the idea that NSE bhavcopy `PREVCLOSE` gives free adjusted prices (Reliance 2017 bonus: 0 of 1,500 stocks rebased) — corporate-action adjustment is the crux of any bhavcopy work. (4) Step ⑤ re-scoped to a decomposed replication on a proxy universe. (5) NSE's main site still 403s from this machine; MSEI is the working FII/DII source and its FII `sell` field is wrong every time (use `net`). (6) Fixed a console-encoding crash that would have killed scheduled runs. **Needs Devansh:** OK to add a GitHub Actions cron to run `capture.py` always-on (`research/04` open item 10). |
| 2026-10-01 | **Step ③ built; session closed mid-stream at Devansh's request — resume from here.** `obs/analysis.py` (pure functions, 20 tests incl. a no-lookahead property test), `dashboard.py` (4 views; every chart has a table twin; palette validated with the dataviz skill's checker; both colour modes viewed in a browser), `tests/` (25 tests, all pass). First descriptive findings logged (A1, D1, D3, E1 — headline: Nifty–Bank correlation rises in stress; stress is variance not mean; correlations with Nifty rise in stress except gold; **FPI flows move with and follow Nifty, no lead**). Participant-OI updater now uses a sidecar of fully-scanned months (a bug had skipped partially-fetched months forever) and a request budget, because NSE's archive host cuts us off after ~1,000 requests; the 23:30 run spends 600/day catching up (stored 2012-01 → 2015-10 so far). Dependency note: installing Streamlit downgraded `websockets` 17.0.1 → 16.1.1; fetchers re-tested fine; full env now pinned in `requirements.txt`. **Resume with:** (a) `git status` — the dashboard/analysis/test work may need committing; (b) price data is stale because nothing schedules `build.py` and refreshing into git-tracked snapshots costs ~4–8 MB each — **decide a price-refresh policy** (idea: nightly refresh into a gitignored `data/live/`, commit dated snapshots only at milestones); (c) Wayback constituent anchors mostly failed (Internet Archive timeouts) — rerun `capture.py --backfill` later; (d) next roadmap items: step ④ validation harness, F&O/equity bhavcopy ingest + corporate-action handling for ⑤, remaining dashboard views. Dashboard server was stopped. |
| 2026-10-03 | **Scheduled capture hardened; drawdown logged.** Found 5 of 11 recent runs killed (0xC000013A) because the task launched `python.exe` with a visible console window that got closed; task now runs `pythonw.exe` with WakeToRun on, `capture.py` guards `sys.stdout is None`; verified with a manual trigger (rc 0, full log). A 12:05 catch-up run hung 18 min with no log (cause unconfirmed — likely console freeze). Still needs always-on host (GitHub Actions) to cover PC-off days. First look at the Aug–Oct 2026 drawdown (Nifty −14.8% from ATH, 8-week losing streak, FPI −$28.8bn YTD, FII index-futures long share 8%) → `market_patterns.md`. Open: price-refresh policy, GH Actions OK, Wayback backfill rerun. |
| 2026-10-07 | **Step ④ built — the validation harness (Hark, on Devansh's go-ahead "make it alive").** Worked in the public clone `Market_Algo_Hark`. `observatory/harness/`: **costs** (STT date-stamped from research/01 §5.2; exchange/SEBI/stamp/GST from zerodha.com/charges read 2026-10-07; pre-2026 non-STT charges approximated at today's rates, < 1.5 bp/side, labelled), **backtest** (target weights in; lag ≥ 1 enforced, `lag=0` raises; weights drift; costs on execution date, dated or frozen-today; √-law impact when ADV is supplied; approximate net-of-tax by Indian FY with loss carry-forward), **splits** (walk-forward, purged k-fold, CPCV — purge/embargo **verified identical to `skfolio.CombinatorialPurgedCV`** as oracle), **stats** (PSR, DSR, E[max SR], MinTRL, Harvey-Liu Bonferroni haircut, PBO by CSCV — checked by simulation, not re-typed formulas), **trials** (registration required before any trial; immutable; trial touching the holdout refused; holdout unlock once, logged), **gates** (India regimes fixed before any run, neighbour-ratio sensitivity, √-law capacity, 12-gate report). 19 new tests, 44 total pass. **E001 shakedown** (Nifty 50 month-end SMA trend vs buy & hold, 9-point grid + 1 cash-yield check, 2008-09 → 2024-09, holdout 2024-10 → sealed): trend cut volatility 19.9% → 13.5% and max drawdown −38% → −34% but CAGR 13.0% → 9.6%; Sharpe 0.75 vs 0.72; **fails gate 5** — PBO 94% (choosing the SMA length is noise), t 2.94 < 3; MinTRL to show it beats buy & hold ≈ 2,800 years. Report: `observatory/reports/e001/`. Harness was debugged (common-window bug) before the first commit and the trial log reset once then; from this commit on the log is append-only. |
| 2026-10-07 | **Older-code fixes (Hark, on Devansh's go-ahead).** `analysis.lead_lag` now returns a Newey-West HAC band and t-stat (`band_hac`, `t_hac`) beside the naive band; dashboard E1 plots the HAC band. `analysis.regime_labels(expanding=True)` gives look-ahead-free VIX cut-offs; dashboard D1/D3 has a toggle. `flows.with_retry` retries NSE FII/DII 3× (5/20/60 s) and MSEI once before giving up, so one blip no longer loses a DII day. `store.read_raw(key, snapshot)` falls back to the vintage on or before the date instead of crashing. 7 new tests, 51 pass. **Re-check:** E1 holds (daily k=+1 HAC t 1.68); D1 holds; D3 direction holds but gold's correlation rises most under expanding cut-offs, so the G1 "gold least stress-sensitive" answer is withdrawn — see market_patterns.md. |
| 2026-10-07 | **Step ⑤ first pass (Hark, on Devansh's go-ahead "build till the dashboard is ready").** (1) `obs/bhavcopy.py` + `build_bhav.py`: NSE equity bhavcopy 2004-01-01 → 2026-10-06 (5,624 days, EQ+BE, both file formats) into gitignored `data/bhav/` — regenerable from NSE's immutable archive. (2) `obs/corpactions.py`: NSE corporate-action feed parsed (bonus/split/consolidation/scheme/rights/dividend) and **audited against the observed price gap**; Yahoo split history as a second source (604 agree, 46 disagree); NSE's feed misses some big splits (JSW Steel 2017, Vedanta 2008, ITC 2005) and NSE does not re-base PREVCLOSE on demergers either. Symbol renames joined via NSE symbolchange.csv; ETFs (ISIN INF…) dropped from the universe. (3) `obs/momentum.py`: official rules confirmed from the Sept 2026 methodology document. (4) Results: June 2026 selection **28/30** vs the actual list; same code on the real Nifty 200 27/30; turnover proxy 154/200 vs the real Nifty 200; returns 13.9% vs 18.4% CAGR 2005–2026 (TE 7.2%) but **+1.6 pts/yr, TE 3.7%, corr 0.985 since 2018**. (5) Dashboard view *Momentum 30* (smoke-tested headless; not yet eyeballed in a browser). 69 tests pass. Text data under `data/corpactions/`, `data/reference/`, `reports/` committed as per-year CSVs. **Next:** decompose the pre-2018 gap (held-stock unexplained gaps → Wayback Nifty 200 anchors → weight proxy); add anchors as forward capture records each review. |
