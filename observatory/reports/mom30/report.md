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
