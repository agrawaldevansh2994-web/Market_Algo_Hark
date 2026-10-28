/* Market Observatory — static rebuild of observatory/dashboard.py.
   Reads only data/*.json (written by observatory/export_web.py). No build step.
   Window clipping, rebasing and cumulative products are done here exactly as
   dashboard.py does them (clip(), A.rebase, cum - cum.iloc[0], (1+r).cumprod()). */
"use strict";

const VIEWS = [
  ["overview", "Overview"], ["structure", "Equity structure"], ["flows", "Flows & positioning"],
  ["mom30", "Momentum 30"], ["paper", "Paper"], ["health", "Data health"],
];
const WINDOWS = { "1Y": 1, "3Y": 3, "5Y": 5, "10Y": 10, "Max": null };
const FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif";
const state = { view: "overview", window: "5Y", a1other: "niftybank", a1win: 60, expanding: false,
                e1freq: "Weekly", review: null, auditPick: null };
const cache = {};
let META = null, P = null, SLOT = null;

// ------------------------------------------------------------------ utils
const $ = (s, el = document) => el.querySelector(s);
function h(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") e.className = v; else if (k === "html") e.innerHTML = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else if (v !== undefined && v !== null) e.setAttribute(k, v);
  }
  for (const k of kids.flat()) if (k !== null && k !== undefined) e.append(k.nodeType ? k : document.createTextNode(String(k)));
  return e;
}
async function load(name) {
  if (!cache[name]) cache[name] = fetch(`data/${name}.json`, { cache: "no-cache" }).then(r => {
    if (!r.ok) throw new Error(`data/${name}.json: HTTP ${r.status}`); return r.json(); });
  return cache[name];
}
function dates(obj) {           // rebuild the delta-encoded date list
  if (obj._dates) return obj._dates;
  const out = []; if (!obj.d0) return (obj._dates = out);
  let t = Date.parse(obj.d0 + "T00:00:00Z"); out.push(obj.d0);
  for (const g of obj.dd) { t += g * 86400000; out.push(new Date(t).toISOString().slice(0, 10)); }
  return (obj._dates = out);
}
function minusYears(iso, n) {   // pandas: Timestamp - DateOffset(years=n) (Feb 29 -> Feb 28)
  let [y, m, d] = iso.split("-").map(Number); y -= n;
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate(); if (d > last) d = last;
  return `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}
/* dashboard.clip(): df.loc[df.index[-1] - DateOffset(years):] ; anchor defaults to the frame's own last date */
function clipIdx(ds, anchor) {
  const yrs = WINDOWS[state.window];
  if (yrs === null || !ds.length) return 0;
  const start = minusYears(anchor || ds[ds.length - 1], yrs);
  let lo = 0, hi = ds.length;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (ds[mid] < start) lo = mid + 1; else hi = mid; }
  return lo;
}
function clipObj(obj, anchor) {
  const ds = dates(obj), i0 = clipIdx(ds, anchor);
  const c = {}; for (const [k, v] of Object.entries(obj.c)) c[k] = v.slice(i0);
  return { d: ds.slice(i0), c };
}
const isNum = v => typeof v === "number" && isFinite(v);
const fmt = (v, dp = 2, sign = false) => !isNum(v) ? "" :
  (sign && v >= 0 ? "+" : "") + v.toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });
const pct = (v, dp = 1, sign = false) => !isNum(v) ? "" : fmt(v * 100, dp, sign) + "%";
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const dmy = iso => { if (!iso) return ""; const [y, m, d] = iso.split("-"); return `${d} ${MON[+m - 1]} ${y}`; };
const minOf = a => a.reduce((m, v) => isNum(v) && v < m ? v : m, Infinity);
const maxOf = a => a.reduce((m, v) => isNum(v) && v > m ? v : m, -Infinity);
function lastNum(a) { for (let i = a.length - 1; i >= 0; i--) if (isNum(a[i])) return a[i]; return null; }
function md(s) {                // tiny markdown: **bold**, *italic*, `code`
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>").replace(/`(.+?)`/g, "<code>$1</code>");
}
const cap = s => h("div", { class: "caption", html: md(s) });
const sub = s => h("h2", {}, s);

// ------------------------------------------------------------------ tables
/* t = {cols, rows}; opt.fmt[col] = fn(v) ; opt.left = cols aligned left ; opt.wrap = long-text cols */
function table(t, opt = {}) {
  const f = opt.fmt || {}, left = new Set([...(opt.left || [t.cols[0]]), ...(opt.wrap || [])]), wrapc = new Set(opt.wrap || []);
  const thead = h("tr", {}, t.cols.map(c => h("th", { class: left.has(c) ? "l" : "" }, opt.rename?.[c] ?? c)));
  const tb = h("tbody");
  const rows = opt.rows || t.rows;
  const frag = document.createDocumentFragment();
  for (const r of rows) {
    const tr = document.createElement("tr");
    r.forEach((v, j) => {
      const c = t.cols[j]; const td = document.createElement("td");
      if (wrapc.has(c)) td.className = "wr"; else if (left.has(c) || (typeof v === "string" && !opt.numStr)) td.className = "l";
      td.textContent = v === null || v === undefined ? "" : f[c] ? f[c](v) : typeof v === "number" ? (PLAIN.has(c) ? String(v) : defNum(v)) : String(v);
      tr.append(td);
    });
    frag.append(tr);
  }
  tb.append(frag);
  return h("div", { class: "tbl", style: opt.maxh ? `max-height:${opt.maxh}px` : null }, h("table", {}, h("thead", {}, thead), tb));
}
const PLAIN = new Set(["year", "rank", "lag", "review", "n"]);   // id-like numbers: no thousands separator
function defNum(v) {            // Streamlit-like default: integers plain, floats up to 4 dp
  if (Number.isInteger(v)) return v.toLocaleString("en-US");
  return v.toLocaleString("en-US", { maximumFractionDigits: 4 });
}
/* table twin: rendered only when opened (some are thousands of rows) */
function twin(label, build) {
  const d = h("details", { class: "twin" }, h("summary", {}, label));
  const inner = h("div", { class: "inner" }); d.append(inner);
  d.addEventListener("toggle", () => { if (d.open && !inner.firstChild) inner.append(build()); });
  return d;
}
function seriesTable(ds, cols, names, dp = 2, idxName = "date") {
  return table({ cols: [idxName, ...names], rows: ds.map((d, i) => [d, ...cols.map(c => c[i])]) },
               { fmt: Object.fromEntries(names.map(n => [n, v => fmt(v, dp)])) });
}

// ------------------------------------------------------------------ charts
function mix(a, b, t) {
  const ca = [1, 3, 5].map(i => parseInt(a.slice(i, i + 2), 16)), cb = [1, 3, 5].map(i => parseInt(b.slice(i, i + 2), 16));
  return "#" + ca.map((x, i) => Math.round(x + (cb[i] - x) * t).toString(16).padStart(2, "0")).join("");
}
const divScale = () => [[0, P.neg], [0.25, mix(P.mid, P.neg, 0.5)], [0.5, P.mid], [0.75, P.pos[0]], [1, P.pos[1]]];
const color = k => P.series[SLOT[k]];
function baseLayout(height = 360, extra = {}) {
  const axisX = { showgrid: false, showline: true, linecolor: P.axis, ticks: "outside", tickcolor: P.axis,
    showspikes: true, spikemode: "across", spikethickness: 1, spikecolor: P.muted, spikedash: "solid", spikesnap: "cursor" };
  return Object.assign({
    height, margin: { l: 56, r: 16, t: 30, b: 40 }, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: FONT, size: 12, color: P.ink2 }, hovermode: "x unified",
    legend: { orientation: "h", yanchor: "bottom", y: 1.02, x: 0, font: { color: P.ink2 } },
    hoverlabel: { font: { family: FONT } }, xaxis: axisX,
    yaxis: { gridcolor: P.grid, gridwidth: 1, zeroline: false, showline: false },
  }, extra);
}
const lineTrace = (x, y, name, c, fmtH = "%{y:,.2f}", extra = {}) => Object.assign({ x, y, type: "scatter", mode: "lines", name,
  line: { color: c, width: 2 }, hovertemplate: `${name}: ${fmtH}<extra></extra>`, connectgaps: false }, extra);
function plot(el, traces, layout, cfg = {}) {
  Plotly.newPlot(el, traces, layout, Object.assign({ displaylogo: false, responsive: true,
    modeBarButtonsToRemove: ["lasso2d", "select2d"] }, cfg));
}
function chartDiv(h0) { return h("div", { class: "chart", style: `height:${h0}px` }); }
function heat(t, height) {      // dashboard.heat()
  const rows = t.rows.map(r => r[0]), cols = t.cols.slice(1), z = t.rows.map(r => r.slice(1));
  const ann = [];
  z.forEach((r, i) => r.forEach((v, j) => { if (isNum(v)) ann.push({ x: cols[j], y: rows[i], text: v.toFixed(2), showarrow: false,
    font: { size: 12, color: Math.abs(v) > 0.6 ? P.on_strong : P.ink } }); }));
  const el = chartDiv(height);
  return { el, draw: () => plot(el, [{ type: "heatmap", z, x: cols, y: rows, zmin: -1, zmax: 1, colorscale: divScale(), showscale: true,
    xgap: 2, ygap: 2, hovertemplate: "%{y} · %{x}: %{z:.2f}<extra></extra>",
    colorbar: { thickness: 10, len: 0.9, outlinewidth: 0, tickfont: { color: P.ink2 } } }],
    { height, margin: { l: 110, r: 16, t: 40, b: 20 }, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      font: { family: FONT, size: 12, color: P.ink2 }, annotations: ann,
      yaxis: { autorange: "reversed", showgrid: false, automargin: true }, xaxis: { showgrid: false, side: "top" } },
    { displayModeBar: false }) };
}
function seg(options, value, onChange, labels) {
  const box = h("div", { class: "seg" });
  for (const o of options) box.append(h("button", { class: String(o) === String(value) ? "on" : "",
    onclick: () => onChange(o) }, labels ? labels(o) : String(o)));
  return box;
}
const ctl = (label, el) => h("div", {}, h("div", { class: "ctl-label" }, label), el);
function tiles(items) {
  return h("div", { class: "tiles" }, items.map(t => h("div", { class: "tile", title: t.help || "" },
    h("div", { class: "lab" }, t.label), h("div", { class: "val" }, t.value),
    t.delta ? h("div", { class: "delta" }, t.delta) : null, t.asof ? h("div", { class: "asof" }, t.asof) : null)));
}

// ================================================================== views
async function viewOverview(root) {
  const o = await load("overview");
  root.append(cap("Where things stand. Each series is measured to its own last observation — FRED publishes " +
    "with a lag, so as-of dates differ and are shown."));
  root.append(tiles(o.tiles.map(t => ({ label: t.name, value: t.value, delta: pct(t.d1, 2, true),
    asof: `as of ${t.as_of}`, help: `as of ${t.as_of}` }))));

  const four = ["nifty50", "niftybank", "niftyit", "niftymidcap"];
  root.append(sub("Indian equity indices, rebased to 100"));
  root.append(cap("One axis; all four start at 100 on the first day all have data in the window."));
  const cl = clipObj(o.close4, o.panel_last);        // clip by the whole panel's last date, as dashboard does
  const keep = cl.d.map((_, i) => four.every(k => isNum(cl.c[k][i])));   // A.rebase: dropna(how="any")
  const ds = cl.d.filter((_, i) => keep[i]);
  const reb = {}; for (const k of four) { const v = cl.c[k].filter((_, i) => keep[i]); reb[k] = v.map(x => x / v[0] * 100); }
  const el1 = chartDiv(360); root.append(el1);
  plot(el1, four.map(k => lineTrace(ds, reb[k], o.names[k], color(k), "%{y:,.1f}")), baseLayout(360));
  root.append(twin("Table view", () => seriesTable(ds, four.map(k => reb[k]), four, 2)));

  root.append(sub("Nifty 50 drawdown"));
  root.append(cap("Distance below the running peak, measured from the start of the series (2007) — " +
    "so the window changes what you see, not the numbers."));
  const dd = clipObj(o.drawdown); const ddp = dd.c.nifty50.map(v => v * 100);
  const el2 = chartDiv(260); root.append(el2);
  plot(el2, [lineTrace(dd.d, ddp, "Nifty 50 drawdown", color("nifty50"), "%{y:.1f}%")],
    baseLayout(260, { showlegend: false, yaxis: { ...baseLayout().yaxis, ticksuffix: "%" } }));
  root.append(twin("Table view", () => seriesTable(dd.d, [ddp], ["drawdown_%"], 2)));

  root.append(sub("Returns"));
  const rc = ["1D", "1W", "1M", "3M", "YTD", "1Y"];
  root.append(table(o.returns, { maxh: 1200, rename: { last: "Last", series: "" },
    fmt: { last: v => fmt(v, 2), ...Object.fromEntries(rc.map(c => [c, v => fmt(v, 1, true) + "%"])) } }));
}

async function viewStructure(root) {
  const s = await load("structure");
  root.append(cap("How the Indian market is internally connected, and how that changes with volatility. Questions A1, D1, D3."));

  root.append(sub("A1 · Does Nifty vs Bank Nifty break down in stress?"));
  const row = h("div", { class: "row" });
  const selEl = h("select", { onchange: e => { state.a1other = e.target.value; render(); } },
    Object.entries(s.names).map(([k, n]) => h("option", { value: k, ...(k === state.a1other ? { selected: "" } : {}) }, n)));
  row.append(ctl("Compare Nifty 50 with", selEl),
             ctl("Rolling window (trading days)", seg(s.wins, state.a1win, w => { state.a1win = w; render(); })));
  root.append(row);
  const o = state.a1other, w = state.a1win;
  const cl = clipObj({ ...s.rc[o], c: { v: s.rc[o].c[`${o}_${w}`] } });
  const v = cl.c.v, lo = minOf(v), hi = maxOf(v), last = v[v.length - 1];
  const el = chartDiv(300); root.append(el);
  plot(el, [lineTrace(cl.d, v, `Nifty 50 vs ${s.names[o]}`, color(o), "%{y:.2f}")],
    baseLayout(300, { showlegend: false, yaxis: { ...baseLayout().yaxis, range: [Math.max(-1, Math.floor((lo - 0.03) * 10) / 10), 1] } }));
  root.append(cap(`${w}-day rolling correlation of daily log returns, same exchange session so no timezone ` +
    `contamination. Latest ${fmt(last, 2)}; window min ${fmt(lo, 2)}, max ${fmt(hi, 2)}. ` +
    "The vertical axis does not start at zero. Sharp steps are single extreme days entering or " +
    "leaving the window — e.g. 4 Jun 2024 (Nifty −6.1%, Bank Nifty −8.3%) lifts the 60-day line by " +
    "0.09 on the day and drops it 0.12 when it leaves 60 sessions later."));
  root.append(twin("Table view", () => seriesTable(cl.d, [v], ["corr"], 3)));

  root.append(sub("D1 · What does Nifty do by India VIX regime?"));
  const tg = h("input", { type: "checkbox", onchange: e => { state.expanding = e.target.checked; render(); } });
  tg.checked = state.expanding;
  root.append(h("label", { class: "toggle" }, tg, "No look-ahead: expanding cut-offs (each day uses only VIX history up to that day)"));
  const key = state.expanding ? "expanding" : "full";
  root.append(table(s.d1[key], { fmt: { days: v => fmt(v, 0) }, rename: {} }));
  const cutText = state.expanding
    ? "Cut-offs are the median and top decile of VIX history *up to each day* (first year unlabelled), so nothing looks ahead. Each day"
    : `Calm: India VIX ≤ ${fmt(s.cutoffs.median, 1)} (median). Stress: ≥ ${fmt(s.cutoffs.top_decile, 1)} (top decile). Cut-offs use the whole ` +
      "history, so this describes the past; it is not a live signal. Toggle above for the no-look-ahead version. Each day";
  root.append(cap(cutText + " is classified by the *previous* close. Note the mean-return column: its standard error is larger " +
    "than the gaps between regimes — stress differs in variance, not demonstrably in average return."));

  root.append(sub("D3 · Do correlations with Nifty converge in stress?"));
  root.append(cap("Correlation with Nifty 50, split by India VIX regime at the previous close. Conditioning on same-day " +
    "volatility would inflate correlations mechanically (Forbes & Rigobon 2002), which is why the lagged classification is used."));
  const d3 = s.d3[key];
  const hd = heat(d3.daily, 200), hw = heat(d3.weekly, 330);
  root.append(h("div", { class: "cols2" },
    h("div", {}, h("div", { html: "<strong>Within India — daily</strong><br><span class='caption'>Same trading session, so daily bars are clean.</span>" }), hd.el),
    h("div", {}, h("div", { html: "<strong>Cross-asset — weekly</strong><br><span class='caption'>These trade outside Indian hours; weekly bars shrink the session mismatch (scope §4.1).</span>" }), hw.el)));
  hd.draw(); hw.draw();
  root.append(cap("Weeks per regime — " + ["calm", "elevated", "stress"].map(k => `${k} ${d3.weeks[k]}`).join(", ") +
    ". Stress cells rest on far fewer observations than calm ones; read small differences as noise."));
  root.append(twin("Table view — D3", () => {
    const rows = [...d3.daily.rows.map(r => ["within India (daily)", ...r]), ...d3.weekly.rows.map(r => ["cross-asset (weekly)", ...r])];
    return table({ cols: ["", "series", ...d3.daily.cols.slice(1)], rows }, { left: ["", "series"] });
  }));
}

async function viewFlows(root) {
  const f = await load("flows");
  root.append(cap("Institutional flows. Questions E1 (do FPI flows lead Nifty?) and E3 (derivatives positioning)."));

  root.append(sub("FPI equity flow vs Nifty 50"));
  root.append(cap("Cumulative net FPI investment through the stock exchange (₹ crore, NSDL, custodian-confirmed), " +
    "re-dated to the trading day it describes: NSDL's reporting date covers the previous trading day " +
    "(scope §4.8). Two panels sharing a time axis — not a dual axis."));
  const nif = clipObj(f.nifty), cum = clipObj(f.fpi_cum);
  const c0 = cum.c.fpi_cum[0], cumv = cum.c.fpi_cum.map(x => x - c0);
  const el = chartDiv(440); root.append(el);
  // make_subplots(rows=2, shared_xaxes, vertical_spacing=0.08, row_heights=[0.55, 0.45])
  const L = baseLayout(440, { showlegend: true });
  L.yaxis = { ...L.yaxis, domain: [0.494, 1] }; L.yaxis2 = { ...L.yaxis, domain: [0, 0.414] };
  L.xaxis = { ...L.xaxis, anchor: "y2" };
  plot(el, [lineTrace(nif.d, nif.c.nifty50, "Nifty 50", color("nifty50"), "%{y:,.0f}", { yaxis: "y" }),
            lineTrace(cum.d, cumv, "Cumulative FPI flow (₹ cr)", color("niftybank"), "%{y:,.0f}", { yaxis: "y2" })], L);
  root.append(twin("Table view", () => {
    const m = new Map(); nif.d.forEach((d, i) => m.set(d, [nif.c.nifty50[i], null]));
    cum.d.forEach((d, i) => { const r = m.get(d) || [null, null]; r[1] = cumv[i]; m.set(d, r); });
    const ks = [...m.keys()].sort();
    return table({ cols: ["date", "nifty50", "fpi_cum_flow_cr"], rows: ks.map(k => [k, ...m.get(k)]) },
                 { fmt: { nifty50: v => fmt(v, 1), fpi_cum_flow_cr: v => fmt(v, 1) } });
  }));

  root.append(sub("E1 · Do FPI flows lead Nifty, or follow it?"));
  root.append(ctl("Frequency", seg(["Daily", "Weekly"], state.e1freq, v => { state.e1freq = v; render(); })));
  const ll = f.lead_lag[state.e1freq], ci = n => ll.cols.indexOf(n);
  const lag = ll.rows.map(r => r[0]), corr = ll.rows.map(r => r[ci("corr")]), band = ll.rows.map(r => r[ci("band_hac")]);
  const el2 = chartDiv(320); root.append(el2);
  const L2 = baseLayout(320, { margin: { l: 56, r: 16, t: 30, b: 70 } });
  L2.xaxis = { ...L2.xaxis, dtick: 1, title: { text: "lag k  ·  k > 0: flow leads Nifty  |  k < 0: flow follows Nifty", standoff: 12 } };
  L2.yaxis = { ...L2.yaxis, zeroline: true, zerolinecolor: P.axis, title: { text: "correlation" } };
  plot(el2, [{ type: "bar", x: lag, y: corr, name: "correlation", marker: { color: color("nifty50") }, width: 0.45,
               hovertemplate: "lag %{x}: %{y:.3f}<extra></extra>" },
             { type: "scatter", mode: "lines", x: lag, y: band, name: "±1.96 HAC noise band", line: { color: P.muted, width: 1 },
               hovertemplate: "band: %{y:.3f}<extra></extra>" },
             { type: "scatter", mode: "lines", x: lag, y: band.map(b => -b), name: "±1.96 HAC noise band", showlegend: false,
               line: { color: P.muted, width: 1 }, hovertemplate: "band: %{y:.3f}<extra></extra>" }], L2);
  root.append(cap(`${state.e1freq} bars, ${fmt(ll.rows[0][ci("n")], 0)} observations. The peak at k = 0 and the decay toward k < 0 ` +
    "mean flows move with the market and follow its recent direction. Bars at k > 0 would indicate flows *leading* — they stay " +
    "inside the noise band. The band is Newey-West (HAC): robust to fat-tailed returns and persistent flows; the naive " +
    "±1.96/√n band is too narrow here (it is in the table as `band`). NSDL data, Dec 2009 onward. Several lags are inspected, " +
    "so a bar only just outside the band is still not evidence."));
  root.append(twin("Table view", () => table(ll)));

  root.append(sub("E3 · Who holds index futures? Participant net positions"));
  if (!f.poi) { root.append(h("div", { class: "info" }, "No participant open-interest data stored yet.")); }
  else {
    const poi = clipObj(f.poi);
    const parts = [["fii", "FII"], ["dii", "DII"], ["pro", "Proprietary"], ["client", "Retail clients"]];
    // break_gaps(): a NaN row one day before every gap longer than 10 days
    const bx = [], by = Object.fromEntries(parts.map(([k]) => [k, []]));
    poi.d.forEach((d, i) => {
      if (i > 0 && (Date.parse(d) - Date.parse(poi.d[i - 1])) / 86400000 > 10) {
        bx.push(new Date(Date.parse(d) - 86400000).toISOString().slice(0, 10)); parts.forEach(([k]) => by[k].push(null));
      }
      bx.push(d); parts.forEach(([k]) => by[k].push(poi.c[`${k}_idx_fut_net`][i]));
    });
    const el3 = chartDiv(330); root.append(el3);
    const L3 = baseLayout(330); L3.yaxis = { ...L3.yaxis, title: { text: "net contracts" } };
    plot(el3, parts.map(([k, lab]) => lineTrace(bx, by[k], lab, color(k), "%{y:,.0f}")), L3);
    const weekdays = bdays(poi.d[0], poi.d[poi.d.length - 1]);
    root.append(cap(`Net position (long − short) in index futures by participant type, from NSE's daily participant-wise ` +
      `open interest. Coverage in this window: ${poi.d.length.toLocaleString("en-US")} of about ${weekdays.toLocaleString("en-US")} ` +
      `weekdays (${Math.round(poi.d.length / weekdays * 100)}%); lines break where data is missing. Stored history ` +
      `${f.poi_full.min} to ${f.poi_full.max} (${f.poi_full.n.toLocaleString("en-US")} days) — the backfill of earlier years ` +
      "is still running. Every contract has a long and a short side, so the four lines sum to zero each day."));
    const pc = Object.keys(poi.c);
    root.append(twin("Table view", () => table({ cols: ["date", ...pc], rows: poi.d.map((d, i) => [d, ...pc.map(c => poi.c[c][i])]) },
      { fmt: Object.fromEntries(pc.map(c => [c, v => fmt(v, 0)])) })));
  }

  root.append(sub("Latest FII / DII (NSE provisional)"));
  if (f.cash) {
    if (f.lost.length) root.append(h("div", { class: "warn" }, "⚠ No capture for trading day(s) " + f.lost.join(", ") +
      " — permanent: the source serves only the latest day."));
    root.append(table(f.cash, { fmt: { "FII net (₹ cr)": v => fmt(v, 2), "DII net (₹ cr)": v => fmt(v, 2) } }));
    root.append(cap("Only the net columns are trusted: MSEI's FII sell value is inconsistent (market_patterns.md)."));
  }
}
function bdays(a, b) {          // len(pd.bdate_range(a, b))
  let n = 0; for (let t = Date.parse(a); t <= Date.parse(b); t += 86400000) { const w = new Date(t).getUTCDay(); if (w && w < 6) n++; }
  return n;
}

