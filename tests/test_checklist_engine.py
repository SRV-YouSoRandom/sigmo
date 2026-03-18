"""Tests for the checklist engine – start, progress, complete, abandon, issues."""

import pytest

from app.services.checklist_engine import (
    handle_abandon,
    handle_issue_report,
    progress_step,
    start_checklist,
)
from app.services.session_service import get_active_session, get_paused_session


@pytest.mark.asyncio
async def test_start_checklist_success(seeded_db):
    result = await start_checklist(seeded_db, "123456", "kitchen opening")
    assert "Kitchen Opening" in result["reply"]
    assert "Step 1 of 3" in result["reply"]
    assert "John" in result["manager_msg"]
    assert "Kitchen Opening" in result["manager_msg"]
    assert "Makati" in result["manager_msg"]
    assert result["manager_chat_id"] == "999"
    assert result["session"].status == "active"
    assert result["session"].current_step == 1


@pytest.mark.asyncio
async def test_start_checklist_unknown_user(seeded_db):
    result = await start_checklist(seeded_db, "unknown", "kitchen opening")
    assert "not registered" in result["reply"]
    assert result["session"] is None


@pytest.mark.asyncio
async def test_start_checklist_unknown_command(seeded_db):
    result = await start_checklist(seeded_db, "123456", "foobar")
    assert result["reply"] is None


@pytest.mark.asyncio
async def test_start_checklist_duplicate_session(seeded_db):
    await start_checklist(seeded_db, "123456", "kitchen opening")
    result = await start_checklist(seeded_db, "123456", "kitchen opening")
    assert "already have an active" in result["reply"]


@pytest.mark.asyncio
async def test_progress_step_done(seeded_db):
    await start_checklist(seeded_db, "123456", "kitchen opening")
    result = await progress_step(seeded_db, "123456", is_photo=False)
    assert "Step 2 of 3" in result["reply"]
    assert result["completed"] is False


@pytest.mark.asyncio
async def test_progress_step_requires_photo(seeded_db):
    await start_checklist(seeded_db, "123456", "kitchen opening")
    await progress_step(seeded_db, "123456", is_photo=False)  # step 1 → 2
    result = await progress_step(seeded_db, "123456", is_photo=False)
    assert "requires a photo" in result["reply"]


@pytest.mark.asyncio
async def test_complete_checklist(seeded_db):
    await start_checklist(seeded_db, "123456", "kitchen opening")
    await progress_step(seeded_db, "123456", is_photo=False)        # step 1 → 2
    await progress_step(seeded_db, "123456", is_photo=True, file_id="photo123")  # step 2 → 3
    result = await progress_step(seeded_db, "123456", is_photo=False)  # step 3 → complete
    assert result["completed"] is True
    assert "complete" in result["reply"]
    assert "John" in result["manager_msg"]
    assert "Kitchen Opening" in result["manager_msg"]
    assert "Makati" in result["manager_msg"]


@pytest.mark.asyncio
async def test_progress_no_active_session(seeded_db):
    result = await progress_step(seeded_db, "123456", is_photo=False)
    assert "No active checklist" in result["reply"]


@pytest.mark.asyncio
async def test_abandon_checklist(seeded_db):
    await start_checklist(seeded_db, "123456", "kitchen opening")
    result = await handle_abandon(seeded_db, "123456")
    assert "cancelled" in result["reply"]


@pytest.mark.asyncio
async def test_abandon_no_session(seeded_db):
    result = await handle_abandon(seeded_db, "123456")
    assert "No active checklist" in result["reply"]


# ---------------------------------------------------------------------------
# Issue report tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_operational_issue_auto_advances(seeded_db):
    """Operational issue should auto-advance to the next step."""
    await start_checklist(seeded_db, "123456", "kitchen opening")
    # Currently on step 1
    result = await handle_issue_report(seeded_db, "123456", "Broken switch", "operational")
    assert result["completed"] is False
    assert "Step 2 of 3" in result["reply"]
    assert "🟡" in result["manager_msg"]
    # Session should still be active
    session = await get_active_session(seeded_db, "123456")
    assert session is not None
    assert session.current_step == 2


@pytest.mark.asyncio
async def test_critical_issue_pauses_checklist(seeded_db):
    """Critical issue should pause the session."""
    await start_checklist(seeded_db, "123456", "kitchen opening")
    result = await handle_issue_report(seeded_db, "123456", "Gas leak detected", "critical")
    assert "paused" in result["reply"].lower()
    assert "🔴" in result["manager_msg"]
    # Session must be paused
    session = await get_paused_session(seeded_db, "123456")
    assert session is not None
    assert session.status == "paused"
    assert session.current_step == 1  # did not advance


@pytest.mark.asyncio
async def test_cannot_progress_paused_checklist(seeded_db):
    """Staff should not be able to advance a paused checklist."""
    await start_checklist(seeded_db, "123456", "kitchen opening")
    await handle_issue_report(seeded_db, "123456", "Fire!", "critical")
    result = await progress_step(seeded_db, "123456", is_photo=False)
    assert "paused" in result["reply"].lower()


@pytest.mark.asyncio
async def test_operational_issue_on_last_step_completes(seeded_db):
    """Operational issue on the last step should complete the checklist."""
    await start_checklist(seeded_db, "123456", "kitchen opening")
    await progress_step(seeded_db, "123456", is_photo=False)                      # → step 2
    await progress_step(seeded_db, "123456", is_photo=True, file_id="photo123")   # → step 3
    # Now on step 3 (last step) — report an operational issue
    result = await handle_issue_report(seeded_db, "123456", "Minor spill", "operational")
    assert result["completed"] is True