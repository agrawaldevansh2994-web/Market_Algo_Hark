# Market & Data Patterns — Running Log

*A dated log of empirical findings — things discovered by running the observatory, not designed in advance. Distinct from `02-observatory-scope.md`, which is scope, methodology and policy (what we decided to do). This file is what we found.*

*Two kinds of entry will accumulate here: data-quality patterns (how the sources behave — that's all we have so far, since only Layer 0 exists) and, once Layers 1–4 are built, actual market-behaviour patterns (correlation structure, lead-lag, regime effects). Each entry should be falsifiable and dated — if a later finding contradicts an earlier one, add a new entry rather than editing the old one, so the log stays a true history.*

---

## 2026-08-12 — Yahoo's spot FX quotes (`=X`) are unusable at daily frequency

**Finding.** yfinance's `USDINR=X`, `EURUSD=X` etc. produce daily bars whose `Close` is frequently identical to `Open` (40% of days for USDINR, 23% for EURUSD) and whose cross-pair correlations are roughly half their true value.

**Evidence.**

| Test | Yahoo `=X` | FRED H.10 | Expected |
|---|---|---|---|
| EUR/USD vs DXY, daily correlation | **−0.34** | **−0.84** | ≈ −0.85 |
| USD/JPY vs DXY, daily correlation | +0.20 | +0.40 | positive |
| `Close == Open` share (USDINR) | 40% | n/a | ≈ 0% |
| Same pair, two sources vs each other | r ≈ +0.30–0.38 | | ≈ +1.00 |

The correlation splits across two adjacent days (lag 0 → −0.34, lag +1 → −0.40) — the signature of an inconsistent intraday snapshot, not a fixed timestamp offset, so it can't be fixed by shifting. It has also gotten worse over time: EUR/USD vs DXY was −0.57 in 2005–10, ~−0.08 from 2011 on.

**The twist.** Resampled to weekly, the Yahoo series recovers completely — EUR/USD vs DXY weekly is **−0.824** on Yahoo vs **−0.814** on FRED. The defect is intraday noise that averages out over a week. This is evidence, after the fact, that the project's weekly-first framing was the right call for a reason nobody knew about yet when the call was made.

**Resolution.** All spot FX now sourced from FRED H.10 (`DEXINUS`, `DEXUSEU`, `DEXJPUS`, `DEXCHUS`) — every H.10 rate is snapped at the same instant (noon ET), so cross-FX relationships are internally consistent. The `=X` series are kept as `*_yf` context columns, retained specifically as the evidence exhibit for this finding.

**Where it lives in code.** `observatory/config/instruments.yaml` (`usdinr`, `eurusd`, `usdjpy`, `usdcny` are `source: fred`); `observatory/checks.py` asserts `eurusd`/`dxy` correlation stays in `[-0.95, -0.70]` so a regression here fails the build, not a downstream analysis. Full derivation: `research/02-observatory-scope.md` §4.5.

---

## 2026-08-12 — Pegged-currency zero-return days are real history, not a data bug

**Finding.** USD/INR and USD/CNY (FRED, full history) show 22% and 33% exact-zero-return days respectively — high enough to look like a stale-fill artifact.

**Evidence.** The zero-return share is concentrated before 2005 and falls sharply after:

| Era | USD/INR | USD/CNY |
|---|---|---|
| 1995–99 | 20.9% | 28.5% |
| 2000–04 | 17.1% | 29.8% |
| 2005–09 | 4.2% | 15.5% |
| 2010–26 | 2.4–4.1% | 5.6–7.4% |

The CNY was hard-pegged at 8.2765 until July 2005; the RBI managed the rupee far more tightly pre-2005 too. The pattern is genuine monetary-regime history, not a fetch or fill defect. Confirmed immaterial to the observatory's actual window either way — excluding zero-days moves the USDINR/Nifty correlation from −0.3929 to only −0.3967.

**Resolution.** No data change. `checks.py`'s zero-return gate is scoped to start **2008-03-03** (the observatory's real usable window, set by India VIX inception) rather than full history, so the check fires on genuine bugs rather than on genuine history.

**Where it lives in code.** `observatory/checks.py::ANALYSIS_START`. Full derivation: `research/02-observatory-scope.md` §4.6.

