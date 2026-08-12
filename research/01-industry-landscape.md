# How the Systematic Trading Industry Actually Works

*Research scope pass — compiled 2026-08-11. No strategy chosen, no code written. This is the "study the established curriculum before improvising" stage.*

> **Status of claims.** Everything here is sourced. Where sources conflict, or where a number is folklore rather than documented, it is flagged inline. Sharpe ranges quoted from secondary summaries are marked as estimates. Two facts with large downstream consequences (the April 2026 STT hike and the SEBI retail-algo framework) were independently re-verified against multiple sources — see §5.

---

## 1. The Lifecycle — what "building an algorithm" actually means

The single most common beginner error is treating "the algorithm" as one artefact. In every real shop, it is **four separable systems**, and the discipline comes from keeping them separate.

### 1.1 The four-layer architecture

This traces to Grinold & Kahn's *Active Portfolio Management* and is restated in Narang's *Inside the Black Box*. It is the core architectural lesson of the field.

| Layer | Question it answers | Output | Common mistake |
|---|---|---|---|
| **Alpha / signal model** | What will go up relative to what? | A forecast or score per instrument | Conflating this with the trading rule — a signal is not a strategy |
| **Portfolio construction** | Given the forecasts, how much of each do I hold? | Target positions | Skipping it; letting the signal directly size positions |
| **Execution** | How do I get from current positions to target positions? | Orders | Assuming fills at the price that generated the signal |
| **Risk** | What must never happen regardless of what the signal says? | Constraints, limits, kill-switches | Making it part of the strategy instead of an independent veto |

Why this matters practically: each layer can be tested, attributed, and replaced independently. When live performance diverges from backtest, layered attribution tells you *which* layer broke — signal decay vs cost-model error vs execution slippage. Without the separation, you get one undifferentiated "it isn't working."

WorldQuant's BRAIN platform is the industrial-scale version: thousands of contributors submit raw alphas into a shared simulator; the alphas are treated as commodity inputs, and the (separately owned) correlation-screening, portfolio-construction and execution machinery converts many weak, uncorrelated signals into a book. *Their exact numeric acceptance thresholds are not public — the shape of the model is well evidenced, the gates are not.*

### 1.2 The research-to-production pipeline

Consistent across practitioner accounts. Each stage has a **gate** — a pass/fail you commit to *before* seeing the result.

1. **Hypothesis** — state *why* an edge should exist (behavioural bias, structural flow, risk premium, information advantage). *Gate: is there an economic rationale, and is it non-obvious enough not to be fully crowded?* Two Sigma and D.E. Shaw are both described as rejecting pure data mining with no prior — such signals fail live.
2. **Feature engineering** — cleaning, normalisation, cross-sectional comparability. Reported as where much of a shop's real intellectual capital sits: same raw data, wildly different signal quality depending on transforms.
3. **In-sample testing** — Information Coefficient, IC-IR, quintile spreads, turnover, **with costs folded in from the start, not bolted on later.** *Gate: statistically significant, cost-aware predictive power.*
4. **Out-of-sample / walk-forward** — unseen data spanning multiple regimes. *This stage eliminates the majority of candidates.*
5. **Production screening** — capacity analysis, decay-rate analysis, correlation against the existing signal library, regime stability.
6. **Paper trading / incubation** — real-time simulation with realistic costs and slippage.
7. **Staged live deployment** — small capital first, scaled only as live tracks research expectations, with risk overlays applied at portfolio level.
8. **Monitoring, attribution, retirement.**

López de Prado's framing of the gate discipline is the line worth memorising:

> *"Backtesting is not a research tool. If a strategy does not perform well in a backtest, do not tweak it (overfit) until the backtest looks good. Instead, investigate how the research process misled you… Fix the research process, not the strategy."*

### 1.3 Roles — and what they mean for a solo builder

| Role | Owns |
|---|---|
| Quant researcher | Hypotheses, features, models, backtests |
| Quant developer | Data pipelines (~80% of the job per one practitioner account) and execution/OMS tooling |
| Execution trader | Live risk, intraday P&L, market impact, real-time sizing |
| Risk | Sits **outside the P&L chain**; enforces limits independent of strategy logic |

The separation is a deliberate check against conflicts of interest. A solo builder wears all four hats serially, and the dominant failure mode is collapsing them into one loop where researcher-you tweaks the backtest until trader-you is happy, with no independent risk-you.

The industry's transplantable fix is **procedural, not organisational**:
- A written research log where the hypothesis and pass/fail thresholds are fixed *before* out-of-sample results are seen.
- Execution and portfolio-construction code built as separable modules from the alpha model.
- Hard risk rules (max position, max drawdown, correlation caps) that "trader-you" cannot override without a paper trail.

### 1.4 Post-deployment: alpha decay is the normal case

Decay is treated as inevitable, not exceptional. Maven Securities quantified it: delaying a mean-reversion signal's execution cost an average **9.9%/year in Europe and 5.6%/year in the US**, and that cost is itself growing ~16–36bps/year, driven by crowding, cheaper execution tech, and falling barriers to entry. Funds treat "kill the strategy" as an expected pipeline outcome, not a failure event.

The academic counterpart: **McLean & Pontiff (2016, *Journal of Finance*)** found published return-predictive anomalies decline roughly **26% in-sample-to-out-of-sample**, and decline further *after* publication — implicating both discovery-stage overfitting and post-publication crowding.

### 1.5 The canonical reading list

