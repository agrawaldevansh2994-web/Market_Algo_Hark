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


def test_with_retry_recovers_from_transient_failures():
    from obs.flows import with_retry
    calls, waits = [], []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("blip")
        return "ok"

    assert with_retry(flaky, waits=(1, 2, 3), sleep=waits.append) == "ok"
    assert waits == [1, 2]


def test_with_retry_reraises_after_last_attempt():
    import pytest
    from obs.flows import with_retry

    def dead():
        raise TimeoutError("down")

    with pytest.raises(TimeoutError):
        with_retry(dead, waits=(1, 1), sleep=lambda s: None)