---

## 2026-09-28 — Snapshots were freezing in-progress bars as if they were closes

**Finding.** yfinance returns a bar for the current day while that session is still trading. The fetcher stored it as-is, so any pull made before a session settled froze a mid-session price into the permanent snapshot, labelled as that day's close.

**Evidence.** The 2026-08-12 snapshot was pulled at 23:43 IST, which is 14:13 ET, mid-session in New York. Its last bar compared with the settled value for the same day, from the 2026-09-28 pull:

| Instrument | Snapshot "close" vs settled close |
|---|---|
| VIX | **+0.89%** |
| Brent | −0.56% |
| WTI | −0.53% |
| Copper | +0.22% |
| DXY | −0.07% |
| S&P 500 | +0.02% |
| Gold | −0.00% |
| Nifty 50, India VIX | **0.000%** — pulled after the 15:30 IST close, so already final |

The split is exactly the signature expected: every instrument whose session was open at pull time is off, and every instrument whose session had closed is exact.

**Why it matters.** Raw snapshots are the reproducibility record and are never rewritten. A frozen mid-session price is a number that never existed as a close. A backtest acting on it would see a price no one could have traded at the close, and a dashboard would show a "close" that isn't one. `checks.py` could not catch it: one bar out of thousands moves no correlation.

**Resolution.** `obs/fetch.py::drop_unsettled` trims any trailing bar whose session has not settled at fetch time: 16:00 IST for Indian instruments, 17:30 ET for US and 24-hour instruments (the futures and DXY trade to the ~17:00 ET roll). FRED is untouched because it only publishes final values. Edge cases tested either side of each cutoff. **The 2026-08-12 snapshot is left as-is** — snapshots are history, not something to edit after the fact. It is superseded by 2026-09-28, which contains only settled bars.

**Operational consequence.** Any scheduled pull should run after 16:00 IST for Indian data. US data pulled then will lag one day, and that is the correct behaviour, not a bug.

---

## 2026-09-28 — NSDL flows describe the trading day *before* their date

**Finding.** NSDL's FPI flows are dated by custodial *reporting* date, and a reporting date covers trades "on and up to the previous trading day" (NSDL's own footnote). Measured, not assumed:

| Nifty return taken from… | r with `fpi_equity_exch_nsdl` (n = 3,804) |
|---|---|
| 2 days before the reporting date | +0.200 |
| **the trading day before the reporting date** | **+0.263** |
| the same date as the row — the naive join | +0.036 |
| the day after | +0.014 |

Stable in every era: 2008–13 prior-day **+0.396** vs same-row −0.017; 2014–19 **+0.224** vs +0.069; 2020–26 **+0.302** vs +0.046. The all-routes series (`fpi_equity_nsdl`) shows the same shape.

**Why it matters.** Question E1 asks whether FII flows lead or lag Nifty. A same-date join makes FII flows look nearly unrelated to the market (r ≈ 0.04), while the correct alignment shows a strong contemporaneous relationship (r ≈ 0.26). One day of date convention decides the answer before any analysis starts.

**Not interpreted here:** the +0.200 at two days back could be feedback trading (flows following returns) or occasional multi-day custodial batching. That is E1's question, not a data-quality finding.

**Resolution.** NSDL rows stay on their reporting date — never silently shifted (scope §4.8). `checks.py` fails if the prior-day correlation stops beating the same-row one by ≥ 0.10.

---

## 2026-09-28 — NSDL's archive reconciles to itself across 27 years

**Finding.** The NSDL archive holds daily FPI flows from **1999-01-01** (investments) and 2003 (derivatives), with a route split (stock exchange vs primary market) from **2009-12-01**. The layout drifted — debt categories split into General Limit / VRR / FAR, and Hybrid, Mutual Fund and AIF categories were added — but every day with a published daily Total (4,053 days) reconciles: leaf rows sum to the Total with median gap ₹0.00 cr, max **₹0.20 cr** (rounding).

**Where it lives.** `obs/flows.py`; raw month files `data/raw/nsdl_fpi_invest/`, `nsdl_fpi_deriv/` (333 months, no gaps); check in `checks.py::check_flows`.

