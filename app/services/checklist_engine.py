"""Core checklist engine – start, progress, complete, abandon, and issue reporting."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.commands import parse_command
from app.models.checklist_run import ChecklistRun
from app.models.checklist_step import ChecklistStep
from app.models.issue_report import IssueReport
from app.models.session import Session
from app.models.staff import Staff
from app.models.step_photo import StepPhoto
from app.services.session_service import (
    abandon_session,
    complete_session,
    create_session,
    get_active_session,
    update_session_step,
)

CHECKLIST_LABELS: dict[str, str] = {
    "KITCHEN_OPEN": "Kitchen Opening",
    "KITCHEN_CLOSE": "Kitchen Closing",
    "DINING_OPEN": "Dining Opening",
    "DINING_CLOSE": "Dining Closing",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_staff(db: AsyncSession, chat_id: str) -> Staff | None:
    result = await db.execute(select(Staff).where(Staff.chat_id == chat_id))
    return result.scalars().first()


async def _get_step(
    db: AsyncSession, restaurant_id: str, checklist_id: str, step_number: int
) -> ChecklistStep | None:
    result = await db.execute(
        select(ChecklistStep).where(
            ChecklistStep.restaurant_id == restaurant_id,
            ChecklistStep.checklist_id == checklist_id,
            ChecklistStep.step_number == step_number,
        )
    )
    return result.scalars().first()


async def _count_steps(db: AsyncSession, restaurant_id: str, checklist_id: str) -> int:
    result = await db.execute(
        select(func.count(ChecklistStep.id)).where(
            ChecklistStep.restaurant_id == restaurant_id,
            ChecklistStep.checklist_id == checklist_id,
        )
    )
    return result.scalar() or 0


async def _count_photos(db: AsyncSession, session_id: int) -> int:
    result = await db.execute(
        select(func.count(StepPhoto.id)).where(StepPhoto.session_id == session_id)
    )
    return result.scalar() or 0


async def _get_restaurant(db: AsyncSession, restaurant_id: str):
    from app.models.restaurant import Restaurant
    res = await db.execute(
        select(Restaurant).where(Restaurant.restaurant_id == restaurant_id)
    )
    return res.scalars().first()


def _format_step_message(step: ChecklistStep, total_steps: int) -> str:
    """Format step instruction text. Buttons are added by send_step_message in notifier."""
    return f"Step {step.step_number} of {total_steps} – {step.instruction}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def start_checklist(db: AsyncSession, chat_id: str, text: str) -> dict:
    checklist_id = parse_command(text)
    if checklist_id is None:
        return {"reply": None, "use_buttons": False, "manager_msg": None, "manager_chat_id": None, "session": None}

    staff = await _get_staff(db, chat_id)
    if staff is None:
        return {
            "reply": "You are not registered in the system. Please contact your manager.",
            "use_buttons": False,
            "manager_msg": None,
            "manager_chat_id": None,
            "session": None,
        }

    existing = await get_active_session(db, chat_id)
    if existing:
        label = CHECKLIST_LABELS.get(existing.checklist_id, existing.checklist_id)
        return {
            "reply": (
                f"You already have an active checklist: {label}.\n"
                "Tap Done to continue, or send ABANDON to cancel it."
            ),
            "use_buttons": False,
            "manager_msg": None,
            "manager_chat_id": None,
            "session": existing,
        }

    total_steps = await _count_steps(db, staff.restaurant_id, checklist_id)
    if total_steps == 0:
        return {
            "reply": "No steps configured for this checklist. Please contact your manager.",
            "use_buttons": False,
            "manager_msg": None,
            "manager_chat_id": None,
            "session": None,
        }

    session = await create_session(db, chat_id, staff.restaurant_id, checklist_id)
    step = await _get_step(db, staff.restaurant_id, checklist_id, 1)

    label = CHECKLIST_LABELS.get(checklist_id, checklist_id)
    now = datetime.utcnow().strftime("%I:%M %p")

    reply = f"Starting {label} checklist.\n{_format_step_message(step, total_steps)}"
    restaurant = await _get_restaurant(db, staff.restaurant_id)

    return {
        "reply": reply,
        "use_buttons": True,
        "manager_msg": f"{staff.name} started {label} at {now}",
        "manager_chat_id": restaurant.manager_chat_id if restaurant else None,
        "session": session,
    }


async def progress_step(
    db: AsyncSession, chat_id: str, is_photo: bool = False, file_id: str | None = None
) -> dict:
    session = await get_active_session(db, chat_id)
    if session is None:
        return {
            "reply": "No active checklist. Send a command like 'kitchen opening' to start one.",
            "use_buttons": False,
            "manager_msg": None,
            "manager_chat_id": None,
            "completed": False,
        }

    current_step = await _get_step(
        db, session.restaurant_id, session.checklist_id, session.current_step
    )
    if current_step is None:
        return {
            "reply": "Step data is missing. Please contact your manager.",
            "use_buttons": False,
            "manager_msg": None,
            "manager_chat_id": None,
            "completed": False,
        }

    total_steps = await _count_steps(db, session.restaurant_id, session.checklist_id)

    if current_step.requires_photo and not is_photo:
        return {
            "reply": "This step requires a photo. Please send a photo to continue.",
            "use_buttons": False,
            "manager_msg": None,
            "manager_chat_id": None,
            "completed": False,
        }

    manager_photo_msg = None
    if is_photo and file_id:
        photo = StepPhoto(
            session_id=session.id,
            step_number=session.current_step,
            file_id=file_id,
        )
        db.add(photo)
        await db.commit()

        staff = await _get_staff(db, chat_id)
        label = CHECKLIST_LABELS.get(session.checklist_id, session.checklist_id)
        manager_photo_msg = (
            f"📸 {staff.name} sent a photo for {label} – Step {session.current_step}"
            if staff else None
        )

    next_step_num = session.current_step + 1

    if next_step_num > total_steps:
        return await _complete_checklist(db, session, total_steps)

    await update_session_step(db, session, next_step_num)
    next_step = await _get_step(
        db, session.restaurant_id, session.checklist_id, next_step_num
    )

    reply_parts = []
    if is_photo:
        reply_parts.append("Photo received. Moving on.")
    reply_parts.append(_format_step_message(next_step, total_steps))
    reply = "\n".join(reply_parts)

    manager_chat_id = None
    if manager_photo_msg:
        restaurant = await _get_restaurant(db, session.restaurant_id)
        manager_chat_id = restaurant.manager_chat_id if restaurant else None

    return {
        "reply": reply,
        "use_buttons": True,
        "manager_msg": manager_photo_msg,
        "manager_chat_id": manager_chat_id,
        "completed": False,
    }


async def _complete_checklist(db: AsyncSession, session: Session, total_steps: int) -> dict:
    await complete_session(db, session)

    photo_count = await _count_photos(db, session.id)
    run = ChecklistRun(
        chat_id=session.chat_id,
        restaurant_id=session.restaurant_id,
        checklist_id=session.checklist_id,
        start_time=session.started_at,
        end_time=datetime.utcnow(),
        status="completed",
        photo_count=photo_count,
    )
    db.add(run)
    await db.commit()

    duration = datetime.utcnow() - session.started_at
    minutes = int(duration.total_seconds() // 60)
    label = CHECKLIST_LABELS.get(session.checklist_id, session.checklist_id)
    reply = f"✅ Checklist complete. {label} finished in {minutes} minutes."

    staff = await _get_staff(db, session.chat_id)
    start_str = session.started_at.strftime("%I:%M %p")
    end_str = datetime.utcnow().strftime("%I:%M %p")
    manager_msg = (
        f"{staff.name} completed {label}. Start: {start_str} | Finish: {end_str}"
        if staff else None
    )

    restaurant = await _get_restaurant(db, session.restaurant_id)
    return {
        "reply": reply,
        "use_buttons": False,
        "manager_msg": manager_msg,
        "manager_chat_id": restaurant.manager_chat_id if restaurant else None,
        "completed": True,
    }


async def handle_abandon(db: AsyncSession, chat_id: str) -> dict:
    session = await get_active_session(db, chat_id)
    if session is None:
        return {"reply": "No active checklist to abandon.", "use_buttons": False, "manager_msg": None, "manager_chat_id": None}

    await abandon_session(db, session)

    photo_count = await _count_photos(db, session.id)
    run = ChecklistRun(
        chat_id=session.chat_id,
        restaurant_id=session.restaurant_id,
        checklist_id=session.checklist_id,
        start_time=session.started_at,
        end_time=datetime.utcnow(),
        status="abandoned",
        photo_count=photo_count,
    )
    db.add(run)
    await db.commit()

    label = CHECKLIST_LABELS.get(session.checklist_id, session.checklist_id)
    return {
        "reply": f"{label} checklist abandoned.",
        "use_buttons": False,
        "manager_msg": None,
        "manager_chat_id": None,
    }


async def handle_issue_report(
    db: AsyncSession, chat_id: str, description: str
) -> dict:
    """Log a critical issue for the current step and notify the manager."""
    session = await get_active_session(db, chat_id)
    if session is None:
        return {
            "reply": "No active checklist. Start a checklist first.",
            "use_buttons": False,
            "manager_msg": None,
            "manager_chat_id": None,
        }

    staff = await _get_staff(db, chat_id)
    label = CHECKLIST_LABELS.get(session.checklist_id, session.checklist_id)

    issue = IssueReport(
        session_id=session.id,
        chat_id=chat_id,
        restaurant_id=session.restaurant_id,
        checklist_id=session.checklist_id,
        step_number=session.current_step,
        description=description,
    )
    db.add(issue)
    await db.commit()

    staff_name = staff.name if staff else chat_id
    manager_msg = (
        f"⚠️ Critical Issue Reported\n"
        f"Staff: {staff_name}\n"
        f"Checklist: {label}\n"
        f"Step: {session.current_step}\n"
        f"Issue: {description}"
    )

    restaurant = await _get_restaurant(db, session.restaurant_id)

    # Get total steps to re-send the current step with buttons after issue is logged
    total_steps = await _count_steps(db, session.restaurant_id, session.checklist_id)
    current_step = await _get_step(
        db, session.restaurant_id, session.checklist_id, session.current_step
    )
    step_msg = _format_step_message(current_step, total_steps) if current_step else ""

    return {
        "reply": f"Issue reported. You can continue with the checklist.\n{step_msg}",
        "use_buttons": True,
        "manager_msg": manager_msg,
        "manager_chat_id": restaurant.manager_chat_id if restaurant else None,
    }