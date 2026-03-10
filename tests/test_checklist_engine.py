"""Tests for the checklist engine – start, progress, complete, abandon."""

import pytest

from app.services.checklist_engine import handle_abandon, progress_step, start_checklist


@pytest.mark.asyncio
async def test_start_checklist_success(seeded_db):
    """Starting a valid checklist creates a session and returns step 1."""
    result = await start_checklist(seeded_db, "123456", "kitchen opening")

    assert result["reply"] is not None
    assert "Starting Kitchen Opening" in result["reply"]
    assert "Step 1 of 3" in result["reply"]
    assert result["manager_msg"] is not None
    assert "John started Kitchen Opening" in result["manager_msg"]
    assert result["manager_chat_id"] == "999"
    assert result["session"] is not None
    assert result["session"].status == "active"
    assert result["session"].current_step == 1


@pytest.mark.asyncio
async def test_start_checklist_unknown_user(seeded_db):
    """Unknown chat_id returns a registration error."""
    result = await start_checklist(seeded_db, "unknown", "kitchen opening")
    assert "not registered" in result["reply"]
    assert result["session"] is None


@pytest.mark.asyncio
async def test_start_checklist_unknown_command(seeded_db):
    """Unknown command returns None reply."""
    result = await start_checklist(seeded_db, "123456", "foobar")
    assert result["reply"] is None


@pytest.mark.asyncio
async def test_start_checklist_duplicate_session(seeded_db):
    """Starting a second checklist while one is active prompts the user."""
    await start_checklist(seeded_db, "123456", "kitchen opening")
    result = await start_checklist(seeded_db, "123456", "kitchen opening")
    assert "already have an active" in result["reply"]


@pytest.mark.asyncio
async def test_progress_step_done(seeded_db):
    """Replying 'done' to a non-photo step advances to the next step."""
    await start_checklist(seeded_db, "123456", "kitchen opening")
    result = await progress_step(seeded_db, "123456", is_photo=False)
    assert "Step 2 of 3" in result["reply"]
    assert result["completed"] is False


@pytest.mark.asyncio
async def test_progress_step_requires_photo(seeded_db):
    """Step 2 requires a photo – sending 'done' is rejected."""
    await start_checklist(seeded_db, "123456", "kitchen opening")
    await progress_step(seeded_db, "123456", is_photo=False)  # advance to step 2

    result = await progress_step(seeded_db, "123456", is_photo=False)
    assert "requires a photo" in result["reply"]


@pytest.mark.asyncio
async def test_complete_checklist(seeded_db):
    """Completing all steps marks the checklist as done."""
    await start_checklist(seeded_db, "123456", "kitchen opening")
    await progress_step(seeded_db, "123456", is_photo=False)  # step 1 → 2
    await progress_step(seeded_db, "123456", is_photo=True, file_id="photo123")  # step 2 → 3
    result = await progress_step(seeded_db, "123456", is_photo=False)  # step 3 → complete

    assert result["completed"] is True
    assert "Checklist complete" in result["reply"]
    assert "Kitchen Opening" in result["reply"]
    assert result["manager_msg"] is not None
    assert "John completed Kitchen Opening" in result["manager_msg"]


@pytest.mark.asyncio
async def test_progress_no_active_session(seeded_db):
    """Progress with no active session returns guidance."""
    result = await progress_step(seeded_db, "123456", is_photo=False)
    assert "No active checklist" in result["reply"]


@pytest.mark.asyncio
async def test_abandon_checklist(seeded_db):
    """Abandoning an active session flags it."""
    await start_checklist(seeded_db, "123456", "kitchen opening")
    result = await handle_abandon(seeded_db, "123456")
    assert "abandoned" in result["reply"]


@pytest.mark.asyncio
async def test_abandon_no_session(seeded_db):
    """Abandoning when nothing is active returns info message."""
    result = await handle_abandon(seeded_db, "123456")
    assert "No active checklist" in result["reply"]
