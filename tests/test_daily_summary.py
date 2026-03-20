"""Tests for the daily summary builder."""

from datetime import datetime, timedelta

import pytest

from app.models.checklist_run import ChecklistRun
from app.models.issue_report import IssueReport
from app.models.session import Session
from app.services.report_service import (
    build_summary_message,
    get_issues_for_yesterday,
    get_runs_for_yesterday,
    _pht_day_window,
)


# ---------------------------------------------------------------------------
# PHT window helper
# ---------------------------------------------------------------------------

def test_pht_day_window_span_is_24h():
    start, end = _pht_day_window()
    assert (end - start).total_seconds() == 86400


def test_pht_day_window_end_is_16h_utc():
    """Window end should be 16:00 UTC (= midnight PHT today)."""
    _, end = _pht_day_window()
    assert end.hour == 16
    assert end.minute == 0


# ---------------------------------------------------------------------------
# get_runs_for_yesterday
# ---------------------------------------------------------------------------

def _yesterday_pht_run(hour_pht: int, minute: int = 0) -> tuple[datetime, datetime]:
    """Return (start, end) UTC datetimes for a run at the given PHT hour yesterday."""
    start, _ = _pht_day_window()
    # start is 16:00 UTC two days ago = 00:00 PHT yesterday
    run_start = start + timedelta(hours=hour_pht, minutes=minute)
    run_end = run_start + timedelta(minutes=15)
    return run_start, run_end


@pytest.mark.asyncio
async def test_get_runs_includes_completed(seeded_db):
    s, e = _yesterday_pht_run(8)
    seeded_db.add(ChecklistRun(
        chat_id="123456", restaurant_id="R001", checklist_id="KITCHEN_OPEN",
        start_time=s, end_time=e, status="completed", photo_count=2,
    ))
    await seeded_db.commit()
    runs = await get_runs_for_yesterday(seeded_db, "R001")
    assert len(runs) == 1
    assert runs[0]["status"] == "completed"
    assert runs[0]["photo_count"] == 2
    assert runs[0]["staff_name"] == "John"


@pytest.mark.asyncio
async def test_get_runs_includes_abandoned(seeded_db):
    s, e = _yesterday_pht_run(9)
    seeded_db.add(ChecklistRun(
        chat_id="123456", restaurant_id="R001", checklist_id="KITCHEN_OPEN",
        start_time=s, end_time=e, status="abandoned", photo_count=0,
    ))
    await seeded_db.commit()
    runs = await get_runs_for_yesterday(seeded_db, "R001")
    assert any(r["status"] == "abandoned" for r in runs)


@pytest.mark.asyncio
async def test_get_runs_captures_late_night_close(seeded_db):
    """A run ending at 23:45 PHT (15:45 UTC) must be included — was missed by old UTC window."""
    s, e = _yesterday_pht_run(23, 30)   # 23:30 PHT yesterday
    seeded_db.add(ChecklistRun(
        chat_id="123456", restaurant_id="R001", checklist_id="KITCHEN_CLOSE",
        start_time=s, end_time=e, status="completed", photo_count=0,
    ))
    await seeded_db.commit()
    runs = await get_runs_for_yesterday(seeded_db, "R001")
    assert len(runs) == 1


@pytest.mark.asyncio
async def test_get_runs_excludes_today(seeded_db):
    """A run that started today (PHT) must NOT appear in yesterday's summary."""
    _, window_end = _pht_day_window()
    # 30 minutes after the window closes = today PHT
    future = window_end + timedelta(minutes=30)
    seeded_db.add(ChecklistRun(
        chat_id="123456", restaurant_id="R001", checklist_id="KITCHEN_OPEN",
        start_time=future, end_time=future + timedelta(minutes=10),
        status="completed", photo_count=0,
    ))
    await seeded_db.commit()
    runs = await get_runs_for_yesterday(seeded_db, "R001")
    assert runs == []


@pytest.mark.asyncio
async def test_get_runs_empty(seeded_db):
    runs = await get_runs_for_yesterday(seeded_db, "R001")
    assert runs == []


