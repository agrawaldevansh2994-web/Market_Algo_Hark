import pandas as pd

from obs.flows import lost_capture_days


def test_lost_capture_days_reports_only_interior_gaps():
    trading = pd.to_datetime(["2026-09-24", "2026-09-25", "2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01"])
    captured = pd.to_datetime(["2026-09-25", "2026-09-29", "2026-09-30"])
    lost = lost_capture_days(captured, trading)
    assert lost == [pd.Timestamp("2026-09-28")]       # before first / after last capture are not "lost"


def test_lost_capture_days_none_when_gap_free_or_empty():
    trading = pd.to_datetime(["2026-09-29", "2026-09-30"])
    assert lost_capture_days(pd.to_datetime(["2026-09-29", "2026-09-30"]), trading) == []
    assert lost_capture_days(pd.DatetimeIndex([]), trading) == []