---

## 2026-09-28 — NSE participant-OI files drift in format, and one is misaligned at source

**Finding.** NSE's daily participant-wise open-interest archive (Client / DII / FII / Pro) runs from 2012 but its format drifts: the first column is `CLIENT_TYPE` in 2012 and `Client Type` later; FII labels sometimes carry a trailing space; and at least one file (**2013-08-22**) puts the title and header on a single line **with its row labels shifted down by one** — the row labelled "Pro" holds the market totals and "TOTAL" is empty.

**How it was caught.** Every contract has exactly one long and one short side, so across participants longs must equal shorts in every column. Clean files balance exactly (occasionally to within one contract in 2026). The 2013-08-22 file was off by **461,914 contracts**.

**Resolution.** Files that fail the identity are rejected at fetch time and logged, never stored. The labels could probably be recovered from neighbouring days, but that would be inventing a correction to source data for a handful of days in a descriptive series.

---

## 2026-09-28 — MSEI's FII/DII figures are not internally consistent

**Finding.** MSEI republishes the combined FII/DII figures that NSE publishes. For 2026-09-25 both agree on buy (12,327.36) and net (−3,693.93), but MSEI's FII **sell** is 12,748.12 against NSE's 16,021.29 — and MSEI's own buy − sell (−420.76) contradicts its own net. DII agreed exactly.

**Resolution.** MSEI is used only as a fallback when NSE refuses. Every stored FII/DII row carries its `source`; `checks.py` fails on any NSE row where buy − sell ≠ net and warns on MSEI rows, whose net is the only field trusted.

---

## 2026-09-28 — NSE's main site blocks sustained automated traffic; its archive does not need to be touched through it

**Finding.** After ~15 minutes of steady requests, `www.nseindia.com` began returning **403** to new sessions from this machine. The FII/DII endpoint — the one source that cannot be backfilled — sits behind it. The archive host (`nsearchives.nseindia.com`) serves files **without** the main site's cookies.

**Resolution.** Archive fetchers never touch the main site. The nightly FII/DII capture runs first, falls back to MSEI, and is scheduled twice (21:30 and 23:30 IST) — capture is idempotent.

---

## 2026-10-01 — NSE's `PREVCLOSE` is not rebased on ex-dates (a hypothesis that failed)

**Hypothesis tested.** NSE's daily equity bhavcopy carries `CLOSE` and `PREVCLOSE`. If `PREVCLOSE` were adjusted for splits and bonuses on the ex-date, `CLOSE / PREVCLOSE − 1` would chain into clean, adjusted returns for every NSE stock since 2000 with no corporate-actions database — survivorship-free adjusted prices for free.

**Result: false.** Reliance's 1:1 bonus went ex on 2017-09-07. The bhavcopy for that day shows `CLOSE` 818.10 against `PREVCLOSE` **1,645.40** — the unadjusted prior close — so the chained return is −50.3%, a bonus booked as a crash. Across all 1,500 EQ-series stocks that day, **none** had their previous close rebased by more than 5%.

**Consequence.** Bhavcopy prices are raw. Any return series built from them needs an external split/bonus/demerger adjustment, and wrong adjustments are silent: they look like extreme returns that momentum scoring would rank first or last. Adjustment is therefore the crux of any bhavcopy-based work (`research/04` §7.1), not a detail.

**What the archive does offer** (probed 2026-10-01, `nsearchives.nseindia.com`, no cookies needed): daily equity bhavcopy back to **2000-01-03** — every security that traded that day, so delisted names are present (survivorship-free by construction); F&O bhavcopy at least to 2015; ISIN in the equity file from roughly 2010 but not 2008, so symbol changes need care before then.

---

## 2026-10-01 — A capture night was lost, permanently

**Finding.** The 2026-09-28 NSE FII/DII provisional figures are missing from the store and cannot be recovered. The endpoint serves only the latest day, and the machine was off for the whole window between that evening's publication and the next evening's (about 24 hours), so by the time capture ran the endpoint had moved on to 2026-09-29. NSDL still covers the FPI side; **DII cash flow for 2026-09-28 has no free source.**

