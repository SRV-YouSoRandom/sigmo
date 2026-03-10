"""Core checklist engine – start, progress, and complete checklist flows."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.commands import parse_command
from app.models.checklist_run import ChecklistRun
from app.models.checklist_step import ChecklistStep
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CHECKLIST_LABELS: dict[str, str] = {
    "KITCHEN_OPEN": "Kitchen Opening",
    "KITCHEN_CLOSE": "Kitchen Closing",
    "DINING_OPEN": "Dining Opening",
    "DINING_CLOSE": "Dining Closing",
}


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


async def _count_steps(
    db: AsyncSession, restaurant_id: str, checklist_id: str
) -> int:
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


def _format_step_message(step: ChecklistStep, total_steps: int) -> str:
    msg = f"Step {step.step_number} of {total_steps} – {step.instruction}"
    if step.requires_photo:
        msg += "\nSend a photo when finished."
    else:
        msg += "\nReply DONE when finished."
    return msg


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def start_checklist(
    db: AsyncSession, chat_id: str, text: str
) -> dict:
    """Attempt to start a checklist from a staff text command.

    Returns a dict with keys:
        - reply: str          – message to send back to the staff member
        - manager_msg: str|None – notification for the manager (if applicable)
        - manager_chat_id: str|None
        - session: Session|None
    """
    checklist_id = parse_command(text)
    if checklist_id is None:
        return {"reply": None, "manager_msg": None, "manager_chat_id": None, "session": None}

    staff = await _get_staff(db, chat_id)
    if staff is None:
        return {
            "reply": "You are not registered in the system. Please contact your manager.",
            "manager_msg": None,
            "manager_chat_id": None,
            "session": None,
        }

    # Check for an existing active session
    existing = await get_active_session(db, chat_id)
    if existing:
        label = CHECKLIST_LABELS.get(existing.checklist_id, existing.checklist_id)
        return {
            "reply": (
                f"You already have an active checklist: {label}.\n"
                "Reply DONE to continue, or send ABANDON to cancel it."
            ),
            "manager_msg": None,
            "manager_chat_id": None,
            "session": existing,
        }

    total_steps = await _count_steps(db, staff.restaurant_id, checklist_id)
    if total_steps == 0:
        return {
            "reply": "No steps configured for this checklist. Please contact your manager.",
            "manager_msg": None,
            "manager_chat_id": None,
            "session": None,
        }

    session = await create_session(db, chat_id, staff.restaurant_id, checklist_id)
    step = await _get_step(db, staff.restaurant_id, checklist_id, 1)

    label = CHECKLIST_LABELS.get(checklist_id, checklist_id)
    now = datetime.utcnow().strftime("%I:%M %p")

    reply = f"Starting {label} checklist.\n{_format_step_message(step, total_steps)}"

    # Manager notification
    from app.models.restaurant import Restaurant

    res = await db.execute(
        select(Restaurant).where(Restaurant.restaurant_id == staff.restaurant_id)
    )
    restaurant = res.scalars().first()
    manager_msg = f"{staff.name} started {label} at {now}"

    return {
        "reply": reply,
        "manager_msg": manager_msg,
        "manager_chat_id": restaurant.manager_chat_id if restaurant else None,
        "session": session,
    }


async def progress_step(
    db: AsyncSession, chat_id: str, is_photo: bool = False, file_id: str | None = None
) -> dict:
    """Advance the current session by one step.

    Returns a dict with keys:
        - reply: str          – message to send back to staff
        - manager_msg: str|None
        - manager_chat_id: str|None
        - completed: bool
    """
    session = await get_active_session(db, chat_id)
    if session is None:
        return {
            "reply": "No active checklist. Send a command like 'kitchen opening' to start one.",
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
            "manager_msg": None,
            "manager_chat_id": None,
            "completed": False,
        }

    total_steps = await _count_steps(db, session.restaurant_id, session.checklist_id)

    # Validate input type
    if current_step.requires_photo and not is_photo:
        return {
            "reply": "This step requires a photo. Please send a photo to continue.",
            "manager_msg": None,
            "manager_chat_id": None,
            "completed": False,
        }

    # Store photo if provided
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
            if staff
            else None
        )

    next_step_num = session.current_step + 1

    # Check if we've completed all steps
    if next_step_num > total_steps:
        return await _complete_checklist(db, session, total_steps)

    # Advance to next step
    await update_session_step(db, session, next_step_num)
    next_step = await _get_step(
        db, session.restaurant_id, session.checklist_id, next_step_num
    )

    reply_parts = []
    if is_photo:
        reply_parts.append("Photo received. Moving on.")
    reply_parts.append(_format_step_message(next_step, total_steps))
    reply = "\n".join(reply_parts)

    # Get manager chat_id for photo notification
    manager_chat_id = None
    if manager_photo_msg:
        from app.models.restaurant import Restaurant

        res = await db.execute(
            select(Restaurant).where(Restaurant.restaurant_id == session.restaurant_id)
        )
        restaurant = res.scalars().first()
        manager_chat_id = restaurant.manager_chat_id if restaurant else None

    return {
        "reply": reply,
        "manager_msg": manager_photo_msg,
        "manager_chat_id": manager_chat_id,
        "completed": False,
    }


async def _complete_checklist(
    db: AsyncSession, session: Session, total_steps: int
) -> dict:
    """Finalize a completed checklist."""
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

    # Manager notification
    staff = await _get_staff(db, session.chat_id)
    start_str = session.started_at.strftime("%I:%M %p")
    end_str = datetime.utcnow().strftime("%I:%M %p")
    manager_msg = (
        f"{staff.name} completed {label}. "
        f"Start: {start_str} | Finish: {end_str}"
        if staff
        else None
    )

    from app.models.restaurant import Restaurant

    res = await db.execute(
        select(Restaurant).where(Restaurant.restaurant_id == session.restaurant_id)
    )
    restaurant = res.scalars().first()

    return {
        "reply": reply,
        "manager_msg": manager_msg,
        "manager_chat_id": restaurant.manager_chat_id if restaurant else None,
        "completed": True,
    }


async def handle_abandon(db: AsyncSession, chat_id: str) -> dict:
    """Abandon the active session."""
    session = await get_active_session(db, chat_id)
    if session is None:
        return {
            "reply": "No active checklist to abandon.",
            "manager_msg": None,
            "manager_chat_id": None,
        }

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
        "manager_msg": None,
        "manager_chat_id": None,
    }
