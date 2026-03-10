"""Tests for session service CRUD operations."""

import pytest

from app.services.session_service import (
    abandon_session,
    complete_session,
    create_session,
    get_active_session,
    update_session_step,
)


@pytest.mark.asyncio
async def test_create_session(seeded_db):
    session = await create_session(seeded_db, "123456", "R001", "KITCHEN_OPEN")
    assert session.chat_id == "123456"
    assert session.restaurant_id == "R001"
    assert session.checklist_id == "KITCHEN_OPEN"
    assert session.current_step == 1
    assert session.status == "active"


@pytest.mark.asyncio
async def test_get_active_session(seeded_db):
    await create_session(seeded_db, "123456", "R001", "KITCHEN_OPEN")
    active = await get_active_session(seeded_db, "123456")
    assert active is not None
    assert active.status == "active"


@pytest.mark.asyncio
async def test_get_active_session_none(seeded_db):
    active = await get_active_session(seeded_db, "123456")
    assert active is None


@pytest.mark.asyncio
async def test_update_session_step(seeded_db):
    session = await create_session(seeded_db, "123456", "R001", "KITCHEN_OPEN")
    await update_session_step(seeded_db, session, 2)

    refreshed = await get_active_session(seeded_db, "123456")
    assert refreshed.current_step == 2


@pytest.mark.asyncio
async def test_complete_session(seeded_db):
    session = await create_session(seeded_db, "123456", "R001", "KITCHEN_OPEN")
    await complete_session(seeded_db, session)

    active = await get_active_session(seeded_db, "123456")
    assert active is None  # no longer active


@pytest.mark.asyncio
async def test_abandon_session(seeded_db):
    session = await create_session(seeded_db, "123456", "R001", "KITCHEN_OPEN")
    await abandon_session(seeded_db, session)

    active = await get_active_session(seeded_db, "123456")
    assert active is None
