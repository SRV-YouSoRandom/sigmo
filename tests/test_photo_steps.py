"""Tests for photo step detection and storage."""

import pytest

from app.models.step_photo import StepPhoto
from app.services.checklist_engine import progress_step, start_checklist
from sqlalchemy import select


@pytest.mark.asyncio
async def test_photo_step_stores_file_id(seeded_db):
    """Sending a photo on a photo-required step stores the file_id."""
    await start_checklist(seeded_db, "123456", "kitchen opening")
    await progress_step(seeded_db, "123456", is_photo=False)  # step 1 → 2 (photo step)

    result = await progress_step(
        seeded_db, "123456", is_photo=True, file_id="telegram_photo_abc"
    )

    assert "Photo received" in result["reply"]

    # Verify photo was stored
    photos = await seeded_db.execute(select(StepPhoto))
    photo = photos.scalars().first()
    assert photo is not None
    assert photo.file_id == "telegram_photo_abc"
    assert photo.step_number == 2


@pytest.mark.asyncio
async def test_photo_step_rejects_done(seeded_db):
    """Sending 'done' on a photo-required step is rejected."""
    await start_checklist(seeded_db, "123456", "kitchen opening")
    await progress_step(seeded_db, "123456", is_photo=False)  # step 1 → 2

    result = await progress_step(seeded_db, "123456", is_photo=False)
    assert "requires a photo" in result["reply"]


@pytest.mark.asyncio
async def test_non_photo_step_accepts_done(seeded_db):
    """Sending 'done' on a non-photo step advances normally."""
    await start_checklist(seeded_db, "123456", "kitchen opening")
    result = await progress_step(seeded_db, "123456", is_photo=False)  # step 1 (non-photo)
    assert "Step 2 of 3" in result["reply"]