**Resolution.** A day's figures stay available from its publication (~evening) until the next evening, so a run at any time in that window captures it — confirmed by a 13:14 run catching the previous day. The scheduled task now fires at 09:00, 13:00, 21:30 and 23:30 IST, runs missed triggers on wake, and `capture.py` writes a `capture start` line so a run killed mid-way leaves a trace. `checks.py` now reports lost Nifty trading days against the capture and fails if the newest capture is more than 7 days old. It stays a **warning** for the lost day, because a permanent loss cannot be fixed and a perpetually failing check would stop meaning anything.

**Residual risk.** All of this still depends on the machine being on at some point in each 24-hour window. A scheduler that is always on (a cloud runner) would close it; see `research/04` open items.

---

## 2026-10-01 — NSE's main site stays blocked; MSEI's FII sell figure is wrong every time

**Finding 1.** `www.nseindia.com` still returns 403 from this machine ~20 hours after the first refusal (2026-09-28), so it is not a short rate-limit. The archive host (`nsearchives.nseindia.com`) and `niftyindices.com` answer normally. FII/DII has therefore been captured from MSEI since 2026-09-29. Anything that needs the main site — including the live-quote parts of jugaad-data — is unavailable from here until that clears.

**Finding 2.** MSEI's FII row has `buy − sell ≠ net` on **every** captured day since the fallback began (2026-09-25 overlap, 09-29, 09-30), while its DII row is always consistent. On the one overlap day MSEI's FII net and buy equal NSE's exactly and only its *sell* differs (12,748.12 vs NSE's 16,021.29; MSEI's `buy − net` equals NSE's sell, so its `sell` field is just wrong). **Use MSEI's `net`, never its `sell`.** `checks.py` warns on every such row.

**Backfill behaviour.** A sustained crawl (~1,000 archive requests in 15 minutes, 2026-09-28) was followed by hours of `ConnectionError` from the archive host too, which then lifted by itself. Backfills now stop after 5 consecutive failures instead of grinding through 150 months against a refusing server, keep partial months, and run at ≥ 2 s per request.

---

## 2026-10-01 — Participant-OI files: six format quirks, one rule

**Finding.** NSE's participant-wise open-interest archive changes shape often: `CLIENT_TYPE` vs `Client Type` header; a trailing space on `FII `; title and header on one line (2013); the `TOTAL` row blank with labels shifted by one (2013-08-22); **no title line at all** (2014-07-17); and a file with no `Client` row (2014-02-24).

**Rule.** The only validator that cannot be fooled by a shifted file is the accounting identity — every contract has one long and one short side, so across participants longs must equal shorts in every column, and the four participants must sum to `TOTAL`. A file that fails is rejected for that **day only** and logged; nothing is corrected or inferred (an inferred `Client` row would be invented data in a descriptive series). An untitled file whose content passes the identities is accepted, with its date resting on the file name.

---

## 2026-10-01 — Point-in-time index membership is not freely available; the index definitions are exact set identities

**Finding 1 — no free history.** NSE publishes only each index's *current* list. The Internet Archive holds a handful of dated copies: Nifty 200 — 4 versions 2017-11 → 2023-08 on `niftyindices.com` plus 2 on NSE's archive host (2024-10, 2025-12); Nifty 100 — 9 versions 2017 → 2026; Nifty200 Momentum 30 — 2 versions, both September 2026. That is validation anchors, not a continuous history.

**Finding 2 — identities hold.** On the live lists, Nifty 100 = Nifty 50 ∪ Nifty Next 50 and Nifty 200 = Nifty 100 ∪ Nifty Midcap 100 **exactly**, and Nifty200 Momentum 30 sits inside Nifty 200. `checks.py` asserts all three on every snapshot, which both validates each captured file and means any single bad list is caught by the others.

**Policy.** Membership is captured forward from 2026-10-01 (a snapshot whenever a list changes) and anchored backward with the archive copies. A snapshot dated D says what the file held on D, and an index change takes effect on NSE's effective date, which can precede it — treat membership as good to about a week around the March and September reviews. Analysis must use `members_at(index, date)`, which returns the snapshot date with the answer, and must never apply today's list to past dates.

---

## Layers 1–4 findings

