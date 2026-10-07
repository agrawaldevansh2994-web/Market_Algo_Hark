"""Corporate actions → adjusted prices, with an audit trail.

Bhavcopy prices are unadjusted (research/04 §7.1), and adjustment errors are
silent and land in the tails momentum ranks by. So adjustment here is two
independent sources that must agree before a factor is applied:

  announced  NSE's corporate-action feed (api/corporates-corporateActions),
             one call per year, parsed from free-text subjects into
             (kind, factor): bonus a:b → b/(a+b); split FV X→Y → Y/X;
             consolidation X→Y → Y/X.
  observed   the price gap in the bhavcopy itself on the ex-date:
             close(ex) / close(previous trading day).

audit() pairs them. An announced split/bonus is APPLIED only when the observed
gap is within a factor of 1.35 of the announced one (a day's ordinary move
rarely exceeds ±25%; NSE stock circuits are mostly 20%). If the gap appears on
another day within ±5 sessions (the feed's ex-date is occasionally off), the
factor is applied on the day the market actually moved. A gap within a factor
of 2 (a split landing on a crash day) is still applied, as `applied_loose`, for
factors of 1:2 or larger. If no gap is found the
action is NOT applied and is listed as `no_gap` — applying it would invent a
crash. Demergers and schemes of arrangement use NSE's own adjusted base price
when bhavcopy PREVCLOSE shows a re-base; it usually does not (Reliance →
Jio Financial, 2023), so otherwise the factor is market-implied: the ex-date
gap net of the day's median move, applied only beyond 2% (an estimate — the
spun-off value is not observed directly). Large gaps with
no announced action are listed as `unexplained` for manual review.

Symbol renames (ZOMATO → ETERNAL) are joined through NSE's symbolchange.csv
so a renamed stock keeps its price history.

Dividends are parsed too (amount per share), for total-return work only;
momentum ranks on price return, as the index methodology specifies.

Stored as text so they can be committed:
  data/corpactions/nse_actions/YYYY.csv  every split / bonus / consolidation /
                                     scheme / rights / dividend row
  data/corpactions/symbolchange.csv  NSE's rename file, as downloaded
  reports/corpactions/audit.csv      the audit (written by build_momentum.py)
"""

from __future__ import annotations

import re
import time as _time
from io import StringIO

import numpy as np
import pandas as pd
import requests

from .flows import UA
from .store import DATA_ROOT
from .textstore import read_split, write_split

CA_DIR = DATA_ROOT / "corpactions"
CA_API = "https://www.nseindia.com/api/corporates-corporateActions?index=equities&from_date=01-01-{y}&to_date=31-12-{y}"
SYMCHG_URL = "https://nsearchives.nseindia.com/content/equities/symbolchange.csv"

MATCH_TOL = np.log(1.35)
LOOSE_TOL = np.log(2.0)      # announced factor kept when the gap is this close (crash-day splits)
SEARCH_WINDOW = 5
UNEXPLAINED_GAP = np.log(1 / 0.6)   # a close-to-close move beyond −40% / +67%

_NUM = r"(\d+(?:\.\d+)?)"
BONUS = re.compile(r"\bbon(?:us)?\s*[-:]?\s*" + _NUM + r"\s*:\s*" + _NUM, re.I)
SPLIT = re.compile(r"(?:split|sub-?division|spl\b)[^0-9]*?" + _NUM + r"[^0-9]*?to[^0-9]*?" + _NUM, re.I)
CONSOL = re.compile(r"consolidat[^0-9]*?" + _NUM + r"[^0-9]+?to[^0-9]*?" + _NUM, re.I)
SCHEME = re.compile(r"demerg|scheme\s+of\s+arr|sch\.?\s*of\s*arr|arngment|arrangement|spin", re.I)
RIGHTS = re.compile(r"\brights?\b", re.I)
DIVIDEND = re.compile(r"\b(?:div|dividend)\b[^/]*?(?:rs\.?|re\.?|inr)\s*" + _NUM, re.I)
NOT_EQUITY_BONUS = re.compile(r"bonus[^/]*?(deb|dvr|pref|ncd|warrant)", re.I)


