"""Fetchers — pull raw history from live sources into the snapshot store.

Two sources are wired up:

  yfinance  indices, futures and the ICE dollar index. research/01 §4.2 flags
            it as degraded, and scope §4.5 records the specific defect we
            measured: the `=X` spot FX quotes are unusable at daily frequency.
  fred      Federal Reserve H.10. Authoritative, free, and every rate is
            snapped at the same instant (noon ET), which is exactly the
            property the `=X` quotes lack. Publishes with a few days' lag.

Sources for the India 10Y, FII/DII flows and real MCX prices are unresolved —
see scope §6.
"""

from __future__ import annotations

import io
import warnings

import pandas as pd
import requests

from .registry import Instrument, Registry, load_registry
from .store import write_raw

OHLCV = ["Open", "High", "Low", "Close", "Volume"]


def fetch_yfinance(inst: Instrument, period: str = "max") -> pd.DataFrame:
    """Daily OHLCV for one instrument, indexed by naive local trading date.

    The index is deliberately left in each instrument's *own* local trading
    date. Forcing everything onto one timezone would silently paper over the
    session mismatch that scope §4.1 exists to keep visible.
    """
    import yfinance as yf

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = yf.Ticker(inst.ticker).history(
            period=period, interval="1d", auto_adjust=False
        )

    if df.empty:
        raise ValueError(f"{inst.key} ({inst.ticker}): source returned no rows")

    idx = pd.to_datetime(df.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    df.index = idx.normalize()
    df.index.name = "date"

    df = df[[c for c in OHLCV if c in df.columns]]
    # Indices carry no meaningful volume; drop the column rather than store zeros.
    if "Volume" in df and (df["Volume"].fillna(0) == 0).all():
        df = df.drop(columns="Volume")

    return df[~df.index.duplicated(keep="last")].sort_index()


FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"


def fetch_fred(inst: Instrument, timeout: int = 60) -> pd.DataFrame:
    """Daily series from FRED, shaped like the OHLCV frames for a uniform store.

    FRED publishes a single observation per day, so Close is the only real
    field. It is stored under 'Close' so downstream code needs no special case.
    """
    resp = requests.get(FRED_CSV.format(inst.ticker), timeout=timeout)
    resp.raise_for_status()

    df = pd.read_csv(io.StringIO(resp.text))
    if df.shape[1] != 2:
        raise ValueError(f"{inst.key} ({inst.ticker}): unexpected FRED columns {list(df.columns)}")
    df.columns = ["date", "Close"]

    df["date"] = pd.to_datetime(df["date"])
    # FRED marks holidays with '.', which read_csv leaves as a string.
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna().set_index("date").sort_index()
    df.index.name = "date"

    if df.empty:
        raise ValueError(f"{inst.key} ({inst.ticker}): FRED returned no usable rows")

    return df[~df.index.duplicated(keep="last")]


FETCHERS = {"yfinance": fetch_yfinance, "fred": fetch_fred}


def fetch_all(
    registry: Registry | None = None,
    snapshot: str | None = None,
    period: str = "max",
) -> tuple[dict[str, int], dict[str, str]]:
    """Pull every fetchable instrument. Returns (rows_written, failures)."""
    reg = registry or load_registry()
    written: dict[str, int] = {}
    failed: dict[str, str] = {}

    for inst in reg.fetchable():
        try:
            fetcher = FETCHERS[inst.source]
            df = fetcher(inst, period=period) if inst.source == "yfinance" else fetcher(inst)
            write_raw(inst.key, df, snapshot)
            written[inst.key] = len(df)
        except Exception as exc:  # network, symbol change, upstream break
            failed[inst.key] = f"{type(exc).__name__}: {exc}"

    return written, failed