async function viewMom30(root) {
  const m = await load("mom30");
  if (m.missing) { root.append(h("div", { class: "info" }, "No replication results yet. Run `python build_bhav.py` then `python build_momentum.py`.")); return; }
  const s = m.summary, tt = s.tracking.replica_tilt, te = s.tracking.replica_ew;
  root.append(sub("⑤ Nifty200 Momentum 30 — how close does a free-data rebuild get?"));
  root.append(cap("A measured replication of a published index (roadmap step 5), not a strategy signal. The methodology is " +
    "NSE's (Sept 2026 document, pp. 187–189); what free data forces us to approximate is listed at the bottom. Success means " +
    "an explained gap, not a zero one."));
  root.append(tiles([
    { label: "Replica CAGR", value: pct(tt.cagr_rep, 1), help: "Estimated market cap × score weights, total return, gross of costs" },
    { label: "Index TRI CAGR", value: pct(tt.cagr_bench, 1) },
    { label: "Gap per year", value: pct(tt.gap_pa, 1, true), help: "Replica minus index, annualised" },
    { label: "Tracking error", value: pct(tt.tracking_error, 1), help: "Annualised std. dev. of daily return differences" },
    { label: "Daily correlation", value: tt.corr.toFixed(3) }]));
  root.append(cap(`${tt.start} → ${tt.end}, ${s.reviews} semi-annual reviews. Equal-weight replica: CAGR ${pct(te.cagr_rep, 1)}, ` +
    `tracking error ${pct(te.tracking_error, 1)}.`));
  const lv = s.tracking.live_replica_tilt;
  if (lv) root.append(h("div", { class: "info", html: md(`**Since the index went live (${s.live_from})** the replica returned ` +
    `${pct(lv.cagr_rep, 1)} a year against ${pct(lv.cagr_bench, 1)} — a gap of ${pct(lv.gap_pa, 1, true)}, tracking error ` +
    `${pct(lv.tracking_error, 1)}, correlation ${lv.corr.toFixed(3)}. Everything before that date is NSE's own back-calculation, ` +
    "built with membership and free-float data we cannot see.") }));

  const dd = clipObj(m.daily), keys = Object.keys(m.series);
  const growth = {}; for (const k of keys) { let g = 1; growth[k] = dd.c[k].map(r => (g *= 1 + (isNum(r) ? r : NaN))); }
  const el = chartDiv(380); root.append(el);
  const L = baseLayout(380); L.yaxis = { ...L.yaxis, type: "log", title: { text: "growth of ₹1 (log)" } };
  plot(el, keys.map(k => lineTrace(dd.d, growth[k], m.series[k].name, P.series[m.series[k].slot], "%{y:,.2f}×")), L);
  root.append(twin("Monthly values", () => {      // growth.resample("ME").last()
    const rows = []; let cur = null;
    dd.d.forEach((d, i) => { const ym = d.slice(0, 7); const row = [monthEnd(ym), ...keys.map(k => growth[k][i])];
      if (ym === cur) rows[rows.length - 1] = row; else { rows.push(row); cur = ym; } });
    return table({ cols: ["date", ...keys], rows }, { fmt: Object.fromEntries(keys.map(k => [k, v => fmt(v, 3)])) });
  }));

  root.append(sub("Where the gap comes from, year by year"));
  const el2 = chartDiv(300); root.append(el2);
  const L2 = baseLayout(300); L2.yaxis = { ...L2.yaxis, zeroline: true, zerolinecolor: P.axis, title: { text: "% points" } };
  plot(el2, [{ type: "bar", x: m.gap_bars.year, y: m.gap_bars.gap, name: "replica − index, % pts",
    marker: { color: m.gap_bars.gap.map(v => v >= 0 ? P.pos[1] : P.neg) }, hovertemplate: "%{x}: %{y:+.1f} pts<extra></extra>" }], L2);
  root.append(table(m.by_year, { fmt: Object.fromEntries(m.by_year.cols.slice(1).map(c => [c, v => fmt(v, 1)])), rename: {} }));
  root.append(table(m.eras, { fmt: { correlation: v => fmt(v, 3), ...Object.fromEntries(m.eras.cols.slice(1, 5).map(c => [c, v => fmt(v, 1)])) } }));
  root.append(cap("The gap sits before 2018, and most of 2005–2012's comes from 2007–2008. The decomposition below tests each suspect on its own."));

  if (m.decomp) {
    root.append(sub("Decomposing the gap — one approximation changed at a time"));
    const f1 = Object.fromEntries(m.decomp.gap.cols.slice(1).map(c => [c, v => fmt(v, 1)]));
    root.append(table(m.decomp.gap, { fmt: f1, wrap: ["experiment"] }));
    root.append(twin("Tracking error by era, %", () => table(m.decomp.te, { fmt: f1, wrap: ["experiment"] })));
    root.append(cap("Gap = replica minus index, % points a year. **Universe only** rows compare a size-weighted proxy-200 with " +
      "the Nifty 200 TRI, so they test the universe and the price data without any momentum logic."));
    if (m.jumps) {
      root.append(cap(`Held stocks' single-day moves beyond ±20% before 2018: ${m.jumps.n} days, net contribution ` +
        `${pct(m.jumps.net, 1, true)} of portfolio value; ${m.jumps.unexplained} are unexplained price gaps. Most fall on ` +
        "market-wide crash days (Jan 2008)."));
      root.append(twin("Largest held-stock jumps before 2018", () => table(m.jumps.top)));
    }
  }

  root.append(sub("Validation anchors — the real lists on file"));
  if (m.anchors) {
    root.append(table(m.anchors, { wrap: ["check", "ours_only", "actual_only"], maxh: 1400 }));
    root.append(cap("The first row tests the whole pipeline; the next two test only the universe proxy (new, then first pass); " +
      "the last scores the *real* Nifty 200 with our code, so its overlap isolates the scoring from the universe approximation. " +
      "More anchors arrive as the forward capture records each review."));
  }

  root.append(sub("Picks at each review"));
  if (!state.review || !m.picks[state.review]) state.review = m.reviews[m.reviews.length - 1];
  const holder = h("div");
  const lab = h("span", { class: "val" }, state.review);
  const rng = h("input", { type: "range", min: 0, max: m.reviews.length - 1, step: 1, value: m.reviews.indexOf(state.review) });
  const drawPicks = () => {
    const pk = m.picks[state.review]; holder.innerHTML = "";
    holder.append(table(pk.table, { left: ["symbol"], maxh: 1150 }));
    holder.append(cap(`Cut-off ${dmy(pk.cutoff)}, effective ${dmy(pk.effective)}; ${pk.n_eligible} stocks eligible after the ` +
      "F&O and one-year-listing filters."));
  };
  rng.addEventListener("input", () => { state.review = m.reviews[+rng.value]; lab.textContent = state.review; drawPicks(); });
  root.append(h("div", { class: "slider" }, h("div", { class: "ctl-label" }, "Review: ", lab), rng,
    h("div", { class: "caption" }, `${m.reviews[0]} … ${m.reviews[m.reviews.length - 1]}`)));
  root.append(holder); drawPicks();
  if (m.turnover) root.append(cap(`Average names changed per review: ${fmt(m.turnover.names_changed, 1)} of 30; average one-way ` +
    `turnover ${pct(m.turnover.one_way, 0)}.`));

  root.append(sub("Corporate-action audit"));
  if (m.audit) {
    const statuses = m.audit.counts.rows.map(r => r[0]);
    if (!state.auditPick) state.auditPick = new Set(["no_gap", "unexplained"].filter(x => statuses.includes(x)));
    root.append(h("div", { class: "cols12" }, table(m.audit.counts, { rename: { status: "status" } }),
      h("div", { class: "caption", html: md("**applied** — NSE announced it and the price gapped by that factor on the ex-date. " +
        "**applied_shifted** — the gap came within 5 sessions of the announced date. **no_gap** — announced, but the market never " +
        "moved by that factor; *not* applied. **scheme_market_implied** — demerger or scheme; factor = ex-date gap net of the day's " +
        "median move (an estimate). **unexplained** — a gap beyond −40% / +67% with nothing announced. Scope: the stocks that " +
        "ever reached the liquidity top 300 at a review.") })));
    const chips = h("div", { class: "chips" }), tb = h("div");
    const si = m.audit.rows.cols.indexOf("status");
    const drawAudit = () => { tb.innerHTML = ""; tb.append(table(m.audit.rows, { rows: m.audit.rows.rows.filter(r => state.auditPick.has(r[si])),
      left: ["cid", "ex_date", "kind", "announced", "subject", "status", "applied_date", "yf_check"] })); };
    for (const st of statuses) {
      const lb = h("label", { class: state.auditPick.has(st) ? "on" : "" }, st);
      lb.addEventListener("click", () => { state.auditPick.has(st) ? state.auditPick.delete(st) : state.auditPick.add(st);
        lb.classList.toggle("on"); drawAudit(); });
      chips.append(lb);
    }
    root.append(h("div", { class: "ctl-label" }, "Show status"), chips, tb); drawAudit();
  }

  const ap = h("details", { class: "twin" }, h("summary", {}, "What free data forces us to approximate"));
  ap.append(h("div", { class: "inner" }, h("ul", { class: "approx", html: [
    "**A. Universe** — Nifty 200 membership history is not free. Proxy: top 200 by *estimated* market cap = 6-month average " +
    "split-adjusted price × today's share count (Yahoo). Later share issuance or buybacks make it wrong; stocks that no longer " +
    "trade get a turnover-imputed value. The first pass used 6-month turnover instead.",
    "**B. Weights** — free-float market cap history is not free. Proxy: estimated full market cap × score, capped at min(5%, 5× " +
    "base weight). Equal weight shown alongside.",
    "**C. Timing** — portfolio changes at the close of the last trading day of June/December; NSE's effective date is usually a few sessions earlier.",
    "**D. Prices** — adjusted only where NSE's announcement and the market's own gap agree (audit above).",
    "**E. Mid-period events** — delistings and ad-hoc replacements are not modelled.",
    `Results are **gross of costs**, like the TRI. Single-day moves are clipped at −60% / +150% (${s.clipped_daily_moves} clipped).`,
  ].map(x => `<li>${md(x)}</li>`).join("") })));
  root.append(ap);
  root.append(cap(`Replication data through ${m.data_end} (committed reports/mom30, rebuilt only when build_momentum.py runs).`));
}
function monthEnd(ym) { const [y, mo] = ym.split("-").map(Number); return `${ym}-${String(new Date(Date.UTC(y, mo, 0)).getUTCDate()).padStart(2, "0")}`; }