### 2026-10-01 — First descriptive pass: A1, D1, D3, E1 (data through 2026-09-28)

All computed by `obs/analysis.py` (unit-tested against planted answers) and shown in `dashboard.py`. **Nothing is fitted, but ~140 numbers were inspected** (4 questions; 11 lags × 2 frequencies for E1; 9 assets × 3 regimes for D3). A value near its noise band is not evidence.

**A1 — Nifty vs Bank Nifty does not break down in stress.** 60-day rolling daily correlation: median 0.88, range 0.61 (2021-10-26, a *calm* period) to 0.98. By prior-close India VIX regime it *rises*: calm 0.85 → elevated 0.88 → stress 0.91. Single days dominate the rolling line: 2024-06-04's election-result crash (Nifty −6.1%, Bank −8.3%) lifted it by 0.09 and its exit 60 sessions later dropped it 0.12.

**D1 — stress is variance, not mean.** India VIX regimes (in-sample cut-offs: median 17.0, top decile 30.2; each day classified by the *previous* close). Nifty annualised vol: calm 11.5%, elevated 18.2%, stress 42.6%. Mean daily return +0.028% / +0.027% / +0.015% with standard errors 0.016 / 0.028 / 0.131 — indistinguishable. Stress extremes: −13.9% / +16.3% in a day.

**D3 — correlations with Nifty rise with prior-day stress, for everything except gold.** Within India, daily: Bank 0.85→0.91, IT 0.44→0.80, Midcap 0.77→0.90. Cross-asset, weekly (484 / 388 / 97 weeks): S&P 500 0.41→0.60, USD/INR −0.38→−0.64, Dollar Index −0.05→−0.50, Brent 0.07→0.39, Copper 0.19→0.50, **Gold −0.00→0.18**. A first answer to G1: gold is the least stress-sensitive. Same-day *daily* S&P correlation was only 0.20→0.39, under half the weekly figure — a direct measurement of the §4.1 session contamination. Caveats: the stress column rests on 97 weeks; regime cut-offs use the whole history; conditioning on same-day volatility would inflate these (Forbes & Rigobon), hence the lag.

**E1 — FPI flows move with and follow Nifty; no lead found.** NSDL exchange-route net flow re-dated to the trading day it describes. Daily corr(flow(t), Nifty(t+k)): k=0 +0.279, k=−1 +0.207, −2 +0.133, −3 +0.106; **k=+1 +0.041** (band ±0.032), +2 0.000. Weekly: k=0 +0.397, −1 +0.311, −2 +0.186, **+1 +0.003**. Contemporaneous co-movement plus decay into the past is the signature of flows chasing returns; it does not prove causation. Cumulative-flow shape matches known FPI history (2022 outflow, 2023 recovery, Oct 2024 burst), which independently supports the NSDL data and its T+1 re-dating.
</content>

### 2026-10-03 — The Aug–Oct 2026 Indian equity drawdown: a slow grind, not a crash (data through 2026-10-01)

Prices re-downloaded live from Yahoo for this note (repo snapshots untouched); flows and positioning from the stored NSDL / MSEI / NSE participant-OI data. Descriptive only; nothing fitted.

**Size and shape.** Nifty 50 closed 22,421.9 on 2026-10-01, **−14.8% from its all-time high** (26,329 on 2026-01-02) and −9.5% from the 2026-08-03 high. Sensex −9.3%, Bank −7.0%, IT −11.1%, Midcap 50 −8.9% from their recent highs — broad, every index. **8 consecutive weekly losses**, the longest streak in this dataset (Nifty weekly closes, 2007 →); press reports call it the longest in ~25 years, which we cannot verify with data that starts in 2007.

**No panic days.** Worst Nifty day in the last six months is −2.12% (2026-07-08); the recent worst are −1.64% (2026-09-24) and −1.56% (2026-09-28). 20-day annualised realised vol 10.3% vs a 14.2% median since 2008. India VIX 14.5, up from 10.4 on 2026-09-23 but low. Consistent with D1 (stress is variance): this episode has had a falling mean without the variance spike.