| Book | Good for | Known criticism |
|---|---|---|
| Grinold & Kahn, *Active Portfolio Management* | The institutional foundation; formalises the four-layer architecture and the Fundamental Law | Dense, mean-variance/CAPM-flavoured |
| Narang, *Inside the Black Box* | The accessible version of the same decomposition; best first read | Light on maths |
| López de Prado, *Advances in Financial Machine Learning* | Purged CV, meta-labelling, triple-barrier, fractional differentiation | Criticised as heavy on academic ML machinery relative to what's deployable; several techniques contested/under-replicated; aimed more at HFT/microstructure than low-frequency |
| Ernest Chan, *Quantitative Trading* / *Algorithmic Trading* / *Machine Trading* | The practical solo/small-shop trilogy | Practical rather than rigorous |
| Chincarini & Kim, *Quantitative Equity Portfolio Management* | Bridges academic theory and real equity portfolio construction | — |
| Harvey, Liu & Zhu, *"…and the Cross-Section of Expected Returns"* | The load-bearing paper behind industry data-mining scepticism | Not a book — read it early anyway |

**Folklore flag:** Renaissance Technologies' methods are not publicly documented. Anything specific circulating about RenTec's pipeline is folklore and is deliberately excluded here.

---

## 2. Strategy Families — the map of what exists

| Family | Source of edge | Holding | Honest Sharpe* | Capacity | Solo-accessible? |
|---|---|---|---|---|---|
| **Trend / managed futures** | Behavioural underreaction + hedging flows; crisis alpha | Weeks–months | 0.3–0.6 | Very large ($300B+ industry) | **Yes** — best-documented, lowest infra barrier |
| **Cross-sectional equity factors** | Risk premia + behavioural | Monthly–annual | 0.3–0.5 pre-cost | Enormous in large caps, shrinks in small | **Yes** for research; hard to monetise long-short solo |
| **Mean reversion / stat arb** | Liquidity provision compensation | Minutes–days | 0.5–1.0 today (was 1.0–1.4 in the 90s–00s) | Modest, decays with size | **Partially** — daily-bar pairs yes; true high-turnover stat arb no |
| **Market making** | Spread + rebates, vs adverse selection | Seconds | 2–5 (masks tail risk) | Scales with volume, not capital | **No** in regulated equities/futures; **partially** in crypto |
| **Latency arb / HFT** | Being microseconds faster | Milliseconds | 3+ (survivorship-biased) | Winner-take-most | **No.** Structurally closed — see §2.1 |
| **Carry (FX / futures / crypto funding)** | Compensation for crash & liquidity risk | Weeks–months | 0.3–0.5 FX; 0.5–0.7 multi-asset | Large in FX/futures, small in crypto | **Yes** — crypto funding/basis is among the most realistic |
| **Event-driven / PEAD / merger arb** | Forced-seller behaviour + complexity premium | Days–months | 0.4–0.8, fat left tail | Deal-volume constrained | **Yes** for systematic PEAD |
| **Volatility / VRP / options selling** | Variance risk premium (real, documented) | Days–weeks | Looks 1.5–2.5 in calm periods; ~0.3–0.6 tail-adjusted | Bounded by tail risk borne | **Mechanically yes** — but the risk management *is* the strategy |
| **Alt-data / ML signals** | Informational or nonlinear-pattern advantage | Varies | **Scarce verified live evidence** | Data-cost constrained | **Marginally** — largest gap between claims and evidence |
| **Crypto arb (funding, basis, cross-exchange)** | Retail leverage imbalance + venue fragmentation | Continuous / seconds | Compressing fast | Moderate | **Yes** — but see §2.2 |

\* *Sharpe ranges are synthesised across secondary sources and should be treated as informed estimates, not citable figures. Verify against primary papers before any decision rests on them.*

### 2.1 Why HFT is genuinely closed, not just hard

Colocation runs $1,000–$5,000+/month **per venue**, plus microwave/laser links and FPGA hardware — setup in the hundreds of thousands to millions. Retail broadband plus a retail broker introduces latency measured in tens-to-hundreds of milliseconds, and brokers use "last look" to reject stale-priced orders. By the time a retail signal fires, the opportunity is gone. Anyone selling "latency arbitrage" as a retail strategy is selling marketing.

### 2.2 What has already compressed

Crypto cross-exchange and triangular arbitrage on major pairs is described by 2026 practitioners as *"mostly educational — build it to learn order-book mechanics, don't expect it to pay."* Funding-rate arb retains more capacity because it requires balance sheet across venues, but it is explicitly now "the institutional favourite," meaning you compete with better-capitalised players.

### 2.3 The factor zoo and the replication crisis

This is the field's own reckoning with data mining, and it is directly relevant to anyone planning to use ML on market data.

- **Harvey, Liu & Zhu (2016, RFS)** catalogued hundreds of published factors and argued that, given how many have been mined from overlapping data, the conventional **t > 2.0 threshold guarantees false positives**. They propose **t ≥ 3.0** for a new factor to be taken seriously, concluding *"most claimed research findings in financial economics are likely false."*
- **Hou, Xue & Zhang, "Replicating Anomalies"** tried to replicate ~450 documented anomalies with more careful methodology (value-weighted, microcap-controlled). **Over half failed to replicate.**
- **What survived:** value, momentum, quality/profitability show the most persistent cross-market, cross-asset replication. Size and low-volatility are weaker and regime/microcap-concentrated. The honest 2020s consensus (AQR, Robeco) is a small set of robust premia — value, momentum, quality, low-risk, carry, trend — and scepticism toward everything else.

### 2.4 Combining strategies is the only actual free lunch