async function viewPaper(root) {
  const p = await load("paper");
  root.append(sub("Paper book: Momentum 30 replica, traded on paper"));
  root.append(cap(META.caveats.paper));
  if (p.missing) { root.append(h("div", { class: "info" }, "No paper book yet.")); return; }
  const hasTri = p.tri_ret !== null && p.tri_ret !== undefined;
  root.append(tiles(hasTri
    ? [{ label: "NAV", value: "₹" + fmt(p.nav, 0) }, { label: "Paper return", value: pct(p.ret, 2, true) },
       { label: "Index TRI return", value: pct(p.tri_ret, 2, true) }, { label: "vs TRI", value: pct(p.tri_diff, 2, true) }]
    : [{ label: "NAV", value: "₹" + fmt(p.nav, 0) }, { label: "Paper return", value: pct(p.ret, 2, true) },
       { label: "Index (price) return", value: pct(p.idx_ret, 2, true) }, { label: "Difference", value: pct(p.diff, 2, true) }]));
  const d = p.daily, ci = n => d.cols.indexOf(n), x = d.rows.map(r => r[ci("date")]);
  const el = chartDiv(320); root.append(el);
  const lines = ["Paper book", "Index (TRI)", "Index (price)"].filter(c => ci(c) >= 0);
  plot(el, lines.map((c, i) => ({ type: "scatter", mode: "lines+markers", name: c, x, y: d.rows.map(r => r[ci(c)]),
    line: { color: P.series[i], width: 2, dash: c === "Index (price)" ? "dot" : "solid" } })),
    { height: 320, margin: { l: 56, r: 16, t: 10, b: 40 }, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      font: { family: FONT, color: P.ink2 }, legend: { orientation: "h", y: -0.18 },
      yaxis: { tickformat: ".1%", gridcolor: P.grid, zeroline: false }, xaxis: { showgrid: false, linecolor: P.axis, type: "date", tickformat: "%d %b", dtick: 86400000 } });
  root.append(cap(`Since ${dmy(p.first)} close; last mark ${dmy(p.last)}.` +
    (hasTri && p.tri_last !== p.last ? ` TRI published through ${dmy(p.tri_last)}; "vs TRI" is measured to that day.` : "") +
    (p.dividends ? ` Dividends credited: ₹${fmt(p.dividends, 0)} (gross).` : "")));
  if (p.membership) {
    const m = p.membership;
    root.append(h("div", { class: m.overlap === m.of ? "ok" : "info" },
      `Official index list (${dmy(m.as_of)}): ${m.overlap} of ${m.of} names held.` +
      (m.held_not_in_index.length ? ` Held, not in index: ${m.held_not_in_index.join(", ")}.` : "") +
      (m.in_index_not_held.length ? ` In index, not held: ${m.in_index_not_held.join(", ")}.` : "") +
      " The book only trades at the semi-annual review, so drift between reviews is expected."));
  }
  root.append(h("div", { class: "cols2" },
    h("div", {}, h("h3", {}, "Holdings"), table(p.positions, { fmt: { shares: v => defNum(v) }, maxh: 1150 })),
    h("div", {}, h("h3", {}, "Fills"), table(p.ledger, { left: ["date", "symbol", "side"], maxh: 1150 }))));
  root.append(cap(`Costs paid so far: ₹${fmt(p.cost, 0)} (estimate).`));
}

