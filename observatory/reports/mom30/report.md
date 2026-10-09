# Step 5 — Nifty200 Momentum 30, decomposed replication (first pass, 2026-10-07)

Built by `build_momentum.py` from NSE bhavcopy (2004-01-01 → 2026-10-06, 5,624 trading days),
NSE's corporate-action feed, Yahoo split history (second source) and the published TRI
(niftyindices.com via jugaad-data). Gross of costs, like the TRI. Dashboard: **Momentum 30** view.

## TL;DR

| Claim | Number | Where |
|---|---|---|
| Selection, latest review (June 2026) vs the actual list captured 2026-10-01 | **28 of 30** | `anchors.csv` row 1 |
| Same scoring code run on the *actual* Nifty 200 | 27 of 30 | row 3 — isolates scoring from the universe proxy |
| Turnover proxy vs actual Nifty 200 (2026-10-01) | 154 of 200 | row 2 |
| Returns, whole period 2005-07 → 2026-10 | replica 13.9% vs index 18.4% CAGR; gap −4.4 pts/yr; TE 7.2% | `summary.json` |
| Returns, **2018 → 2026** | replica 15.6% vs index 14.0%; gap **+1.6 pts/yr; TE 3.7%; corr 0.985** | dashboard era table |
| Returns, 2013 → 2017 | gap −7.0 pts/yr; TE 6.0% | |
| Returns, 2005 → 2012 | gap −9.9 pts/yr; TE 10.3% | |
| Names changed per review | 15.7 of 30 on average; 19 in June 2025 (Business Standard reported ~20 for the real index) | `turnover.csv` |

**Reading:** the rule is right — on recent data the rebuild picks 28 of the real 30 and tracks the index
within ~2 pts/yr. The long-run gap is concentrated before 2018 and is not yet decomposed; the leading
causes are listed below with the evidence for each. It must not be tuned away.

## Method (official rules, methodology doc Sept 2026 pp. 187–189)

MR12 = (P(M−1)/P(M−13) − 1)/σ, MR6 likewise with M−7; σ = annualised std of 1-year daily log returns;
z-scores across the eligible set; wz = ½z12 + ½z6; score = 1+wz (wz ≥ 0) else 1/(1−wz); top 30 with the
15-in / 45-out buffer; weight ∝ ffmcap × score capped at min(5%, 5× ffmcap weight). Eligibility:
Nifty 200, ≥ 1 year listed, in F&O on the cut-off date (F&O lists read from the F&O bhavcopy of each
cut-off day). Unit tests in `tests/test_momentum.py` check each formula.

## Approximations (named sources of gap)

| | What | Proxy |
|---|---|---|
| A | Nifty 200 membership history (not free) | top 200 by 6-month average daily turnover, ETFs/fund units (ISIN INF…) removed |
| B | Free-float mcap (not free) | 6-month average turnover × score; equal weight also reported |
| C | Effective date | close of the last trading day of June/December (NSE's is often a few sessions earlier) |
| D | Adjusted prices | corporate-action audit below |
| E | Mid-period replacements/delistings | not modelled; a stock that stops trading is held flat |

## Corporate-action audit (`reports/corpactions/audit.csv`)

Scope: 1,177 stocks that ever reached the turnover top 300 at a review.

| Status | Count | Meaning |
|---|---|---|
| applied | 760 | NSE announced it and the price gapped by that factor (±35%) on the ex-date or within 5 sessions |
| applied_yf | 57 | NSE's feed is silent; Yahoo has the split and it matches the gap (e.g. JSW Steel 1:10, 2017-01-04) |
| applied_loose | 1 | factor ≥ 1:2 and the gap is within 2× (a split on a crash day) |
| scheme_market_implied | 139 | demerger/scheme: factor = ex-date gap net of the day's median move — **estimate** |
| scheme_no_gap | 17 | scheme with no visible gap; nothing applied |
| no_gap | 4 | announced, market never moved by that factor; **not** applied |
| unexplained | 115 | gap beyond −40%/+67% with nothing announced anywhere; 69 of them in 2004–2012 |

Yahoo cross-check of the NSE-announced factors we applied: **604 agree, 46 disagree, 114 no record**
(mostly delisted names). 73 single-day moves remain clipped at −60%/+150% in the return series.

Findings worth keeping: NSE's feed misses some large splits entirely (JSW Steel 2017, Vedanta/Sterlite
2008, ITC 2005); abbreviated subjects ("Bon 1:1", "Fv Spl-Rs10tors2/Bon-12:1") need care; NSE does **not** re-base `PREVCLOSE` on
demerger ex-dates either (Reliance → Jio Financial, 2023-07-20).

