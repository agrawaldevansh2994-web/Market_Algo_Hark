"""export_web.py: JSON encoding helpers, the dashboard import, and an end-to-end export."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import export_web as E

HERE = Path(__file__).resolve().parents[1]


def _decode_dates(obj):
    t = pd.Timestamp(obj["d0"])
    out = [t]
    for g in obj["dd"]:
        t = t + pd.Timedelta(days=g)
        out.append(t)
    return [d.strftime("%Y-%m-%d") for d in out]


def test_series_obj_roundtrips_dates_and_nulls():
    idx = pd.to_datetime(["2024-02-28", "2024-02-29", "2024-03-04", "2025-01-02"])
    df = pd.DataFrame({"a": [1.23456, np.nan, 3.0, np.inf], "b": [1, 2, 3, 4]}, index=idx)
    o = E.series_obj(df, {"a": 2, "b": 0})
    assert _decode_dates(o) == [d.strftime("%Y-%m-%d") for d in idx]
    assert o["c"]["a"] == [1.23, None, 3.0, None]
    assert o["c"]["b"] == [1, 2, 3, 4]
    json.dumps(o, allow_nan=False)          # strict JSON: no NaN/Infinity leaks


def test_table_obj_types():
    df = pd.DataFrame({"when": [pd.Timestamp("2026-10-19"), pd.NaT], "n": np.array([5, 7], dtype="int64"),
                       "x": [0.123456, np.nan], "s": ["msei", None], "f": [True, False]})
    t = E.table_obj(df, 3)
    assert t["cols"] == ["when", "n", "x", "s", "f"]
    assert t["rows"] == [["2026-10-19", 5, 0.123, "msei", True], [None, 7, None, None, False]]
    json.dumps(t, allow_nan=False)


def test_dashboard_import_does_not_render_and_exposes_helpers():
    D = E.load_dashboard()
    for name in ("load", "raw_tables", "load_mom", "ensure_curated", "NAMES", "SER_MOM", "WINDOWS", "PAPER", "MOM"):
        assert hasattr(D, name), name
    assert list(D.WINDOWS) == ["1Y", "3Y", "5Y", "10Y", "Max"]


@pytest.mark.skipif(not any((HERE / "data" / "curated").glob("*.parquet")),
                    reason="curated panels not built (run build.py); end-to-end export skipped")
def test_export_end_to_end(tmp_path):
    sizes = E.run(tmp_path, run_checks=False)
    assert set(sizes) == {"overview", "structure", "flows", "mom30", "paper", "health", "meta"}
    assert all(v < 1_000_000 for v in sizes.values()), sizes
    meta = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    ov = json.loads((tmp_path / "overview.json").read_text(encoding="utf-8"))
    close = pd.read_parquet(HERE / "data" / "curated" / "close_daily.parquet")
    nifty = close["nifty50"].dropna()
    assert meta["data_through"] == nifty.index[-1].strftime("%Y-%m-%d")
    assert next(t for t in ov["tiles"] if t["key"] == "nifty50")["last"] == pytest.approx(float(nifty.iloc[-1]), abs=1e-3)
    assert "TRI" in meta["caveats"]["benchmark_label"] and "not TRI" not in meta["caveats"]["benchmark_label"]
    paper = json.loads((tmp_path / "paper.json").read_text(encoding="utf-8"))
    if not paper.get("missing"):
        daily = pd.read_csv(HERE / "paper" / "state" / "daily.csv")
        assert paper["nav"] == pytest.approx(float(daily["nav"].iloc[-1]), abs=0.01)