**Flows.** FPI net equity (NSDL, all routes) **−US$28.8 bn year to date — the worst calendar year in the stored record** (2025 −18.9, 2022 −16.5); March alone −12.7. Last three sessions FII ≈ −₹10,000 cr/day with DIIs ≈ +₹10,000 cr/day (MSEI source; `sell` field not used, `net` is) — domestic buying absorbing foreign selling, which fits the lack of panic days. Consistent with E1: flows co-move with Nifty; no lead claimed.

**Positioning (caveated).** FII index-futures long share of open interest 8.0% on 2026-10-01 (11.4% a week earlier) — the lowest in the stored participant-OI history. **Stored history is 2012-01 → 2017-10 plus 2026 only** (backfill is still running), so "lowest" does not yet cover 2018–2025, including 2020. Low long share can mean bearish positioning or hedging of cash holdings; not distinguished here.

**Reported drivers (press, unverified by us):** fears of an October rate hike, tight liquidity, high crude, persistent FII selling, a long weekend.

**Open question to test later.** Does a record-low FII index-futures long share precede anything? One episode is an anecdote; test once participant OI covers 2018–2025 (new question for E3).

### 2026-10-07 — E001: a month-end trend filter on Nifty 50 buys a smoother ride, not an edge (dev sample 2008-09-30 → 2024-09-30)

Harness shakedown, pre-registered, 10 trials logged, holdout from 2024-10-01 sealed. Price index (no dividends, which flatters trend by roughly 1%/yr vs buy & hold — estimate).

| | Buy & hold | Trend SMA100 (best of 9) |
|---|---|---|
| CAGR, net | 13.0% | 9.6% |
| Volatility | 19.9% | 13.5% |
| Sharpe | 0.72 | 0.75 |
| Max drawdown | −38% | −34% |
| Cost drag | ~0 | 0.36%/yr |

**What it says.** Every SMA length from 50 to 250 lands at Sharpe 0.63–0.75, around buy & hold's 0.72: the family reliably cuts volatility and gives up return, and the *choice* of length is noise (PBO 94%). Trend sat in cash through the 2008 crash tail and lost a third as much in the COVID crash (−21% vs −52% annualised over Feb–May 2020), but lagged badly in 2009–2013 whipsaws. Turning a long-term hold into sub-year holdings also converts LTCG (12.5%) into STCG (20%): after the approximate tax model, Sharpe falls to 0.64. **Not a strategy.** A volatility-targeted buy & hold is the honest comparator if this is ever revisited.

### 2026-10-07 — Re-check of E1, D1 and D3 with honest yardsticks (data through 2026-09-28)

Two fixes to `obs/analysis.py`, then the original questions re-run. Nothing new was searched for; this only re-reads earlier answers.

**E1 — the conclusion holds, for the right reason now.** The old ±1.96/√n band assumed thin-tailed, independent data; daily FPI flow has lag-1 autocorrelation 0.43 and Nifty returns have fat tails. With a Newey-West (HAC) band: daily k=+1 corr +0.041, naive band ±0.032 (looked significant), **HAC t 1.68** (band ±0.048) — not significant, and 22 lags were inspected besides. Weekly k=+1 +0.003, t 0.08. The contemporaneous and flow-follows-returns lags stay strongly significant (daily k=0 t 12.2, k=−1 t 8.4).

**D1 — holds without look-ahead.** With expanding cut-offs (each day's median / top-decile VIX from history up to that day only): Nifty vol calm 13.9%, elevated 24.0%, stress 57.4%; means still indistinguishable. But only **45 stress days** qualify, because the 2008 VIX spike sets the top-decile bar high for years afterwards. Stress-regime numbers rest on very few days either way.

**D3 — direction holds; the gold answer to G1 does not.** Expanding cut-offs leave too few stress observations (< 60 days daily, 10 weeks weekly) to estimate stress correlations at all, so compare calm → elevated: Bank 0.87 → 0.89, IT 0.53 → 0.66, S&P 500 0.47 → 0.56, USD/INR −0.47 → −0.52, **Gold 0.08 → 0.23**. Correlations still rise with stress, but gold's rise is now the *largest* of the cross-asset set, not the smallest. "Gold is the least stress-sensitive" depended on in-sample cut-offs; treat G1 as **open**.

