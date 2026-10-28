"""Shared paper-book view helpers (Streamlit dashboard and static web export)."""
from __future__ import annotations

import pandas as pd


def paper_frame(d: pd.DataFrame) -> pd.DataFrame:
    """Cumulative returns since the first mark: book, TRI (the benchmark) and price index (context)."""
    d = d.copy()
    d["Paper book"] = d["nav"] / d["nav"].iloc[0] - 1
    d["Index (price)"] = d["index_price"] / d["index_price"].iloc[0] - 1
    tri = d["index_tri"] if "index_tri" in d else pd.Series(float("nan"), index=d.index)
    d["Index (TRI)"] = tri / tri.iloc[0] - 1 if pd.notna(tri.iloc[0]) else float("nan")
    return d
