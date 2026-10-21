# Market Observatory: static site (Vercel)

A static rebuild of `observatory/dashboard.py` (Streamlit) that Vercel can host.
`index.html` + `app.js` + `style.css` read only `data/*.json`; Plotly.js comes from the CDN.
There is no build step and no framework.

The JSON is written by `observatory/export_web.py`, which loads the same curated panels and
calls the same `obs.*` functions as the dashboard. The daily refresh is `observatory/refresh_web.sh`.
It fetches prices, rebuilds the panels, exports, and changes only `web/data/*.json` (text), so the
daily push is text only.

| file | what it holds | changes |
|---|---|---|
| `data/meta.json` | build time (IST), commit, "data through" per source, caveat labels, palette | daily |
| `data/overview.json` | tiles, 4 Indian indices (daily, 2007 on), Nifty drawdown, returns table | daily |
| `data/structure.json` | A1 rolling correlations (3 pairs × 4 windows), D1 regime tables, D3 heatmaps (both cut-off modes) | daily |
| `data/flows.json` | Nifty, cumulative FPI flow, E1 lead-lag (daily and weekly), participant OI, latest FII/DII | daily |
| `data/mom30.json` | Momentum 30 replication (daily returns 2005 on, by-year, eras, decomposition, anchors, picks, audit) | only when `build_momentum.py` reruns |
| `data/paper.json` | paper book NAV, holdings, fills | daily (after `paper.run_paper`) |
| `data/health.json` | last date per series, snapshot counts, `checks.py` output at build time | daily |

## One-time Vercel setup

1. Sign in at vercel.com with GitHub, then **Add New… → Project**. Import `agrawaldevansh2994-web/Market_Algo_Hark`.
2. **Root Directory**: `web` (click Edit next to it).
3. **Framework Preset**: `Other`. Leave the Build Command and Output Directory empty, because there is nothing to build.
4. **Deploy**. Every later push to `main` redeploys on its own, so the daily JSON push goes live within a minute or two.
   The site lives at `https://<project>.vercel.app`.

`vercel.json` (in this folder) only sets clean URLs and a no-cache header on `data/`, so a fresh push shows up right away.

### Optional: custom domain `markets.3dart.co.in`

1. In the project, open **Settings → Domains → Add Domain** and enter `markets.3dart.co.in`.
2. Vercel then shows the DNS record to add. For a subdomain it is a **CNAME**. Each project gets its own target
   (Vercel's docs give `d1d4fc829fe7bc7c.vercel-dns-017.com` as an example), so copy the value from that screen
   rather than a generic one.
3. At the DNS provider for `3dart.co.in`, add: Type `CNAME`, Name `markets`, Value = the target Vercel showed.
   Leave the apex and the other records alone.
4. Wait for Vercel to show "Valid Configuration". It issues HTTPS on its own.
   If Vercel asks for a `TXT` record at `_vercel.3dart.co.in` (domain used in another Vercel account), add that too.

Reference: https://vercel.com/docs/domains/working-with-domains/add-a-domain (subdomains section).

## Local preview

    cd web && python -m http.server 8000     # open http://localhost:8000

## Caveats carried from the Streamlit app

- Descriptive only: no signals, forecasts or backtests.
- Paper view: PAPER ONLY, with a ₹10L notional. Costs are a 0.1%/side estimate. The benchmark is the Nifty200 Momentum 30
  **price index (not TRI)**.
- Momentum 30 replication: gross of costs, compared with the **TRI**. Data runs through the last `build_momentum.py` run.
- Commodities and FX are context only. Cross-asset comparisons use weekly bars.
- This is a static snapshot. The Data health ages are counted in the reader's browser, so a missed refresh shows up as stale.
- The "Run checks.py" button is replaced by the `checks.py` output captured at build time.
