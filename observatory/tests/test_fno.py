"""The participant-OI updater against a fake source — no network."""

from datetime import date

import pandas as pd
import pytest
import requests

from obs import fno, store


def fake_frame(day):
    return pd.DataFrame({"participant": ["FII"], "Future Index Long": [1.0]},
                        index=pd.DatetimeIndex([pd.Timestamp(day)], name="date"))


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "RAW", tmp_path)
    monkeypatch.setattr(fno, "RAW", tmp_path)
    monkeypatch.setattr(fno, "SCANNED", tmp_path / fno.POI_KEY / "_scanned.json")
    today = pd.Period(date.today(), "M")
    return {"start": str(today - 3), "calls": []}


def run(sandbox, monkeypatch, fetch, **kw):
    def counted(day, session):
        sandbox["calls"].append(day)
        return fetch(day)
    monkeypatch.setattr(fno, "fetch_participant_oi", counted)
    return fno.update_participant_oi(start=sandbox["start"], pause=0, log=lambda m: None, **kw)


def weekdays_through_today(start):
    return len(pd.bdate_range(pd.Period(start, "M").start_time, pd.Timestamp(date.today())))


def test_budget_stops_mid_month_then_resumes_without_refetching(sandbox, monkeypatch):
    run(sandbox, monkeypatch, fake_frame, budget=10)
    assert len(sandbox["calls"]) == 10
    assert not fno._scanned()                              # nothing finished, nothing marked

    sandbox["calls"].clear()
    run(sandbox, monkeypatch, fake_frame)
    first_run_days = set(pd.bdate_range(pd.Period(sandbox["start"], "M").start_time, periods=10).date)
    assert not first_run_days & set(sandbox["calls"])      # days already stored are not asked for again
    assert len(sandbox["calls"]) == weekdays_through_today(sandbox["start"]) - 10


def test_failed_month_is_retried_not_skipped(sandbox, monkeypatch):
    start = pd.Period(sandbox["start"], "M")
    bad_day = (start.start_time + pd.offsets.BDay(5)).date()

    def flaky(day):
        if day == bad_day:
            raise requests.ConnectionError("refused")
        return fake_frame(day)

    failed = run(sandbox, monkeypatch, flaky)
    assert failed >= 1
    assert str(start) not in fno._scanned()                # the partial month must not count as done
    assert store.read_partition(fno.POI_KEY, str(start)) is not None   # but its progress is kept

    sandbox["calls"].clear()
    assert run(sandbox, monkeypatch, fake_frame) == 0
    assert str(start) in fno._scanned()
    month_days = [d for d in sandbox["calls"] if pd.Period(d, "M") == start]
    assert bad_day in month_days                           # the failed day is asked for again
    stored_before_failure = set(pd.bdate_range(start.start_time, periods=5).date)
    assert not stored_before_failure & set(month_days)     # days already stored are not


def test_scanned_closed_months_are_skipped_but_recent_months_rescan(sandbox, monkeypatch):
    run(sandbox, monkeypatch, fake_frame)
    sandbox["calls"].clear()
    run(sandbox, monkeypatch, lambda d: None)              # now every day "404s" (holidays)
    months_hit = {pd.Period(d, "M") for d in sandbox["calls"]}
    today = pd.Period(date.today(), "M")
    assert months_hit <= {today - 1, today}                # closed, scanned months were not touched
    assert today - 3 not in months_hit and today - 2 not in months_hit