async function viewHealth(root) {
  const hh = await load("health");
  root.append(cap("Is the data current, and do the integrity checks pass?"));
  const today = new Date(Date.now() + 5.5 * 3600000).toISOString().slice(0, 10);   // IST calendar day
  const rows = hh.rows.map(r => { const age = Math.round((Date.parse(today) - Date.parse(r.last)) / 86400000);
    return [r.series, r.source, r.last, age, age <= r.limit ? "✓ fresh" : `! stale (>${r.limit}d)`]; });
  root.append(table({ cols: ["series", "source", "last date", "age (days)", "status"], rows }, { left: ["series", "source", "last date", "status"], maxh: 1200 }));
  root.append(cap(`Ages are counted to today (${today}, IST) in your browser; this page is a static build from ${META.built_ist}. ` +
    "A stale row here usually means the daily refresh has not run."));
  root.append(h("div", { html: "<strong>Index membership snapshots</strong> (point-in-time history, scope §4.9): " +
    Object.entries(hh.snapshots).map(([k, n]) => `${k} ${n}`).join(" · ") }));
  root.append(sub("Integrity checks"));
  if (hh.checks) {
    root.append(h("div", { class: hh.checks.ok ? "ok" : "err" }, (hh.checks.ok ? "✓ All checks passed" : "✗ One or more checks FAILED") +
      ` — checks.py ran at build time (${hh.checks.ran_at}).`));
    root.append(twin("checks.py output", () => h("pre", {}, hh.checks.output)));
  } else root.append(h("div", { class: "info" }, "checks.py was not run for this build."));
  root.append(sub("Capture log (latest)"));
  if (hh.capture_log) root.append(h("pre", {}, hh.capture_log));
  else root.append(h("div", { class: "info" }, "capture.log not found — it lives on the capture PC and is not committed to the repo."));
}