def parse_subject(subject: str) -> list[tuple[str, float]]:
    """Free-text subject → [(kind, value)]. value is the price factor for
    bonus/split/consolidation (multiply pre-ex prices by it), the per-share
    amount for dividends, NaN for scheme/rights. One subject can carry several
    (\"Bonus 1:1/Dividend- Rs 7 Per Share\")."""
    s = " ".join(str(subject).split())
    out: list[tuple[str, float]] = []
    m = BONUS.search(s)
    if m and not NOT_EQUITY_BONUS.search(s):
        a, b = float(m.group(1)), float(m.group(2))
        if a > 0 and b > 0:
            out.append(("bonus", b / (a + b)))
    m = CONSOL.search(s)
    if m:
        x, y = float(m.group(1)), float(m.group(2))
        if x > 0 and y > x:
            out.append(("consolidation", y / x))
    else:
        m = SPLIT.search(s)
        if m:
            x, y = float(m.group(1)), float(m.group(2))
            if x > 0 and 0 < y < x:
                out.append(("split", y / x))
    if SCHEME.search(s):
        out.append(("scheme", np.nan))
    if RIGHTS.search(s) and not re.search(r"right\s*to", s, re.I):
        out.append(("rights", np.nan))
    for m in DIVIDEND.finditer(s):
        out.append(("dividend", float(m.group(1))))
    return out


# ------------------------------------------------------------------ fetch

def fetch_year(year: int, session: requests.Session) -> list[dict]:
    for attempt in range(3):
        r = session.get(CA_API.format(y=year), timeout=60)
        if r.ok:
            return r.json()
        _time.sleep(5 * (attempt + 1))
    r.raise_for_status()
    return []


def update_actions(start: int = 2004, end: int | None = None, log=print) -> pd.DataFrame:
    """Re-pull the feed for every year and rewrite nse_actions.csv (small: ~25k rows)."""
    end = end or pd.Timestamp.today().year
    s = requests.Session()
    s.headers.update({**UA, "Accept": "application/json"})
    rows = []
    for y in range(start, end + 1):
        for x in fetch_year(y, s):
            for kind, val in parse_subject(x.get("subject", "")):
                rows.append({"symbol": str(x.get("symbol", "")).strip(), "series": x.get("series"),
                             "isin": x.get("isin"), "ex_date": pd.to_datetime(x.get("exDate"), format="%d-%b-%Y",
                                                                             errors="coerce"),
                             "kind": kind, "value": val, "subject": " ".join(str(x.get("subject")).split())})
        log(f"corporate actions {y}: fetched")
        _time.sleep(1)
    df = pd.DataFrame(rows).dropna(subset=["ex_date"])
    df = df.drop_duplicates(["symbol", "ex_date", "kind", "value"]).sort_values(["ex_date", "symbol"])
    df.loc[df["kind"] == "dividend", "subject"] = ""          # amount is in `value`; keeps files small
    write_split(df, CA_DIR / "nse_actions", "ex_date")
    r = s.get(SYMCHG_URL, timeout=60)
    if r.ok:
        (CA_DIR / "symbolchange.csv").write_bytes(r.content)
    elif not (CA_DIR / "symbolchange.csv").exists():
        r.raise_for_status()
    else:
        log(f"symbolchange.csv: HTTP {r.status_code}, keeping the stored copy")
    return df


def load_actions() -> pd.DataFrame:
    return read_split(CA_DIR / "nse_actions", parse_dates=["ex_date"]).fillna({"subject": ""})


def load_symbol_changes() -> pd.DataFrame:
    """old, new, date — oldest first."""
    raw = (CA_DIR / "symbolchange.csv").read_text(encoding="latin-1")
    rows = []
    for line in raw.splitlines():
        parts = [p.strip() for p in line.rsplit(",", 3)]
        if len(parts) != 4:
            continue
        d = pd.to_datetime(parts[3], format="%d-%b-%Y", errors="coerce")
        if pd.notna(d) and parts[1] and parts[2]:
            rows.append({"old": parts[1], "new": parts[2], "date": d})
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


# ------------------------------------------------------------- canonical ids

def canonical_symbols(bhav: pd.DataFrame, changes: pd.DataFrame) -> pd.Series:
    """For each bhav row, the symbol the company trades under today.

    A rename old→new on date D maps old-symbol rows dated before D to new
    (then follows any later rename of new). Rows of a symbol that is *reused*
    after it was renamed away keep their own symbol."""
    sym = bhav["symbol"].to_numpy(object).copy()
    dates = bhav["date"].to_numpy()
    for old, new, d in changes[["old", "new", "date"]].itertuples(index=False):
        hit = (sym == old) & (dates < np.datetime64(d))
        sym[hit] = new
    return pd.Series(sym, index=bhav.index, name="cid")


# ------------------------------------------------------------------ audit