Individual strategies carry idiosyncratic risk (trend whipsaws, carry crashes, value has multi-year drawdowns, short-vol has tails) that is **not highly correlated across families** — trend in particular tends to perform well precisely when equity factors and carry perform worst (2008, Q1 2020, 2022). Blending structurally uncorrelated strategies raises portfolio Sharpe **without requiring any additional edge discovery.** This is the only place in finance where diversification raises risk-adjusted expected return for free.

On weighting: naive equal-weight avoids estimation error but overweights high-vol strategies. Risk parity / inverse-vol is the institutional standard but needs stable vol and correlation estimates — and correlations spike toward 1 in exactly the crises where diversification is needed. Full Markowitz mean-variance optimisation is notoriously unstable and overfits historical correlations. Pragmatic middle: inverse-vol weighting plus an explicit correlation stress test (what does the book do if all pairwise correlations jump to 0.7?).

---

## 3. Why Backtests Lie — the most important section

> A backtest is not evidence. It is a *claim*, produced by a process — you, iterating on a dataset — that is structurally biased toward producing good-looking claims whether or not any edge exists. In software, a passing test suite means the code works. In markets, a passing backtest means, by base rate, that you found a pattern in noise.

### 3.1 The bias catalogue

| Bias | The subtle form that catches experienced people | Defence |
|---|---|---|
| **Lookahead** | Adjusted-close prices bake 2026 split/dividend adjustments into 2020 prices; *restated* fundamentals aren't what was reported at the time; today's index membership implies you knew in 2015 who'd survive | Point-in-time databases; *as-reported* fundamentals with realistic filing lag; reconstruct index membership from disclosed change dates |
| **Survivorship** | A "current NIFTY 500" list run back 20 years erases every delisting and bankruptcy — the exact tail events you need to test against | Survivorship-bias-free universes with delisting returns |
| **Data snooping / multiple testing** | Test 1,000 variants, pick the best in-sample Sharpe → you found the max of 1,000 noise draws. **Engineers are trained to iterate until something works, which is exactly the overfitting procedure.** | Pre-register hypothesis space; count *every* re-run as a trial; DSR/PBO |
| **Universe selection** | "Momentum works great on these 40 names" reverses cause and effect | Define universe by objective ex-ante criteria (liquidity, cap) |
| **Regime selection** | 2012–2021 flatters any long-biased or short-vol strategy | Test across 2000–02, 2008–09, 2020, 2022 separately and report conditionally |
| **Costs** | 15% raw return at 40x turnover dies at 5–10bps round trip; borrow is expensive exactly when the short is most attractive | First-class cost model, not a post-hoc haircut |
| **Capacity illusion** | Filling $50M of a $2M-ADV name at the close | Cap order size vs historical ADV; report the AUM where net alpha hits zero |
| **Signal-to-execution lag** | Trading at the same bar's close that generated the signal | Enforce ≥1 bar lag; fill against bid/ask, not mid |
| **Parameter instability** | 12 parameters tuned to max Sharpe with no economic story | Parsimony; sensitivity testing — does performance degrade gracefully or fall off a cliff? |

### 3.2 The statistical machinery

- **Deflated Sharpe Ratio** (Bailey & López de Prado) — adjusts observed Sharpe for number of trials, variance across trials, and non-normality. **Key result: with enough trials, no observed Sharpe is high enough to reject the null of no skill.** More backtests should make you trust a good result *less*.
- **Probability of Backtest Overfitting (PBO)** — combinatorially splits history, finds the in-sample optimum per combination, measures how often the in-sample winner underperforms out-of-sample. A resampled estimate of overfitting probability rather than a single split.
- **Combinatorial Purged Cross-Validation (CPCV)** — many train/test splits with **purging** (drop training rows whose label horizon overlaps the test window) and **embargoing** (buffer after the test window). Fixes the leakage that makes naive k-fold CV invalid on time series.
- **Harvey & Liu** — the t ≥ 3.0 hurdle and *haircut Sharpe*, discounting reported Sharpe by the number of tests implicitly run.
- **White's Reality Check / Hansen's SPA** — bootstrap tests asking "is the best of N rules significant given I searched over all N?" The statistical ancestors of DSR/PBO.
- **Minimum track record length** (Probabilistic Sharpe Ratio) — how many independent observations are needed to distinguish a Sharpe from zero. For realistic Sharpe (~1.0) with autocorrelation and non-normality, this is **years, not months.**
- **Walk-forward** — better than a single split, but its limit is that it's still sequential in-sample optimisation; you can tune the *walk-forward parameters themselves* until it looks good.
- **Why naive train/test weakens under iteration** — the first holdout is valid. The moment you look at the result, tweak, and re-check, the holdout has become part of your search. Serious shops keep a **sealed final holdout** unlocked exactly once, and count every earlier "OOS" check as in-sample.

