# The Market Observatory — Scope & Decision Record

*Locked 2026-08-12. Phase 2 of Algo_Finance. This is an **observation** layer, not a strategy. Amend this file when scope changes; do not let scope drift silently.*

---

## 1. What this is

A system that studies how the Indian market and its macro drivers actually move — across equities, commodities, FX, rates, volatility and institutional flows — at **daily and weekly** frequency.

It produces **descriptions and answers to named questions**. It does not produce signals, forecasts, positions or orders.

**Why this first.** It carries no overfitting risk (nothing is being fitted), no capital risk, and its data layer *is* the foundation of the validation harness in `CLAUDE.md` §6.3. It also generates the evidence needed to close open decision §5.1 (which market to actually work in).

---

## 2. Instruments — locked

### 2.1 Indian equity

| Instrument | Role | Candidate ticker | Status |
|---|---|---|---|
| Nifty 50 | Broad large-cap benchmark | `^NSEI` | ✅ |
| Nifty Bank | Sector concentration, high beta, rates-sensitive | `^NSEBANK` | ✅ |
| Nifty IT | Dollar-earner — natural inverse exposure to USDINR | `^CNXIT` | ✅ |
| Nifty Midcap | Size/breadth dimension; behaves differently in stress | TBD | ⚠️ verify ticker |

**Dropped:** Sensex — ~0.98 correlated with Nifty 50, near-zero incremental information. May be re-added later purely as a data-quality cross-check.

### 2.2 Volatility & rates

| Instrument | Role | Candidate source | Status |
|---|---|---|---|
| India VIX | **The regime variable.** Most statements about market behaviour are conditional on vol state | `^INDIAVIX` | ✅ |
| India 10Y G-Sec yield | Bank Nifty is a rates trade; no rates series = no explanation | NSE / CCIL / FRED | ⚠️ needs source |

### 2.3 Institutional flows

| Instrument | Role | Source | Status |
|---|---|---|---|
| FII net (cash) | Arguably *the* dominant medium-horizon driver of Nifty | NSE (free, scraped) | ⚠️ needs source |
| DII net (cash) | The domestic offset to FII | NSE (free, scraped) | ⚠️ needs source |

The distinctively Indian series. Free, but not available via a clean API — needs a dedicated fetcher.

### 2.4 Commodities

Held in **two denominations**, per §4 below.

