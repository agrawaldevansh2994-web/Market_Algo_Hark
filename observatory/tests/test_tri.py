import datetime as dt

import pandas as pd
import pytest

from obs import tri as T
from paper.view import paper_frame

PAYLOAD = [{"Index Name": "Nifty200 Momentum 30", "Date": "27 Oct 2026", "TotalReturnsIndex": "35695.07"},
           {"Index Name": "Nifty200 Momentum 30", "Date": "26 Oct 2026", "TotalReturnsIndex": "35089.80"},
           {"Index Name": "Nifty200 Momentum 30", "Date": "23 Oct 2026", "TotalReturnsIndex": "-"}]


def test_parse_list_and_wrapped():
    s = T.parse(PAYLOAD)
    assert list(s.index) == [pd.Timestamp("2026-10-26"), pd.Timestamp("2026-10-27")]
    assert s.iloc[-1] == 35695.07
    import json
    assert T.parse({"d": json.dumps(PAYLOAD)}).equals(s)
    with pytest.raises(ValueError):
        T.parse("<html>")


def _ref(tmp_path, rows):
    pd.DataFrame(rows, columns=["date", "tri"]).to_csv(tmp_path / "nifty200mom30_tri.csv", index=False)


def test_update_appends_after_overlap(tmp_path):
    _ref(tmp_path, [("2026-10-23", 34383.30), ("2026-10-26", 35089.80)])
    fake = lambda name, a, b, s: pd.Series({pd.Timestamp("2026-10-26"): 35089.80, pd.Timestamp("2026-10-27"): 35695.07})
    assert T.update_ref("nifty200mom30_tri", dt.date(2026, 10, 28), tmp_path, fetcher=fake) == 1
    out = pd.read_csv(tmp_path / "nifty200mom30_tri.csv")
    assert out["date"].tolist()[-1] == "2026-10-27" and out["tri"].iloc[-1] == 35695.07
    assert T.update_ref("nifty200mom30_tri", dt.date(2026, 10, 28), tmp_path, fetcher=fake) == 0   # idempotent


def test_update_refuses_mismatched_splice(tmp_path):
    _ref(tmp_path, [("2026-10-26", 35089.80)])
    bad = lambda name, a, b, s: pd.Series({pd.Timestamp("2026-10-26"): 17000.0, pd.Timestamp("2026-10-27"): 17100.0})
    with pytest.raises(ValueError):
        T.update_ref("nifty200mom30_tri", dt.date(2026, 10, 28), tmp_path, fetcher=bad)
    gap = lambda name, a, b, s: pd.Series({pd.Timestamp("2026-10-27"): 35695.07})
    with pytest.raises(ValueError):
        T.update_ref("nifty200mom30_tri", dt.date(2026, 10, 28), tmp_path, fetcher=gap)
    assert len(pd.read_csv(tmp_path / "nifty200mom30_tri.csv")) == 1


def test_update_all_never_raises(tmp_path):
    out = T.update_all(dt.date(2026, 10, 28), tmp_path, log=lambda *_: None)   # files missing
    assert set(out) == set(T.INDICES) and all(v is None for v in out.values())


def test_paper_frame_tri_and_late_fill():
    from paper.run_paper import attach_tri
    d = pd.DataFrame({"date": ["2026-10-15", "2026-10-16", "2026-10-19"], "nav": [100.0, 99.0, 101.0],
                      "index_price": [10.0, 10.1, 10.2], "missing": [None] * 3})
    tri = pd.Series({pd.Timestamp("2026-10-15"): 200.0, pd.Timestamp("2026-10-16"): 202.0})
    d = attach_tri(d, tri)
    assert pd.isna(d["index_tri"].iloc[-1])                     # not published yet
    f = paper_frame(d)
    assert f["Index (TRI)"].iloc[1] == pytest.approx(0.01)
    assert f["Paper book"].iloc[-1] == pytest.approx(0.01)
    tri[pd.Timestamp("2026-10-19")] = 204.0                     # published on a later run
    assert attach_tri(d, tri)["index_tri"].iloc[-1] == 204.0
