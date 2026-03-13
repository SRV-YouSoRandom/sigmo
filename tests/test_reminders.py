"""Tests for scheduler reminder helpers."""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime

from app.core.scheduler import _any_checklist_started_today, _parse_time, _add_minutes
from app.models.session import Session
from app.services.checklist_engine import OPENING_CHECKLISTS


def test_parse_time():
    assert _parse_time("10:00") == (10, 0)
    assert _parse_time("22:30") == (22, 30)
    assert _parse_time("09:05") == (9, 5)


def test_add_minutes_no_wrap():
    assert _add_minutes(10, 0, 20) == (10, 20)
    assert _add_minutes(10, 45, 20) == (11, 5)


def test_add_minutes_wraps_midnight():
    assert _add_minutes(23, 50, 20) == (0, 10)


@pytest.mark.asyncio
async def test_any_checklist_started_today_true(seeded_db):
    """Returns True when a session exists today."""
    session = Session(
        chat_id="123456",
        restaurant_id="R001",
        checklist_id="KITCHEN_OPEN",
        current_step=1,
        status="active",
        started_at=datetime.utcnow(),
    )
    seeded_db.add(session)
    await seeded_db.commit()

    result = await _any_checklist_started_today(seeded_db, "R001", OPENING_CHECKLISTS)
    assert result is True


@pytest.mark.asyncio
async def test_any_checklist_started_today_false(seeded_db):
    """Returns False when no session exists today."""
    result = await _any_checklist_started_today(seeded_db, "R001", OPENING_CHECKLISTS)
    assert result is False


@pytest.mark.asyncio
async def test_opening_followup_skips_if_started(seeded_db):
    """Follow-up job sends nothing if checklist already started."""
    session = Session(
        chat_id="123456",
        restaurant_id="R001",
        checklist_id="KITCHEN_OPEN",
        current_step=1,
        status="active",
        started_at=datetime.utcnow(),
    )
    seeded_db.add(session)
    await seeded_db.commit()

    with patch("app.core.scheduler.send_telegram_message", new_callable=AsyncMock) as mock_send, \
         patch("app.core.scheduler.get_async_session") as mock_factory:
        mock_factory.return_value = AsyncMock()
        mock_factory.return_value().__aenter__ = AsyncMock(return_value=seeded_db)
        mock_factory.return_value().__aexit__ = AsyncMock(return_value=False)

        from app.core.scheduler import _send_opening_followup
        # Patch internals to use seeded_db directly
        with patch("app.core.scheduler._any_checklist_started_today", new_callable=AsyncMock, return_value=True):
            with patch("app.core.scheduler._get_restaurant_and_staff", new_callable=AsyncMock) as mock_rns:
                from app.models.restaurant import Restaurant
                mock_rns.return_value = (
                    Restaurant(restaurant_id="R001", name="Test", manager_chat_id="999"),
                    [],
                )
                await _send_opening_followup("R001")
                mock_send.assert_not_called()