| Commodity | USD reference | INR reference |
|---|---|---|
| Gold | `GC=F` (COMEX) / XAU | MCX gold — ⚠️ needs source |
| Silver | `SI=F` | MCX silver — ⚠️ needs source |
| Crude | `BZ=F` (Brent, India's import benchmark) + `CL=F` (WTI) | MCX crude — ⚠️ needs source |
| Copper | `HG=F` | MCX copper — ⚠️ needs source |

### 2.5 FX

Sourced from **FRED H.10** (Federal Reserve), not Yahoo — see §4.5 for the measured reason. Every H.10 rate is snapped at noon ET, so cross-FX relationships are internally consistent. Cost: a few days' publication lag.

| Pair | Role | Source | Series |
|---|---|---|---|
| USD/INR | The core India variable | FRED | `DEXINUS` |
| EUR/USD | Largest DXY component | FRED | `DEXUSEU` |
| USD/JPY | Global carry / risk barometer; yen-carry unwinds hit EM hard | FRED | `DEXJPUS` |
| USD/CNY | China proxy — drives copper and the EM-Asia bloc (onshore, not CNH) | FRED | `DEXCHUS` |
| DXY (ICE) | The market-standard dollar index — six currencies, euro-heavy | yfinance | `DX-Y.NYB` |
| Fed Broad Dollar | Trade-weighted across 26 currencies **including INR and CNY** — the more India-relevant dollar measure | FRED | `DTWEXBGS` |

Both dollar indices are kept: they answer different questions. `DX-Y.NYB` was verified healthy and is unaffected by the §4.5 defect.

### 2.6 Global context *(added — flagged as a scope addition)*

Not subjects of study, but **required** to answer "is India idiosyncratic or just global beta?" Without a global benchmark, several questions in §3 are unanswerable.

| Instrument | Role | Ticker |
|---|---|---|
| S&P 500 | Global equity beta reference | `^GSPC` |
| CBOE VIX | Global vol reference, to separate India-specific vol | `^VIX` |

---

## 3. The question bank

**Rule: no component gets built unless it answers a question on this list.** This is the defence against building a beautiful dashboard that answers nothing. Add questions freely; do not add features freely.

### A — Internal equity structure
- **A1.** How correlated are Nifty and Bank Nifty, and does that break down in stress?
- **A2.** Is the Nifty IT / USDINR hedge real? How strong, and does it hold in both directions?
- **A3.** Does Midcap-vs-Nifty breadth behave differently going *into* drawdowns than out of them?
- **A4.** Is Bank Nifty actually a rates trade? What is the sign against the 10Y, and is it stable?

### B — Currency
- **B1.** Does USDINR lead Nifty, lag it, or neither?
- **B2.** Is USDINR mostly a dollar story (DXY) or an India story? Decompose it.
- **B3.** Does USDJPY carry stress transmit into Indian equities?

### C — Commodities
- **C1.** How much of Indian gold's move is currency versus metal?
- **C2.** Do copper and oil lead Indian equities, or is that folklore?
- **C3.** Does crude matter *more* to India than to global equities? (India imports ~85% of its crude — if the relationship is real it should show up as a differential, not just a correlation.)
- **C4.** Do the gold/silver and copper/gold ratios say anything about Indian equities?
- **C5.** *(Deferred — needs real MCX data)* What drives the MCX-vs-global basis: duty changes, import curbs, festival demand?

### D — Volatility & regime
- **D1.** What does the market actually do when India VIX is in its top decile?
- **D2.** Is Indian volatility idiosyncratic, or just global vol beta?
- **D3.** **Do correlations across this whole set converge in stress?** (Directly tests `CLAUDE.md` §4.6 — the "free lunch" only exists if they don't.)

### E — Flows
- **E1.** Do FII flows *lead* Nifty, or merely follow it? (Widely assumed to lead; often contemporaneous.)
- **E2.** Do DII flows offset FII flows, and does that measurably dampen drawdowns?

### F — Calendar
- **F1.** Is there a persistent expiry-week effect after the November 2024 rule changes?
- **F2.** Is there real seasonality — budget, monsoon, festival gold demand?

### G — The meta question
- **G1.** **Within this entire set, what is genuinely uncorrelated to Indian equities?** The single most valuable output. This is the free lunch of `CLAUDE.md` §4.6, measured rather than assumed.

### H — Equity derivatives *(added 2026-09-28, `research/04`)*
- **H1.** Is India VIX systematically above subsequently realised Nifty volatility — is there a measurable variance risk premium, and does it vanish in stress? *(Answerable now: both series are in the panel.)*
- **H2.** How do the Nifty futures basis and open interest behave through the expiry cycle? *(Needs F&O bhavcopy.)*
- **H3.** Did the Nov 2024 expiry rationalisation and the Apr 2026 STT hike measurably change F&O volume and open interest? *(Needs F&O bhavcopy; overlaps F1.)*

### I — IPOs *(added 2026-09-28, `research/04`; all need an IPO dataset — study-first, source TBD)*
- **I1.** What does the distribution of listing-day returns look like, mainboard vs SME, and how has it shifted over time?
- **I2.** How much of the listing-day return does subscription explain — QIB versus retail multiples — and does anything explain what happens *after* listing?
- **I3.** What happens to price around anchor-investor lock-in expiry?
- **I4.** Do Indian IPOs underperform over 1–3 years after listing — the classic long-run result — and does that differ by segment?

---

## 4. Known traps and the policy for each

### 4.1 Timezone contamination — the sneaky one
Indian equities close **15:30 IST**. COMEX gold, Brent, DXY and the S&P trade nearly around the clock. A naive daily close-to-close join stamps the *post*-Indian-close US session onto the same calendar date, manufacturing convincing but fake lead-lag in **both** directions.

**Policy:**
1. Prefer **weekly bars** for cross-asset work — contamination is proportionally far smaller.
2. For any daily lead-lag result, report **both** same-day and lagged alignment. A relationship that only exists same-day is presumed to be an artifact until proven otherwise.
3. Never report a daily same-day cross-session correlation without this caveat attached.

### 4.2 Commodity denomination — the definitional trap
MCX gold in INR is arithmetically a blend of USD gold and USDINR. Correlating the two produces a strong relationship that is **true by construction**, not a market insight.

**Policy:** carry both denominations, and label the INR series honestly:
- **Synthetic INR** (`USD price × USDINR`) — legitimate for **C1** (currency-vs-metal decomposition), because that question *is* the decomposition. Clearly marked as synthetic.
- **Real MCX** — required for **C5** (basis/premium). Until real MCX data is sourced, **C5 stays deferred and unanswerable.** The synthetic series has a basis of exactly zero by construction and must never be used for it.

### 4.3 Calendar and missing-data handling
NSE, US and MCX holiday calendars all differ.

**Policy:** pairwise intersection of trading days, not a global intersection across all instruments (a global intersection discards too much history). **Never forward-fill prices before computing returns** — it injects artificial zero-return days and biases correlation estimates downward.

### 4.4 Scope drift
The failure mode is sliding from "analysis" to "what if I traded this." Crossing that line without the validation harness makes every output untrustworthy.

**Policy:** signals, forecasts, backtests, position sizing and orders are **out of scope**, full stop. When a question starts smelling like a signal, it gets written into a backlog file — not built here.

### 4.5 Yahoo `=X` spot FX is unusable at daily frequency — measured, 2026-08-12
`research/01` §4.2 flagged yfinance as degraded in general. The observatory's integrity checks located the specific defect, and it sat directly on the headline question **B1**.

**Evidence:**

| Test | Yahoo `=X` | FRED H.10 | Expected |
|---|---|---|---|
| EUR/USD vs DXY, daily | **−0.34** | **−0.84** | ~−0.85 |
| USD/JPY vs DXY, daily | +0.20 | +0.40 | positive |
| `Close == Open` share | USDINR **40%**, EURUSD 23% | n/a | ~0% |
| The two sources vs each other, daily | r = **+0.30 to +0.38** | | ~+1.00 |

The correlation splits across two adjacent days (lag 0 = −0.34, lag +1 = −0.40), which is the signature of an inconsistent intraday snapshot rather than a fixed timestamp offset — so it cannot be corrected by shifting. It also worsened over time: EUR/USD vs DXY was −0.57 in 2005–10 and ~−0.08 from 2011 on.

**Resolution:** FRED H.10 is primary for all spot FX. The `=X` series are retained as `*_yf` context only, as the evidence exhibit and as a weekly fallback.

**The finding that vindicates the weekly-first policy:** resampled weekly, the Yahoo series *recovers completely* — EUR/USD vs DXY weekly is **−0.824** on Yahoo versus **−0.814** on FRED. The defect is intraday-snapshot noise that averages out. Choosing weekly as the primary frequency was the right call for a reason that had not yet been discovered when it was made.

### 4.6 Zero-return days in managed currencies are real history, not bad data
The gap check initially fired on USD/INR (22% zero-return days) and USD/CNY (33%). Investigation showed these are concentrated **before 2005**: the CNY was hard-pegged at 8.2765 until July 2005, and the RBI managed the rupee far more tightly then. Post-2005 the figures fall to 2–4% and 5–7%.

**Policy:** integrity checks run from **2008-03-03**, the observatory's actual usable window. A check scoped to full history fires on real history; scoped to the analysis window it fires on real bugs. Confirmed immaterial anyway — B1's correlation moves from −0.3929 to −0.3967 when zero-days are excluded.

---

## 5. Build layers

| Layer | Content | Status |
|---|---|---|
| **0 — Data spine** | Instrument registry, daily + weekly bars, alignment policy, parquet store, snapshot-dated pulls, integrity checks | ✅ **done, verified** |
| **1 — Descriptive** | Returns, rolling vol, drawdowns, distribution stats | not started |
| **2 — Cross-asset structure** | Rolling correlations at multiple windows, lead-lag, correlation stability under stress | not started |
| **3 — Regime** | Vol state, trend state, correlation state — **descriptive classification only** | not started |
| **4 — Report** | A weekly output that actually gets read | not started |

### Layer 0 as built

```
observatory/
├── config/instruments.yaml    27 instruments — the only place tickers live
├── obs/
│   ├── registry.py            load + validate; selectors incl. answering('C1')
│   ├── store.py               snapshot-dated parquet: raw/<key>/<date>.parquet
│   ├── fetch.py               yfinance + FRED fetchers
│   └── panel.py               alignment, derived series, returns, weekly resample
├── build.py                   fetch + rebuild curated panels
├── checks.py                  integrity checks — run after every build
└── data/raw|curated/
```

**Verified state:** 20 fetched + 4 derived = 24 series. Usable window **2008-03-03 → 2026-08-07**, spanning the 2008 GFC, the 2013 taper tantrum, 2020 COVID and the 2022 rate shock. All integrity checks pass.

`checks.py` asserts relationships whose sign and magnitude are known *before* looking at the data — a misaligned panel still produces numbers, but not numbers that pass these. It is what caught §4.5 and §4.6.

---

## 6. Open items

| # | Item | Blocks | Status |
|---|---|---|---|
| 1 | Nifty Midcap — currently `^NSEMDCP50` (Midcap **50**). Midcap 150 preferred for breadth; not available on the free source | A3 | open, low priority |
| 2 | India 10Y G-Sec daily series | A4 | **open** |
| 3 | FII/DII daily net flows — needs a dedicated NSE fetcher | E1, E2 | **open** |
| 4 | Real MCX commodity prices | C5 | **open** |
| 5 | Primary data vendor | all | ✅ resolved — FRED for FX and macro, yfinance for indices and futures. See §4.5 |

Items 2–4 are all Indian-specific series with no clean free API. They are the natural next unit of work and they unblock 5 of the 20 questions (A4, C5, E1, E2, plus depth on A3).

---

## 7. Log

| Date | Entry |
|---|---|
| 2026-08-12 | Scope proposed, revised and locked. Sensex dropped. Nifty IT, India VIX, Midcap, 10Y, FII/DII added. FX widened to 5 pairs. Global context pair added to make D2/C3 answerable. Question bank established at 20 questions. Python 3.14.2 venv created; pandas 3.0.5 / numpy 2.5.2 / pyarrow / duckdb / yfinance installed. |
| 2026-08-12 | **Layer 0 built and verified.** Registry, snapshot store, yfinance + FRED fetchers, panel alignment, integrity checks. Integrity checks then found two data faults: Yahoo `=X` spot FX unusable daily (§4.5, resolved by moving FX to FRED H.10) and apparent zero-return gaps that proved to be genuine pegged-currency history (§4.6, resolved by scoping checks to the analysis window). 24 series, 2008-03-03 → 2026-08-07, all checks passing. No analysis run yet. |
| 2026-09-28 | **Re-prioritised after `CLAUDE.md` §5 closed** (`research/04`). Subjects narrow to Indian equities, India VIX + equity derivatives, flows and IPOs. Commodities, FX and global instruments stay in the registry as **context** (they still answer D2, C3, G1) — nothing removed. Question bank grows from 20 to 27: **H1–H3** (derivatives) and **I1–I4** (IPOs). Layer 4 ("a report that gets read") becomes the first half of the Phase 3 Streamlit dashboard. |