// ================================================================== shell
const RENDER = { overview: viewOverview, structure: viewStructure, flows: viewFlows, mom30: viewMom30, paper: viewPaper, health: viewHealth };
const USES_WINDOW = new Set(["overview", "structure", "flows", "mom30"]);
let renderSeq = 0;
async function render() {
  const seq = ++renderSeq, y = window.scrollY;
  $("#nav").replaceWith(Object.assign(seg(VIEWS.map(v => v[0]), state.view, v => { location.hash = v; },
    v => VIEWS.find(x => x[0] === v)[1]), { id: "nav" }));
  $("#win").replaceWith(Object.assign(seg(Object.keys(WINDOWS), state.window, w => { state.window = w; render(); }), { id: "win" }));
  $("#winbox").style.display = USES_WINDOW.has(state.view) ? "" : "none";
  const root = h("div"), view = $("#view");
  view.style.minHeight = view.offsetHeight + "px";      // keep scroll position while re-rendering
  view.innerHTML = ""; view.append(root);               // charts draw into nodes already in the DOM
  try { await RENDER[state.view](root); }
  catch (e) { root.append(h("div", { class: "err" }, `Could not render this view: ${e.message}`)); console.error(e); }
  view.style.minHeight = "";
  if (seq !== renderSeq) return;
  window.scrollTo(0, y);
}
function route() {
  const v = location.hash.replace("#", "");
  state.view = RENDER[v] ? v : "overview";
  window.scrollTo(0, 0); render();
}
(async function init() {
  try { META = await load("meta"); }
  catch (e) { $("#view").innerHTML = `<div class="err">Could not load data/meta.json: ${e.message}</div>`; return; }
  P = META.palette; SLOT = META.slot;
  $("#subtitle").innerHTML = md(`${META.subtitle} Data through ${dmy(META.data_through)}.`) +
    `<br>Built ${META.built_ist}${META.commit ? ` from commit ${META.commit}` : ""}. ${META.caveats.static}`;
  $("#foot").innerHTML = md([META.caveats.descriptive, META.caveats.commodities, META.caveats.costs, META.caveats.fred_lag].join(" ")) +
    "<br>Data through, per source: " + Object.entries(META.through).map(([k, v]) => `${k} ${v}`).join(" · ");
  window.addEventListener("hashchange", route);
  route();
})();
