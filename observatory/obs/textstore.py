"""Small text tables split one CSV per year.

Why: everything committed through the text-only push path must fit one shell
argument (~128 KB), and per-year files also keep git diffs small when only the
latest year changes. read_split() reassembles them.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def write_split(df: pd.DataFrame, folder: Path, date_col: str | None = None, **csv_kw) -> list[Path]:
    """Write df as folder/<YYYY>.csv by the year of date_col (or the index)."""
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("[0-9][0-9][0-9][0-9].csv"):
        old.unlink()
    years = pd.to_datetime(df[date_col]).dt.year.to_numpy() if date_col else pd.to_datetime(df.index).year.to_numpy()
    out = []
    for y in sorted(set(years)):
        p = folder / f"{y}.csv"
        df[years == y].to_csv(p, index=date_col is None, date_format="%Y-%m-%d", **csv_kw)
        out.append(p)
    return out


def read_split(folder: Path, parse_dates: list[str] | None = None, index_col=None) -> pd.DataFrame:
    files = sorted(folder.glob("[0-9][0-9][0-9][0-9].csv"))
    if not files:
        raise FileNotFoundError(folder)
    frames = [pd.read_csv(f, parse_dates=parse_dates, index_col=index_col) for f in files]
    df = pd.concat(frames)
    if index_col is not None:
        df.index = pd.to_datetime(df.index)
    return df