# ---------------------------------------------------------------------------
# get_issues_for_yesterday
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_issues_for_yesterday(seeded_db):
    from app.models.session import Session
    session = Session(
        chat_id="123456", restaurant_id="R001", checklist_id="KITCHEN_OPEN",
        current_step=1, status="active", started_at=datetime.utcnow(),
    )
    seeded_db.add(session)
    await seeded_db.commit()
    await seeded_db.refresh(session)

    window_start, _ = _pht_day_window()
    reported = window_start + timedelta(hours=10)

    issue = IssueReport(
        session_id=session.id,
        chat_id="123456",
        restaurant_id="R001",
        checklist_id="KITCHEN_OPEN",
        step_number=1,
        issue_type="critical",
        description="Gas leak",
        reported_at=reported,
        resolved=False,
    )
    seeded_db.add(issue)
    await seeded_db.commit()

    issues = await get_issues_for_yesterday(seeded_db, "R001")
    assert len(issues) == 1
    assert issues[0]["issue_type"] == "critical"
    assert issues[0]["staff_name"] == "John"
    assert issues[0]["resolved"] is False


# ---------------------------------------------------------------------------
# build_summary_message
# ---------------------------------------------------------------------------

def _make_run(checklist_id: str, status: str = "completed", photos: int = 0) -> dict:
    base = datetime(2026, 1, 1, 8, 0)
    return {
        "checklist_id": checklist_id,
        "staff_name": "John",
        "start_time": base,
        "end_time": base + timedelta(minutes=14),
        "status": status,
        "photo_count": photos,
        "duration_seconds": 840.0,
    }


def _make_issue(issue_type: str, resolved: bool = False) -> dict:
    return {
        "issue_type": issue_type,
        "staff_name": "John",
        "checklist_id": "KITCHEN_OPEN",
        "step_number": 2,
        "description": "Broken switch",
        "resolved": resolved,
        "reported_at": datetime(2026, 1, 1, 8, 5),
    }


def test_build_summary_completed_run():
    msg = build_summary_message([_make_run("KITCHEN_OPEN")], date_str="2026-01-01")
    assert "SIGMO DAILY REPORT" in msg
    assert "Kitchen Opening" in msg
    assert "John" in msg
    assert "14m 0s" in msg
    assert "Completion:  1/1 checklists done" in msg


def test_build_summary_shows_photo_count():
    run = _make_run("KITCHEN_OPEN", photos=3)
    msg = build_summary_message([run], date_str="2026-01-01")
    assert "📷 3" in msg


def test_build_summary_abandoned_run():
    msg = build_summary_message([_make_run("KITCHEN_OPEN", status="abandoned")], date_str="2026-01-01")
    assert "Abandoned" in msg
    assert "cancelled" in msg
    assert "Completion:  0/1 checklists done" in msg


def test_build_summary_missed_checklists():
    # Only KITCHEN_OPEN completed — other 3 should be flagged
    msg = build_summary_message([_make_run("KITCHEN_OPEN")], date_str="2026-01-01")
    assert "Not Done Yesterday" in msg
    assert "Kitchen Closing" in msg
    assert "Dining Opening" in msg
    assert "Dining Closing" in msg


def test_build_summary_all_done_no_missed():
    runs = [
        _make_run("KITCHEN_OPEN"),
        _make_run("KITCHEN_CLOSE"),
        _make_run("DINING_OPEN"),
        _make_run("DINING_CLOSE"),
    ]
    msg = build_summary_message(runs, date_str="2026-01-01")
    assert "Not Done Yesterday" not in msg


def test_build_summary_critical_issue():
    msg = build_summary_message(
        [_make_run("KITCHEN_OPEN")],
        issues=[_make_issue("critical", resolved=False)],
        date_str="2026-01-01",
    )
    assert "Critical" in msg
    assert "UNRESOLVED" in msg
    assert "Broken switch" in msg


def test_build_summary_resolved_issue():
    msg = build_summary_message(
        [_make_run("KITCHEN_OPEN")],
        issues=[_make_issue("critical", resolved=True)],
        date_str="2026-01-01",
    )
    assert "resolved" in msg
    assert "unresolved" not in msg


def test_build_summary_totals_with_issues():
    msg = build_summary_message(
        [_make_run("KITCHEN_OPEN")],
        issues=[_make_issue("operational")],
        date_str="2026-01-01",
    )
    assert "Issues:      1 reported" in msg
    assert "still open" in msg


def test_build_summary_empty():
    msg = build_summary_message([], date_str="2026-01-01")
    assert "SIGMO DAILY REPORT" in msg
    assert "No activity" in msg


def test_build_summary_with_restaurant_branch():
    class FakeRestaurant:
        name = "Sigmo Bistro"
        branch = "Makati"
    msg = build_summary_message([], restaurant=FakeRestaurant(), date_str="2026-01-01")
    assert "Sigmo Bistro – Makati" in msg