def audit(close: pd.DataFrame, prevclose: pd.DataFrame, actions: pd.DataFrame) -> pd.DataFrame:
    """Pair announced actions with observed gaps.

    close, prevclose: date × cid wide frames (unadjusted, NaN when not traded).
    actions: load_actions() with an added `cid` column.
    Returns one row per announced price action (bonus/split/consolidation/
    scheme) for cids present in `close`, plus one row per unexplained gap, with
    status in {applied, applied_shifted, applied_loose, no_gap, scheme_rebased,
    scheme_market_implied, scheme_no_gap, unexplained} and the factor actually applied."""
    gap = np.log(close / close.ffill().shift(1))
    rebase = prevclose / close.ffill().shift(1)            # NSE's own re-basing, when it does it
    mkt = gap.median(axis=1).fillna(0.0)                   # the day's typical move
    idx = close.index
    rows = []
    explained: set[tuple] = set()
    acts = actions[actions["kind"].isin(["bonus", "split", "consolidation", "scheme"]) &
                   actions["cid"].isin(close.columns)]
    # combine several actions on the same day (bonus + split together)
    for (cid, ex), grp in acts.groupby(["cid", "ex_date"]):
        kinds = "+".join(sorted(set(grp["kind"])))
        factor = float(np.prod(grp["value"].dropna())) if grp["value"].notna().any() else np.nan
        pos = idx.searchsorted(ex)
        if pos >= len(idx):
            continue
        g = gap[cid]
        base = {"cid": cid, "ex_date": ex, "kind": kinds, "announced": factor,
                "subject": " | ".join(grp["subject"].astype(str).unique())[:160]}
        if np.isnan(factor):                                # scheme only
            # NSE does NOT re-base PREVCLOSE for demergers (Reliance → Jio Financial,
            # 2023-07-20: PREVCLOSE = prior close). Use NSE's re-basing when present,
            # else the market-implied factor: the ex-date gap net of that day's median
            # move across the panel, applied only when it exceeds 2%.
            rb = rebase[cid].iloc[pos]
            gx = g.iloc[pos]
            if pd.notna(rb) and abs(np.log(rb)) > 0.02:
                status, fac = "scheme_rebased", float(rb)
            elif pd.notna(gx) and abs(gx - mkt.iloc[pos]) > 0.02:
                status, fac = "scheme_market_implied", float(np.exp(gx - mkt.iloc[pos]))
            else:
                status, fac = "scheme_no_gap", np.nan
            rows.append({**base, "status": status, "applied_date": idx[pos] if pd.notna(fac) else pd.NaT,
                         "observed": float(np.exp(gx)) if pd.notna(gx) else np.nan, "factor": fac})
            explained.add((cid, idx[pos]))
            continue
        lf = np.log(factor)
        lo, hi = max(0, pos - SEARCH_WINDOW), min(len(idx), pos + SEARCH_WINDOW + 1)
        window = g.iloc[lo:hi].dropna()
        if pos < len(g) and pd.notna(g.iloc[pos]) and abs(g.iloc[pos] - lf) < MATCH_TOL:
            day, status = idx[pos], "applied"
        else:
            cand = window[(window - lf).abs() < MATCH_TOL]
            loose = window[(window - lf).abs() < LOOSE_TOL]
            loose = loose[(np.sign(loose) == np.sign(lf)) & (loose.abs() > abs(lf) / 2)]
            if len(cand):
                day = (cand - lf).abs().idxmin()
                status = "applied_shifted"
            elif len(loose) and abs(lf) > LOOSE_TOL / 2:
                # e.g. Jindal Steel 1:5 split on 2008-01-21, a −27% market day: gap 0.15 vs 0.20
                day = (loose - lf).abs().idxmin()
                status = "applied_loose"
            else:
                day, status = pd.NaT, "no_gap"
        obs = float(np.exp(g.loc[day])) if pd.notna(day) else (float(np.exp(g.iloc[pos])) if pd.notna(g.iloc[pos]) else np.nan)
        rows.append({**base, "status": status, "applied_date": day, "observed": obs,
                     "factor": factor if status != "no_gap" else np.nan})
        if pd.notna(day):
            explained.add((cid, day))
    # big gaps nobody announced
    big = gap.where(gap.abs() > UNEXPLAINED_GAP).stack().dropna()
    for (day, cid), v in big.items():
        if (cid, day) in explained:
            continue
        rows.append({"cid": cid, "ex_date": day, "kind": "none", "announced": np.nan, "subject": "",
                     "status": "unexplained", "applied_date": pd.NaT, "observed": float(np.exp(v)),
                     "factor": np.nan})
    out = pd.DataFrame(rows)
    return out.sort_values(["ex_date", "cid"]).reset_index(drop=True) if len(out) else out


