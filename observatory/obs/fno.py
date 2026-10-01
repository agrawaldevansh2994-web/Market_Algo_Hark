"""Equity-derivatives positioning — NSE participant-wise open interest.

NSE archives, for each trading day since 2012, the open interest held by each
participant type — Client, DII, FII, Pro — in index/stock futures and
index/stock calls and puts, long and short, as contract counts. Unlike the
FII/DII cash endpoint this archive persists, so a night the capture misses is
refilled on the next run rather than lost.

Every contract has exactly one long and one short side, so across the four
participants longs equal shorts in every instrument column on every day —
an identity checks.py asserts.
"""

from __future__ import annotations

import re
import time as _time
from datetime import date
from io import StringIO

import pandas as pd
import requests

from .flows import MAX_STREAK, UA
from .store import read_partition, read_partitions, write_partition

POI_URL = "https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi_{:%d%m%Y}.csv"
POI_KEY = "nse_participant_oi"
POI_START = "2012-01"  # NSE's first file is 2012-01-02; 2011 returns 404 for every day
PARTICIPANTS = ["Client", "DII", "FII", "Pro"]

# (long column, short column) — each pair must balance across participants.
POI_PAIRS = [
    ("Future Index Long", "Future Index Short"),
    ("Future Stock Long", "Future Stock Short"),
    ("Option Index Call Long", "Option Index Call Short"),
    ("Option Index Put Long", "Option Index Put Short"),
    ("Option Stock Call Long", "Option Stock Call Short"),
    ("Option Stock Put Long", "Option Stock Put Short"),
]


class MalformedFile(ValueError):
    """A file that fails the source's own accounting — rejected, never stored."""


# Clean files balance to within a contract or two; a misaligned one is off by
# hundreds of thousands (e.g. 2013-08-22, whose row labels are shifted by one).
IMBALANCE_TOL = 0.001


def validate_participant_oi(df: pd.DataFrame, day: date) -> None:
    four = df[df["participant"].isin(PARTICIPANTS)]
    total = df[df["participant"] == "TOTAL"].iloc[0]
    if four.drop(columns="participant").isna().any().any():
        raise MalformedFile(f"{day}: missing or non-numeric participant values")
    for long_col, short_col in POI_PAIRS:
        size = max(four[long_col].sum(), 1)
        if abs(four[long_col].sum() - four[short_col].sum()) > IMBALANCE_TOL * size:
            raise MalformedFile(f"{day}: {long_col} does not balance {short_col}")
        for col in (long_col, short_col):
            if pd.isna(total[col]) or abs(four[col].sum() - total[col]) > IMBALANCE_TOL * size:
                raise MalformedFile(f"{day}: participants do not sum to TOTAL in {col}")


