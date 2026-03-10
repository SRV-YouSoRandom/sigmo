"""Tests for the daily summary builder."""

from datetime import datetime, timedelta

import pytest

from app.services.report_service import build_summary_message, get_runs_for_yesterday
from app.models.checklist_run import ChecklistRun


@pytest.mark.asyncio
async def test_get_runs_for_yesterday_returns_completed(seeded_db):
    """Runs from yesterday are returned."""
    yesterday = datetime.utcnow() - timedelta(days=1)
    run = ChecklistRun(
        chat_id="123456",
        restaurant_id="R001",
        checklist_id="KITCHEN_OPEN",
        start_time=yesterday.replace(hour=8, minute=0),
        end_time=yesterday.replace(hour=8, minute=14),
        status="completed",
        photo_count=1,
    )
    seeded_db.add(run)
    await seeded_db.commit()

    runs = await get_runs_for_yesterday(seeded_db, "R001")
    assert len(runs) == 1
    assert runs[0]["staff_name"] == "John"
    assert runs[0]["checklist_id"] == "KITCHEN_OPEN"


@pytest.mark.asyncio
async def test_get_runs_for_yesterday_empty(seeded_db):
    """No runs return an empty list."""
    runs = await get_runs_for_yesterday(seeded_db, "R001")
    assert runs == []


def test_build_summary_message():
    """Summary message is correctly formatted."""
    runs = [
        {
            "checklist_id": "KITCHEN_OPEN",
            "staff_name": "John",
            "start_time": datetime(2026, 1, 1, 8, 2),
            "end_time": datetime(2026, 1, 1, 8, 14),
        },
        {
            "checklist_id": "DINING_OPEN",
            "staff_name": "Maria",
            "start_time": datetime(2026, 1, 1, 9, 0),
            "end_time": datetime(2026, 1, 1, 9, 11),
        },
    ]
    msg = build_summary_message(runs, date_str="2026-01-01")
    assert "Sigmo Daily Report" in msg
    assert "Kitchen Opening" in msg
    assert "John" in msg
    assert "Dining Opening" in msg
    assert "Maria" in msg


def test_build_summary_message_empty():
    """Empty runs list still produces a header."""
    msg = build_summary_message([], date_str="2026-01-01")
    assert "Sigmo Daily Report" in msg