def adjustment_factors(close: pd.DataFrame, audit_df: pd.DataFrame) -> pd.DataFrame:
    """date × cid multiplier for unadjusted prices: product of every applied
    factor whose applied_date is AFTER the row's date (backward adjustment —
    today's prices are left as they are)."""
    f = pd.DataFrame(1.0, index=close.index, columns=close.columns)
    ok = audit_df.dropna(subset=["applied_date", "factor"])
    for cid, day, fac in ok[["cid", "applied_date", "factor"]].itertuples(index=False):
        if cid in f.columns:
            f.loc[f.index < day, cid] *= fac
    return f


# ------------------------------------------------- second source: Yahoo splits

YF_CACHE = CA_DIR / "yf_splits.csv"


def fetch_yf_splits(cids: list[str], workers: int = 8, log=print) -> pd.DataFrame:
    """Yahoo's split/bonus history for <cid>.NS (bonuses appear as splits:
    1:1 bonus = 2.0). Cached in yf_splits.csv; a cid with no history is
    recorded with an empty date so it is not re-asked. Delisted names are
    unknown to Yahoo — those gaps stay unexplained."""
    from concurrent.futures import ThreadPoolExecutor
    import yfinance as yf
    have = pd.read_csv(YF_CACHE, parse_dates=["date"]) if YF_CACHE.exists() else \
        pd.DataFrame(columns=["cid", "date", "ratio"])
    todo = sorted(set(cids) - set(have["cid"]))

    def one(c):
        try:
            sp = yf.Ticker(f"{c}.NS").splits
        except Exception:
            return [{"cid": c, "date": pd.NaT, "ratio": np.nan}]
        if sp is None or len(sp) == 0:
            return [{"cid": c, "date": pd.NaT, "ratio": np.nan}]
        return [{"cid": c, "date": pd.Timestamp(d).tz_localize(None).normalize(), "ratio": float(r)}
                for d, r in sp.items()]

    if todo:
        with ThreadPoolExecutor(workers) as ex:
            rows = [r for rs in ex.map(one, todo) for r in rs]
        have = pd.concat([have, pd.DataFrame(rows)], ignore_index=True)
        CA_DIR.mkdir(parents=True, exist_ok=True)
        have.to_csv(YF_CACHE, index=False, date_format="%Y-%m-%d")
        log(f"yahoo splits: asked {len(todo)} symbols")
    return have


def second_source(aud: pd.DataFrame, close: pd.DataFrame, yf_splits: pd.DataFrame) -> pd.DataFrame:
    """Use Yahoo's split history (a) to verify every NSE-announced factor we
    applied (`yf_check`: agree / disagree / no_record) and (b) to resolve
    unexplained gaps: a Yahoo split within ±5 sessions whose factor 1/ratio
    matches the observed gap is applied as `applied_yf`."""
    aud = aud.copy()
    sp = yf_splits.assign(date=pd.to_datetime(yf_splits["date"], errors="coerce")).dropna(subset=["date"])
    by = {c: g for c, g in sp.groupby("cid")}
    idx = close.index
    known = set(yf_splits["cid"])
    checks = []
    for i, r in aud.iterrows():
        g = by.get(r["cid"])
        near = None
        if g is not None:
            ref = r["applied_date"] if pd.notna(r["applied_date"]) else r["ex_date"]
            d = (g["date"] - ref).abs()
            if len(d) and d.min() <= pd.Timedelta(days=8):
                near = g.loc[d.idxmin()]
        if r["status"] in ("applied", "applied_shifted", "applied_loose"):
            if near is None:
                checks.append("no_record" if r["cid"] in known else "not_asked")
            else:
                ok = abs(np.log(1 / near["ratio"]) - np.log(r["factor"])) < np.log(1.05)
                checks.append("agree" if ok else "disagree")
        elif r["status"] == "unexplained" and near is not None:
            f = 1 / near["ratio"]
            obs = r["observed"]
            if abs(np.log(obs) - np.log(f)) < LOOSE_TOL and np.sign(np.log(obs)) == np.sign(np.log(f)):
                aud.loc[i, ["status", "factor", "applied_date", "announced", "kind"]] = \
                    ["applied_yf", f, r["ex_date"], f, "yahoo_split"]
                checks.append("yahoo_only")
            else:
                checks.append("disagree")
        else:
            checks.append("")
    aud["yf_check"] = checks
    return aud