## Leading hypotheses for the pre-2018 gap (to test next)

1. **Remaining unexplained gaps in held stocks** (Jindal Steel's 2009 bonus is now resolved by Yahoo;
   names delisted since are absent from Yahoo and stay unexplained). Each one clipped at −60% costs the replica
   directly. Test: re-run with held-stock gaps resolved by hand.
2. **Universe proxy (A)** — turnover favours high-churn mid-caps that NSE's mcap ranking would exclude;
   no historical Nifty 200 list exists to measure this before 2026. Test: Internet Archive anchors
   2017–2023 (four Nifty 200 versions on file).
3. **Weights (B)** — equal weight beats the tilt in most years, so the turnover-for-ffmcap proxy itself
   costs ~1.3 pts/yr overall (equal weight: −3.2 vs tilt −4.4).
4. **2005–2008 data thinness** — F&O list of 122 stocks at the first review vs ~210 now.

---

# Step 5b — gap decomposition (2026-10-09)

Script: `decompose_gap.py` → `decomposition.csv`, `held_jumps.csv`, `dividends_by_year.csv`.
Each experiment changes one approximation. Gap = replica − published TRI, % points a year.

## Framing that changes the reading

The index **launched 2020-08-25** (base 2005-04-01). Every TRI value before launch is NSE's own
back-calculation, made with point-in-time Nifty 200 lists and free-float mcaps we cannot see. So the
live period is the cleanest test, and a pre-launch gap can be our proxies *or* choices in that
back-calculation. This script can only measure the first kind.

## Result: new default universe = estimated market cap

`obs/size.py`: mcap ≈ 6-month average split-adjusted price × today's share count (Yahoo, 890 of 1,168
candidates). It is exact if the share count changed only through splits/bonuses; later issuance or
buybacks make it wrong (ESTIMATE). Names that no longer trade (278) get a turnover-imputed value;
they are up to ~25% of the 2007 top 200 and ~0 after 2019.

| Check | Turnover proxy (first pass) | Estimated mcap (new) |
|---|---|---|
| Proxy vs actual Nifty 200, Oct 2026 | 154 / 200 | **176 / 200** |
| June 2026 picks vs actual Momentum 30 | 28 / 30 | 28 / 30 |
| Live since launch: gap, TE, corr | +2.8, 3.8%, 0.985 | **+0.4, 2.5%, 0.992** |
| 2018–2026 gap | +1.6 | −0.4 |
| 2013–2017 gap | −6.9 | −7.8 |
| 2005–2012 gap | −9.9 | −7.7 |

## What the experiments say about pre-2018

1. **Not the momentum rules, mostly.** A plain size-weighted top-200 of our own (no momentum logic)
   trails the Nifty 200 TRI by 3.6–4.0 pts/yr before 2018 and by 0.4 since launch. So roughly half
   of the momentum replica's pre-2018 gap is already present before any scoring: universe/size proxy
   and price data, not selection.
2. **Price jumps in held stocks are not the cause.** 55 held days moved more than ±20% before 2018;
   net contribution +1.1% of portfolio value in total. One real error: IVRCL's 1:5 split
   (2006-03-29) is unadjusted and costs about 4% once. Most others are real market-wide crash days
   (21–22 Jan 2008).
3. **Dividends are under-recorded in 2005–2008.** The replica captured 0.1–0.7% a year then vs
   1.0–2.4% from 2009. Missing NSE dividend records cost roughly 1 pt/yr in those four years.
4. **Timing is second-order.** Shifting the effective date ±5–10 sessions moves the gap by 1–2 pts.
5. **F&O filter is kept.** Switching it off narrows the pre-2018 gap by ~1 pt but triples TE since
   2018; the methodology had it at launch.
6. **The year pattern points at composition.** 2005–2012's gap is mostly 2007–2008 (Oct 2007 −10 pts,
   Sep–Dec 2008 swings); 2014 bleeds 1–4 pts every month. Steady monthly drift is what a different
   set of holdings looks like, not data glitches.

## Remaining open

- The residual momentum-specific gap before 2018 (~4 pts/yr) needs real Nifty 200 lists for
  2005–2017 to settle. The Internet Archive was offline on 2026-10-09; retry the Wayback anchors.
- Fix IVRCL 2006 manually and add a dividend second source for 2005–2008 (small, ~1 pt/yr there).