def fetch_participant_oi(day: date, session: requests.Session) -> pd.DataFrame | None:
    """One trading day's participant OI; None if NSE has no file (holiday).

    Any problem with the file's content raises MalformedFile, which rejects that
    one day. Only network and HTTP errors escape as other exception types."""
    r = session.get(POI_URL.format(day), timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    try:
        return _parse_participant_oi(r.text, day)
    except MalformedFile:
        raise
    except (ValueError, KeyError, IndexError, pd.errors.ParserError) as exc:
        raise MalformedFile(f"{day}: unparseable — {type(exc).__name__}: {str(exc)[:80]}") from exc


def _parse_participant_oi(text: str, day: date) -> pd.DataFrame:
    first = text.splitlines()[0]
    m = re.search(r"as on ([A-Za-z]+\.? \d{1,2}, \d{4})", first)
    titled = m is not None
    if titled and pd.to_datetime(m.group(1)).date() != day:
        raise MalformedFile(f"{day}: file is titled {first[:100]!r}")
    # A few files have no title line at all; the date then rests on the file name,
    # and validate_participant_oi still guards the content.
    if not titled and not re.match(r"\s*client[_ ]type", first, re.I):
        raise MalformedFile(f"{day}: unrecognised first line {first[:60]!r}")

    # Some files put the title and the column header on one line.
    header_on_first = "Future Index Long" in first
    df = pd.read_csv(StringIO(text), skiprows=1 if (titled and not header_on_first) else 0)
    # First column is 'CLIENT_TYPE' in older files, 'Client Type' later.
    df.columns = ["participant"] + [str(c).strip() for c in df.columns[1:]]
    labels = {p.upper(): p for p in PARTICIPANTS} | {"TOTAL": "TOTAL"}
    df["participant"] = df["participant"].astype(str).str.strip().str.upper().map(labels)
    df = df[df["participant"].notna()]
    if sorted(df["participant"]) != sorted(PARTICIPANTS + ["TOTAL"]):
        raise MalformedFile(f"{day}: unexpected rows {df['participant'].tolist()}")

    num = [c for c in df.columns if c != "participant"]
    df[num] = df[num].apply(lambda s: pd.to_numeric(
        s.astype(str).str.replace(",", "").str.strip(), errors="coerce"))
    validate_participant_oi(df, day)
    df.index = pd.DatetimeIndex([pd.Timestamp(day)] * len(df), name="date")
    return df


def update_participant_oi(start: str = POI_START, pause: float = 0.6, log=print) -> int:
    """Fill month files of participant OI; returns the number of failed months.

    Stored closed months are skipped. The current and previous months are
    rescanned for missing days, so a missed night heals itself from the archive.
    """
    # The archive host needs no cookies. Staying off www.nseindia.com keeps
    # archive traffic from tripping the bot protection that guards the
    # latest-day-only FII/DII endpoint (market_patterns.md, 2026-09-28).
    session = requests.Session()
    session.headers.update(UA)
    today = date.today()
    last = pd.Period(today, "M")
    failed = streak = 0

    for p in pd.period_range(pd.Period(start, "M"), last, freq="M"):
        part = str(p)
        existing = read_partition(POI_KEY, part)
        if existing is not None and p < last - 1:
            continue
        have = set(existing.index.date) if existing is not None else set()
        days = [d.date() for d in pd.bdate_range(p.start_time, min(p.end_time, pd.Timestamp(today)))
                if d.date() not in have]

        rows, absent, rejected, error = [], 0, [], None
        try:
            for d in days:
                try:
                    df = fetch_participant_oi(d, session)
                except MalformedFile as exc:
                    rejected.append(str(exc))
                    df = None
                _time.sleep(pause)
                if df is None:
                    absent += 1
                else:
                    rows.append(df)
        except Exception as exc:
            error = exc

        # Keep what was fetched even if a later day failed, so a rerun resumes.
        if rows:
            merged = pd.concat(([existing] if existing is not None else []) + rows).sort_index()
            write_partition(POI_KEY, part, merged)
        if error is not None:
            failed += 1
            streak += 1
            log(f"participant OI {part}: FAILED after +{len(rows)} days — "
                f"{type(error).__name__}: {str(error)[:120]}")
            if streak >= MAX_STREAK:
                log(f"participant OI: {streak} consecutive failures — source is refusing us, "
                    "stopping. Rerun later; stored months are kept and skipped.")
                return failed
            continue
        streak = 0
        if days:
            log(f"participant OI {part}: +{len(rows)} days, "
                f"{absent - len(rejected)} weekdays without a file, {len(rejected)} rejected")
        for msg in rejected:
            log(f"  REJECTED {msg}")
    return failed


def positioning_panel() -> pd.DataFrame:
    """Daily index-futures positioning by participant, in contracts.

    net = long − short. FII long ratio = long / (long + short), the figure
    Indian market commentary usually quotes.
    """
    raw = read_partitions(POI_KEY)
    raw = raw[raw["participant"].isin(PARTICIPANTS)]
    long_ = raw.pivot_table(index=raw.index, columns="participant", values="Future Index Long")
    short = raw.pivot_table(index=raw.index, columns="participant", values="Future Index Short")

    panel = pd.DataFrame({f"{p.lower()}_idx_fut_net": long_[p] - short[p] for p in PARTICIPANTS})
    panel["fii_idx_fut_long_ratio"] = long_["FII"] / (long_["FII"] + short["FII"])
    panel.index.name = "date"
    return panel.sort_index()