**Criticism of López de Prado** (worth knowing, since he's the most-cited voice here): CPCV is computationally expensive and its assumptions are hard to satisfy; PBO is sensitive to partition count/width — a meta-level echo of the overfitting it targets; and much of *AFML* targets HFT/microstructure problems that don't cleanly generalise to lower-frequency work. Several techniques (meta-labelling's real lift, for instance) remain contested.

### 3.3 Transaction costs

Three layers: **spread** (half-spread crossing the book), **impact** (your order moves price against you), **timing/opportunity cost**. The standard impact heuristic is the **square-root law** — impact scales roughly with √(order size / ADV) × volatility, not linearly. **Almgren-Chriss (2000)** formalises the fast-vs-slow execution tradeoff (high impact / low drift risk vs low impact / more volatility exposure) into an efficient frontier of execution schedules.

Practical consequence: a large fraction of published "profitable" retail *and academic* strategies are high-turnover short-horizon signals that go marginal or negative under realistic half-spread plus square-root impact. **This is the most common single reason a strategy that backtests great is uninvestable — independent of any statistical overfitting.**

### 3.4 The live-vs-backtest evidence

- **August 2007 "quant quake"** — multiple market-neutral equity funds, unrelated by design but correlated by crowded positioning, suffered simultaneous unprecedented drawdowns as one fund's deleveraging forced correlated unwinds. No single-strategy backtest could see it: it was a multi-fund liquidity cascade, not a property of any return series.
- **Zillow Offers** (shut Nov 2021, ~$500M+ write-down) — the modern case of a well-resourced, data-rich, extensively backtested systematic pricing model failing in production when forecast error compounded with inventory and liquidity risk in a fast-changing regime.
- Standard reconciliation practice: continuous backtest-vs-live P&L attribution decomposing the gap into signal decay / cost-model error / execution slippage; staged capital with kill-switches; and treating live underperformance beyond predefined noise bands as an **automatic halt-and-diagnose trigger**, not something to wait out.

### 3.5 The retail evidence base

| Study | Finding |
|---|---|
| Barber & Odean (2000), *Trading Is Hazardous to Your Wealth* | Households that traded most underperformed buy-and-hold by ~6.5pp/year net of costs. Mechanism: turnover × costs |
| Chague, De-Losso & Giovannetti (2020), Brazil B3 | Of individuals who persisted day-trading futures 300+ days, **97% lost money**; the rare winners' gross gains are consistent with chance |
| Barber, Lee, Liu & Odean, Taiwan | Day traders as a group lose to costs before adverse selection; **<1% persistently profit** — but that minority shows real year-over-year skill persistence |
| SEBI, FY22–FY24 | **93% of individual F&O traders lost money**; aggregate losses >₹1.8 lakh crore |
| SEBI, FY25 | **91% still loss-making**; aggregate net losses **₹1.06 lakh crore**, up ~41% YoY; participant count fell ~20% after the F&O curbs |

**What these do and don't show.** They are strong, regulator-level, large-sample evidence that retail *discretionary and short-horizon* trading loses to costs and adverse selection. They do **not** directly prove systematic retail strategies fail at the same rate. But the underlying arithmetic — costs are real, counterparties are better informed, and the base rate of "found an edge" is low — is exactly the arithmetic any backtest is implicitly competing against.

### 3.6 The validation protocol, as ordered gates

1. **Data integrity** — point-in-time, survivorship-free, as-reported, reconstructed universe membership.
2. **Hypothesis pre-registration** — write down the logic and expected sign before touching full history; log every variant from that point.
3. **Sealed holdout** — carve out a final period never touched during development.
4. **Cost-realistic simulation** — spread + √-law impact at realistic size vs ADV + financing/borrow + ≥1-bar signal-to-execution lag.
5. **Multiple-testing correction** — DSR, Harvey-Liu-scaled t-hurdle, PBO/CPCV rather than a single split.
6. **Regime stress test** — report ≥3 structurally distinct regimes separately.
7. **Parameter sensitivity** — graceful degradation, not a cliff.
8. **Capacity estimate** — the AUM where net-of-impact expected return hits zero.
9. **Minimum track record length** — is the sample even long enough to distinguish this Sharpe from zero?
10. **Unlock the holdout — once.** If it fails, the strategy is rejected, not re-tuned.
11. **Staged live** — paper → small live with kill-switches → scaled, with continuous backtest-vs-live attribution.
12. **Decay monitoring** — rolling live-vs-backtest tracking with a predefined halt threshold.

---

## 4. The Stack

### 4.1 Backtesting engines — the honest 2026 state

The first architectural decision is **vectorised vs event-driven**, and most people pick wrong.

- **Vectorised** (whole series as arrays): fast, ideal for parameter sweeps and cross-sectional factor research; but easy to leak future information and awkward for path-dependent logic (sizing that depends on unrealised P&L, pyramiding, dynamic stops).
- **Event-driven** (bar-by-bar or tick-by-tick replay into a simulated broker): naturally lookahead-free, models queues/partial fills/slippage properly, and the same code often runs live; slow in pure Python, overkill for daily-bar factor studies.

**Rule of thumb:** vectorised for *research and screening*, then re-validate finalists in an *event-driven* engine before live capital — especially for intraday or options strategies where fills dominate P&L.

| Engine | Type | Status 2026 | Live path | Main criticism |
|---|---|---|---|---|
| **vectorbt** (OSS) | Vectorised, numba | OSS ~maintenance; dev moved to **vectorbt PRO** (~$25–30/mo) | No | Steep curve; cheap sweeps make overfitting easy; weak fill modelling |
| **backtrader** | Event-driven | **Frozen since ~2023**, breaks on newer pandas/numpy | Partial | No longer a safe long-term bet — fine for learning only |
| **zipline-reloaded** | Event-driven | Actively maintained (Py3.13/NumPy2) | No | US-equities-centric, awkward for options/futures/crypto |
| **QuantConnect LEAN** | Event-driven | Active; OSS core + hosted cloud + self-host Docker | **Yes** (IB, Tradier, Alpaca…) | Platform lock-in feel; C# core limits deep Python customisation |
| **NautilusTrader** | Event-driven, Rust core | **Active, releases through mid-2026** | **Yes** — same code path backtest→live | Heavier install, steeper curve; overkill for daily bars |
| **PyBroker** | Event-driven, ML-first | Active, smaller community | Alpaca | Small ecosystem |
| **Backtesting.py** | Event-driven, single-asset | Active | No | Hits design limits fast |
| **bt** | Vectorised, tree-based | Thin maintenance | No | Portfolio allocation research only |
| **Raw pandas/polars** | Either | n/a | n/a | Legitimate for cross-sectional factor work; risk is badly reinventing the bias/cost machinery frameworks already got right |

### 4.2 Data — tiers and why paying matters

| Tier | Options | Notes |
|---|---|---|
| Free | yfinance, Stooq, FRED | **yfinance has become genuinely unreliable** (rate-limit errors, breaking changes as Yahoo tightens anti-scraping). Prototyping only. FRED/Stooq are solid for what they cover |
| Cheap ($0–50/mo) | Alpha Vantage, Tiingo, Nasdaq Data Link | Thin history, sparse corporate-action handling on free tiers |
| Mid ($20–a few hundred/mo) | EODHD, **Polygon.io → rebranded "Massive" in early 2026** | Point-in-time fundamentals, proper adjustment |
| Serious | **Databento** (pay-as-you-go tick/order-book, good docs), **Norgate** (~$30–60/mo, gold standard for clean survivorship-free daily equity/futures) | Norgate is the common choice for serious retail systematic traders |
| Academic | CRSP / WRDS | The benchmark; institutional access only |
| Crypto | CCXT (free, 100+ venues), Tardis.dev, Kaiko | Tardis for normalised tick/order-book history |
| **India** | Zerodha Kite Connect (₹500/mo unlocks historical candles + WebSocket), TrueData, Global Datafeeds (GDFL) | NSE/BSE sell official data but enterprise-priced and clunky |

**Why point-in-time / survivorship-free / correct adjustment is worth paying for:** a current NIFTY 500 list run backwards silently excludes every delisting and merger, so your universe contains only winners. Today's *restated* fundamentals let a signal see the future. And corporate-action adjustment errors — splits, bonuses, very common in Indian equities — manufacture fake price jumps that any backtest will happily "trade" profitably. This is precisely what separates free scraped data from paid vendors.

### 4.3 Broker APIs

**India:** Zerodha **Kite Connect** (₹500/mo, most mature, best docs/community — de facto standard) · Upstox (free) · **Dhan** (free, most liberal published rate limits: 20 req/s non-trading, 10 order, 5 data, 1 quote) · Angel One SmartAPI (free) · Fyers (free) · 5paisa Xstream · Groww (new, maturing) · AliceBlue.

**OpenAlgo** (open-source, AGPL-3.0, self-hosted) is a unified abstraction layer over most Indian brokers — worth adopting early rather than hand-rolling broker adapters.

**International:** Interactive Brokers (via **ib_async**, the maintained successor to the now-unmaintained ib_insync) is the most capable multi-asset API for an individual · Alpaca is the easiest onramp · Tradier for options.

### 4.4 Research infrastructure

- **Data lake:** Parquet + **DuckDB and/or Polars** is the 2026 default for a solo quant — no server, columnar, fast enough for single-machine tick-to-daily. DuckDB for ad-hoc SQL joins, Polars for pipelines.
- **Postgres/TimescaleDB** once you need concurrent writers and a system-of-record for live positions/orders. **ClickHouse** for very high-throughput analytics. **kdb+** is the institutional HFT standard but rarely justified below prop-shop scale.
- **Experiment tracking:** MLflow or W&B transplant well — log parameters, backtest metrics, and artefact versions per run, with git-committed strategy code and a fixed seed/data-snapshot policy.
- **"Notebook rot"** — stale hidden state, un-versioned data pulls, results irreproducible six months later — is *the* most common solo-researcher failure. Fix: promote anything load-bearing out of notebooks into versioned modules with data snapshots tagged by pull date.

### 4.5 Language and latency reality

Python is fine for signal research, portfolio construction, order routing, and anything on daily/hourly/minute bars — the large majority of solo systematic work. **Numba** when vectorised sweeps get too slow. **Rust** (PyO3, or adopting Nautilus's core) for tick-level/order-book simulation or market making. True colocated C++ HFT is irrelevant when trading through a retail broker API with 50–500ms round trips — **do not over-engineer for a latency tier you cannot access.**

### 4.6 2025–26 developments

Polygon.io → Massive rebrand. ib_insync → ib_async. NautilusTrader consolidating as the leading OSS research-to-live engine. OpenAlgo emerging in India. And a real wave of **LLM/agent-assisted quant research** (arXiv work on multi-agent strategy discovery, LLM-driven factor generation) — genuinely useful for idea generation, code scaffolding, and literature synthesis, but **nothing that reliably replaces walk-forward validation.** Treat LLM-generated strategies with the same or more scepticism as any other overfitting-prone backtest output.

---

## 5. India-Specific Reality

*Two items here were independently re-verified because they materially change what is worth building.*

### 5.1 SEBI retail algo framework — **fully mandatory since 1 April 2026** ✅ verified

Foundational circular SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013 dated **4 Feb 2025**. Go-live slipped twice (1 Aug 2025 → 1 Oct 2025 → phased glide path with milestones through Jan 2026) and became **universally mandatory on 1 April 2026**. Confirmed against Fyers, Zerodha, and Angel One implementation notices.

**Categories:** *white-box* (logic disclosed and replicable by the user) vs *black-box* (opaque — stricter empanelment/disclosure obligations on the provider).

**The operative rules:**

| Rule | Detail |
|---|---|
| **10 orders/second per exchange** | The bright line. At or below → **no exchange registration, no unique algo ID required.** Above → algo must be registered with the exchange and tagged with an exchange-issued unique algo ID |
| **Static IP whitelisting** | **Mandatory** for all API order placement — one primary + one backup IP registered with the broker |
| **Auth** | OAuth-based, mandatory 2FA, **daily forced session logout** (no continuous refresh-token sessions) |
| **Market protection** | Compulsory % band around LTP on API market orders; zero market-protection disallowed; market orders auto-convert to MPP |
| **Broker obligations** | Exchange approval per algo; routing only through empanelled algo providers; full liability for grievances and order-level monitoring |
| **Family/HUF** | Multiple family members may share one static IP if mapped to distinct API keys |
| **Audit** | All algo orders tagged regardless of registration; exchanges can terminate rogue algos |

**What this means for you, by activity:**

| Activity | Regulatory position |
|---|---|
| Research and backtest only | **No trigger at all.** Outside SEBI's order-flow jurisdiction |
| Run your own self-written algo on your own capital, <10 orders/sec | **Allowed**, no exchange registration — but requires static IP registered with your broker, OAuth/2FA, market-protection settings, and an empanelled broker API (not a scraped/unofficial route) |
| Exceed 10 orders/sec | Exchange registration + unique algo ID required |
| **Share or sell a strategy to others** | **The line moves sharply.** You become an "algo provider": exchange empanelment via a broker, technical/commercial disclosure, **hosting on Indian servers**, 5-year audit logs, cybersecurity norms. SEBI Investment Adviser / Research Analyst registration may *also* be triggered depending on structure — **this overlap is genuinely unsettled** |

**Flagged as unresolved:** individual-level penalty mechanics for breaching the threshold post-April-2026 are thinly documented publicly.

### 5.2 The cost stack — **STT was hiked again effective 1 April 2026** ✅ verified

This is the single biggest determinant of whether a high-turnover systematic strategy is viable in India, and it just got materially worse.

| Instrument | Pre-Oct 2024 | Oct 2024 | **From 1 Apr 2026** |
|---|---|---|---|
| Equity futures (sell) | 0.0125% | 0.02% | **0.05%** |
| Equity options | 0.0625% on premium | 0.1% on premium | **0.15%** — and on exercise as well as premium |
| Equity delivery | 0.1% buy + 0.1% sell | unchanged | unchanged |
| Intraday equity (sell) | 0.025% | unchanged | unchanged |

Futures STT is now **4x its pre-Oct-2024 level**; options STT **2.4x**. Stated government rationale: curbing retail F&O speculation. On top of STT sit exchange transaction charges, state stamp duty (~0.002–0.003% buy side), GST on brokerage and charges, and SEBI turnover fees.

**The implication is structural, not incremental:** turnover is now taxed hard enough in Indian derivatives that any strategy whose edge is smaller than the round-trip cost stack is dead on arrival — and the cost stack is a *policy variable that has moved against high-turnover traders twice in two years.* Low-turnover strategies (delivery equity, multi-day holds) are comparatively far less affected.

### 5.3 Market structure changes to know

- **Weekly expiries rationalised** (from 20 Nov 2024): one weekly benchmark index per exchange — NSE: Nifty 50 only; BSE: Sensex only. Bank Nifty, Fin Services, Midcap Select, Next 50, Bankex, Sensex 50 weeklies **discontinued**.
- **Lot sizes raised** (21 Nov 2024, min contract value ₹15–20 lakh): Nifty 50 25→75, Bank Nifty 15→30, Fin Services 25→65.
- Upfront option-premium collection from buyers; +2% Extreme Loss Margin on short options on expiry day; calendar-spread margin benefit removed on expiry day (Feb 2025); **intraday** position-limit monitoring replacing end-of-day (Apr 2025).
- **Settlement:** cash market T+1; **T+0 optional beta** running on a limited scrip list since Mar 2024, mainstreaming timeline **still not fixed**.
- **Peak margin regime** (100% upfront SPAN+exposure) remains in force — high intraday leverage is gone versus the pre-2021 era.

### 5.4 Taxation (factual, not tax advice)

- **F&O** = non-speculative business income. **Intraday cash equity** = speculative business income. **Delivery equity** = capital gains (STCG 20%, LTCG 12.5% post-July-2024).
- **Crypto/VDA:** flat **30%**, **no deductions except cost of acquisition**, **no loss set-off or carry-forward** (not across VDAs, not against other heads), plus **1% TDS under s.194S** on every transfer above threshold. This structure alone makes active algorithmic crypto trading in India economically brutal — a strategy with a 60% win rate can be net-negative after tax because losers aren't deductible against winners.

### 5.5 Crypto and forex legality — the thing people get wrong

**Crypto:** No outright ban, no comprehensive law — a genuine grey zone. The 2021 draft ban bill was never tabled and remains shelved. As of **July 2026, RBI still publicly favours prohibition**, citing tax-evasion and capital-flight concerns, while a government framework remains stalled. The VDA tax regime above is unchanged. *Treat any "upcoming bill" claim with scepticism — this is unresolved.*

**Forex — the common misconception:**

| Legal | Not legal |
|---|---|
| Exchange-traded currency derivatives on NSE/BSE/MSE — INR pairs (USD-INR, EUR-INR, GBP-INR, JPY-INR) and select crosses (EUR-USD, GBP-USD, USD-JPY), traded and **settled in INR** through SEBI-registered brokers | **Offshore/overseas forex brokers** — MT4/MT5 CFD platforms, leveraged spot forex. Prohibited for residents under FEMA; RBI does not permit LRS remittance for speculative forex margin and maintains a public **Alert List** of unauthorised platforms |

Penalties for FEMA contravention run to 3x the amount involved (or ₹2 lakh flat), with potential PMLA exposure. People routinely conflate the two columns — they are not the same thing.

---

## Sources

**Lifecycle & architecture**
- [How Quant Hedge Funds Actually Build and Vet Trading Signals](https://youngandcalculated.substack.com/p/how-quant-hedge-funds-actually-build)
- [My Experiences as a Quantitative Developer in a Hedge Fund — QuantStart](https://www.quantstart.com/articles/My-Experiences-as-a-Quantitative-Developer-in-a-Hedge-Fund/)
- [A Modular Architecture for Systematic Quantitative Trading Systems](https://hiya31.medium.com/a-modular-architecture-for-systematic-quantitative-trading-systems-2a8d46463570)
- [WorldQuant BRAIN](https://www.worldquant.com/brain/)
- [The Rise and Fall of Quantopian](https://whatworksintrading.substack.com/p/the-rise-and-fall-of-quantopian-lessons)
- [3 Takeaways from Quantopian Shutting Down — QuantRocket](https://www.quantrocket.com/blog/quantopian-shutting-down/)
- [Alpha Decay: what does it look like? — Maven Securities](https://www.mavensecurities.com/alpha-decay-what-does-it-look-like-and-what-does-it-mean-for-systematic-traders/)
- [Quantitative Finance Reading List — QuantStart](https://www.quantstart.com/articles/Quantitative-Finance-Reading-List/)
- [Does Meta Labeling Add to Signal Efficacy? — Hudson & Thames](https://hudsonthames.org/does-meta-labeling-add-to-signal-efficacy-triple-barrier-method/)

**Strategy families**
- [A Century of Evidence on Trend-Following Investing — AQR](https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing)
- [Demystifying Managed Futures — AQR](https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/Demystifying-Managed-Futures.pdf)
- [Carry — Koijen, Moskowitz, Pedersen, Vrugt](https://jacobslevycenter.wharton.upenn.edu/wp-content/uploads/2014/06/Carry.pdf)
- [The Carry Trade: Risks and Drawdowns — NBER](https://www.nber.org/system/files/working_papers/w20433/w20433.pdf)
- [Statistical Arbitrage in the U.S. Equities Market — Avellaneda & Lee](https://www.tandfonline.com/doi/abs/10.1080/14697680903124632)
- [The Variance Risk Premium is Pervasive — Alpha Architect](https://alphaarchitect.com/the-variance-risk-premium-is-pervasive/)
- [Replicating Anomalies — Hou, Xue, Zhang (NBER)](https://www.nber.org/system/files/working_papers/w23394/w23394.pdf)
- [Factor investing – going beyond Fama and French — Robeco](https://www.robeco.com/en-us/insights/2020/11/factor-investing-going-beyond-fama-and-french)
- [Is Latency Arbitrage Still Possible in 2026? — EBC](https://www.ebc.com/forex/is-latency-arbitrage-still-possible-in-2026)
- [The crypto arbitrage playbook: what still pays in 2026 — CCXT](https://docs.ccxt.com/blog/crypto-arbitrage-strategies)
- [Micro cap – the edge of hedge — The Hedge Fund Journal](https://thehedgefundjournal.com/micro-cap-the-edge-of-hedge/)

**Validation & failure modes**
- [Bailey & López de Prado, The Deflated Sharpe Ratio (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551)
- [The Probability of Backtest Overfitting (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253)
- [Harvey, Liu & Zhu, …and the Cross-Section of Expected Returns (RFS)](https://academic.oup.com/rfs/article/29/1/5/1843824)
- [Probabilistic Sharpe Ratio & Minimum Track Record Length — Portfolio Optimizer](https://portfoliooptimizer.io/blog/the-probabilistic-sharpe-ratio-bias-adjustment-confidence-intervals-hypothesis-testing-and-minimum-track-record-length/)
- [The Dangers of Backtesting — Portfolio Optimization Book](https://portfoliooptimizationbook.com/book/8.3-dangers-backtesting.html)
- [Almgren & Chriss, Optimal Execution of Portfolio Transactions](https://www.smallake.kr/wp-content/uploads/2016/03/optliq.pdf)
- [What happened to the quants in August 2007? — ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1386418110000261)
- [McLean & Pontiff, Does Academic Research Destroy Stock Return Predictability? — JoF](https://onlinelibrary.wiley.com/doi/10.1111/jofi.12365)
- [Barber & Odean, Trading Is Hazardous to Your Wealth](http://faculty.haas.berkeley.edu/odean/papers/returns/individual_investor_performance_final.pdf)
- [Chague, De-Losso & Giovannetti, Day Trading for a Living? (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3423101)
- [Barber, Lee, Liu & Odean, The Cross-Section of Speculator Skill](https://faculty.haas.berkeley.edu/odean/papers/day%20traders/The%20Cross-Section%20of%20Speculator%20Skill.pdf)
- [A Taxonomy of Backtest Lies](https://www.susanpotter.net/quant/backtest-bias-taxonomy/)
- [Using point-in-time data to avoid bias in backtesting — Refinitiv](https://perspectives.refinitiv.com/future-of-investing-trading/how-to-use-point-in-time-data-to-avoid-bias-in-backtesting/)

**Stack**
- [Python Backtesting Frameworks (2026): 7 Compared Honestly](https://quanttradingtools.com/python-backtesting-frameworks/)
- [NautilusTrader (GitHub)](https://github.com/nautechsystems/nautilus_trader) · [Live trading docs](https://nautilustrader.io/docs/latest/concepts/live/)
- [zipline-reloaded (GitHub)](https://github.com/stefan-jansen/zipline-reloaded)
- [Is Backtrader dead? — Backtrader Community](https://community.backtrader.com/topic/3702/is-backtrader-dead)
- [QuantConnect Pricing](https://www.quantconnect.com/pricing/) · [VectorBT PRO](https://vectorbt.pro/features/overview/)
- [yfinance rate-limiting discussion](https://github.com/ranaroussi/yfinance/discussions/2431)
- [Polygon.io is now Massive](https://massive.com/blog/polygon-is-now-massive)
- [Quant Data Provider Comparison: Databento, Massive, EODHD, Barchart](https://waylandz.com/quant-book-en/Data-Provider-Comparison/)
- [Norgate Data](https://norgatedata.com/) · [TrueData](https://www.truedata.in/) · [Global Datafeeds pricing](https://globaldatafeeds.in/global-datafeeds-apis/global-datafeeds-apis/pricing-sales/api-pricing/)
- [OpenAlgo (GitHub)](https://github.com/marketcalls/openalgo) · [ib_async (GitHub)](https://github.com/ib-api-reloaded/ib_async)
- [Time-Series Databases for Quant: kdb+, ClickHouse, InfluxDB](https://www.techinterview.org/post/3233474600/time-series-databases-quant/)
- [QuantEvolve: Multi-Agent Evolutionary Strategy Discovery (arXiv)](https://arxiv.org/html/2510.18569v1)

**India**
- [SEBI Circular — Safer participation of retail investors in Algorithmic trading (4 Feb 2025)](https://www.cse-india.com/upload/upload/Feb_042025.pdf)
- [SEBI — Extension of timeline (30 Sep 2025)](https://www.sebi.gov.in/legal/circulars/sep-2025/extension-of-timeline-for-implementation-of-sebi-circular-dated-february-04-2025-on-safer-participation-of-retail-investors-in-algorithmic-trading-_96979.html)
- [Fyers — New SEBI framework for retail algo trading from 1 April 2026](https://fyers.in/notice-board/new-sebi-framework-for-retail-algo-trading-from-april-01-2026/)
- [Zerodha — SEBI algo trading changes, April 2026](https://inthemoneybyzerodha.substack.com/p/sebi-algo-trading-changes-april-2026)
- [Angel One — SmartAPI access changes from 1 April 2026](https://www.angelone.in/news/market-updates/what-s-changing-in-angel-one-s-smartapi-access-from-april-1-2026)
- [Zerodha — Comprehensive overview of NSE's retail algo circular](https://zerodha.com/z-connect/general/a-comprehensive-overview-of-nses-circular-on-the-new-retail-algo-trading-framework)
- [ICICI Direct — Orders-per-second threshold FAQ](https://www.icicidirect.com/faqs/fno/how-many-orders-per-second-are-allowed-before-a-strategy-has-to-be-classified-as-an-algo)
- [IRCCL — The unfinished business of black-box regulation](https://www.irccl.in/post/retail-algo-trading-under-sebi-s-lens-the-unfinished-business-of-black-box-regulation)
- [Kite Connect](https://zerodha.com/products/api/) · [Dhan API rate limits](https://dhan.co/support/platforms/dhanhq-api/what-are-the-api-rate-limits-for-dhan/) · [AlgoTest — Best brokers for algo trading in India 2026](https://algotest.in/blog/best-brokers-for-algo-trading-in-india/)
- [ClearTax — Securities Transaction Tax, new F&O rates](https://cleartax.in/s/securities-transaction-tax-stt)
- [HDFC Bank — Union Budget 2026: STT hike on F&O trading](https://www.hdfc.bank.in/blogs/union-budget/stt-hike-on-f-o-trading)
- [1 Finance — Budget 2026 hikes STT on futures and options](https://1finance.co.in/blog/stt-futures-options-increased-budget-2026-for-fno-investors/)
- [Zerodha — SEBI's new index derivatives rules](https://zerodha.com/z-connect/business-updates/sebis-new-rules-for-index-derivatives-heres-whats-changing)
- [NSE — T+0 Settlement Cycle](https://www.nseindia.com/static/products-services/t0-settlement-cycle)
- [SEBI — 93% of individual F&O traders incurred losses FY22–FY24](https://www.sebi.gov.in/media-and-notifications/press-releases/sep-2024/updated-sebi-study-reveals-93-of-individual-traders-incurred-losses-in-equity-fando-between-fy22-and-fy24-aggregate-losses-exceed-1-8-lakh-crores-over-three-years_86906.html)
- [Business Standard — Net losses of F&O traders widen in FY25](https://www.business-standard.com/markets/news/net-losses-of-traders-in-fo-widens-in-fy25-sebi-study-125070701221_1.html)
- [CoinDesk/Reuters — RBI still favours crypto prohibition (July 2026)](https://www.coindesk.com/policy/2026/07/08/reserve-bank-of-india-still-favors-crypto-prohibition-to-curtail-tax-evasion-reuters)
- [InCred Money — Is forex trading legal in India? RBI/FEMA rules](https://www.incredmoney.com/knowledge-center/trading-account/is-forex-trading-legal-in-india-rbi-guidelines-explained/)
