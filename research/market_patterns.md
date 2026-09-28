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

## Layers 1–4 findings

Not yet — no correlation, lead-lag or regime analysis has been run. This section will hold the answers to the scope §3 question bank (A1–G1) as they're produced.
</content>
