"""Parquet store — snapshot-dated raw pulls, plus curated panels.

Raw pulls are written under a snapshot date rather than overwritten. That is
the fix for "notebook rot" (research/01 §4.4): every curated panel can be
traced back to the exact vintage of data it was built from.

    data/raw/<key>/<snapshot>.parquet     one pull, as received
    data/curated/<name>.parquet           aligned analysis panels
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
RAW = DATA_ROOT / "raw"
CURATED = DATA_ROOT / "curated"


def today_stamp() -> str:
    return dt.date.today().isoformat()


def raw_path(key: str, snapshot: str | None = None) -> Path:
    return RAW / key / f"{snapshot or today_stamp()}.parquet"


def write_raw(key: str, df: pd.DataFrame, snapshot: str | None = None) -> Path:
    path = raw_path(key, snapshot)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)
    return path


def latest_snapshot(key: str) -> str | None:
    """Most recent snapshot date available for an instrument, if any."""
    folder = RAW / key
    if not folder.exists():
        return None
    stamps = sorted(p.stem for p in folder.glob("*.parquet"))
    return stamps[-1] if stamps else None


def read_raw(key: str, snapshot: str | None = None) -> pd.DataFrame:
    snapshot = snapshot or latest_snapshot(key)
    if snapshot is None:
        raise FileNotFoundError(f"no raw snapshots for {key!r} — run build.py first")
    return pd.read_parquet(raw_path(key, snapshot))


def available_keys() -> list[str]:
    if not RAW.exists():
        return []
    return sorted(p.name for p in RAW.iterdir() if p.is_dir())


def write_curated(name: str, df: pd.DataFrame) -> Path:
    CURATED.mkdir(parents=True, exist_ok=True)
    path = CURATED / f"{name}.parquet"
    df.to_parquet(path)
    return path


def read_curated(name: str) -> pd.DataFrame:
    path = CURATED / f"{name}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run build.py first")
    return pd.read_parquet(path)
