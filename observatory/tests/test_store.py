import pandas as pd

from obs import store


def test_read_raw_falls_back_to_vintage_on_or_before(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "RAW", tmp_path)
    for stamp, v in [("2026-09-01", 1.0), ("2026-09-20", 2.0)]:
        store.write_raw("x", pd.DataFrame({"Close": [v]}, index=pd.to_datetime(["2026-08-31"])), stamp)
    assert store.read_raw("x", "2026-09-25")["Close"].iloc[0] == 2.0   # no exact match → latest before
    assert store.read_raw("x", "2026-09-10")["Close"].iloc[0] == 1.0
    assert store.read_raw("x")["Close"].iloc[0] == 2.0
    assert store.snapshot_on_or_before("x", "2026-08-01") is None
