"""Core checklist engine – start, progress, complete, abandon, and issue reporting."""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.commands import parse_command
from app.core.config import to_pht
from app.metrics.prometheus import (
    active_sessions,
    checklist_abandoned,
    checklist_completed,
    checklist_duration,
    checklist_started,
    issues_reported,
    photos_submitted,
)
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
    get_active_or_paused_session,
    get_active_session,
    pause_session,
    resume_session,
    update_session_step,
)

CHECKLIST_LABELS: dict[str, str] = {
    "KITCHEN_OPEN": "Kitchen Opening",
    "KITCHEN_CLOSE": "Kitchen Closing",
    "DINING_OPEN": "Dining Opening",
    "DINING_CLOSE": "Dining Closing",
}

OPENING_CHECKLISTS = {"KITCHEN_OPEN", "DINING_OPEN"}
CLOSING_CHECKLISTS = {"KITCHEN_CLOSE", "DINING_CLOSE"}


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


async def _has_completed_today(
    db: AsyncSession, restaurant_id: str, checklist_id: str
) -> bool:
    """Return True if this checklist has already been completed today (PHT day).

    Uses the same PHT-aligned boundary as get_today_staff_status:
    midnight PHT = 16:00 UTC the previous calendar day.
    Block is per-restaurant per-checklist — once any staff member completes
    it, no one else can start it again until the next PHT day.
    """
    today_start_pht = (
        datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        - timedelta(hours=8)
    )
    result = await db.execute(
        select(ChecklistRun).where(
            ChecklistRun.restaurant_id == restaurant_id,
            ChecklistRun.checklist_id == checklist_id,
            ChecklistRun.status == "completed",
            ChecklistRun.end_time >= today_start_pht,
        )
    )
    return result.scalars().first() is not None


def _branch_label(restaurant) -> str:
    if restaurant and restaurant.branch:
        return f"{restaurant.name} – {restaurant.branch}"
    return restaurant.name if restaurant else ""


def _format_step_message(step: ChecklistStep, total_steps: int) -> str:
    photo_hint = "\n📷 <i>This step requires a photo.</i>" if step.requires_photo else ""
    return f"<b>Step {step.step_number} of {total_steps}</b>\n{step.instruction}{photo_hint}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def start_checklist(db: AsyncSession, chat_id: str, text: str) -> dict:
    checklist_id = parse_command(text)
    if checklist_id is None:
        return _empty_result()

    staff = await _get_staff(db, chat_id)
    if staff is None:
        return _reply("You are not registered in the system. Please contact your manager.")

    # Block if already active OR paused
    existing = await get_active_or_paused_session(db, chat_id)
    if existing:
        label = CHECKLIST_LABELS.get(existing.checklist_id, existing.checklist_id)
        if existing.status == "paused":
            return _reply(
                f"Your <b>{label}</b> checklist is paused due to a critical issue.\n"
                "Your manager needs to resolve it before you can continue."
            )
        return _reply(
            f"You already have an active checklist: <b>{label}</b>.\n"
            "Tap <b>✅ Done</b> to continue, or use /cancel to stop it."
        )

    # Block if this checklist has already been completed today for this restaurant
    if await _has_completed_today(db, staff.restaurant_id, checklist_id):
        label = CHECKLIST_LABELS.get(checklist_id, checklist_id)
        return _reply(
            f"✅ <b>{label}</b> has already been completed today.\n"
            "It can only be done once per day per restaurant."
        )

    total_steps = await _count_steps(db, staff.restaurant_id, checklist_id)
    if total_steps == 0:
        return _reply("No steps configured for this checklist. Please contact your manager.")

    session = await create_session(db, chat_id, staff.restaurant_id, checklist_id)
    step = await _get_step(db, staff.restaurant_id, checklist_id, 1)
    restaurant = await _get_restaurant(db, staff.restaurant_id)

    label = CHECKLIST_LABELS.get(checklist_id, checklist_id)
    now = to_pht(datetime.utcnow()).strftime("%I:%M %p")
    branch = _branch_label(restaurant)

    # Metrics
    checklist_started.labels(
        restaurant_id=staff.restaurant_id,
        checklist_id=checklist_id,
    ).inc()
    active_sessions.labels(restaurant_id=staff.restaurant_id).inc()

    return {
        "reply": f"Starting <b>{label}</b> checklist.\n\n{_format_step_message(step, total_steps)}",
        "use_buttons": True,
        "manager_msg": f"🟢 <b>{staff.name}</b> started <b>{label}</b> at {now}\n📍 {branch}",
        "manager_chat_id": restaurant.manager_chat_id if restaurant else None,
        "session": session,
        "photo_to_manager": None,
        "completed": False,
        "delete_message_id": None,
    }


async def progress_step(
    db: AsyncSession, chat_id: str, is_photo: bool = False, file_id: str | None = None
) -> dict:
    session = await get_active_session(db, chat_id)
    if session is None:
        paused = await get_active_or_paused_session(db, chat_id)
        if paused and paused.status == "paused":
            label = CHECKLIST_LABELS.get(paused.checklist_id, paused.checklist_id)
            return _reply(
                f"Your <b>{label}</b> checklist is paused due to a critical issue.\n"
                "Your manager needs to resolve it before you can continue."
            )
        return _reply("No active checklist. Tap a button below to start one.")

    current_step = await _get_step(
        db, session.restaurant_id, session.checklist_id, session.current_step
    )
    if current_step is None:
        return _reply("Step data is missing. Please contact your manager.")

    total_steps = await _count_steps(db, session.restaurant_id, session.checklist_id)

    if current_step.requires_photo and not is_photo:
        return {
            **_reply("📷 This step requires a photo. Please send a photo to continue."),
            "delete_message_id": None,
            "photo_to_manager": None,
            "completed": False,
        }

    delete_message_id = session.last_message_id
    manager_photo_msg = None
    photo_file_id_for_manager = None

    if is_photo and file_id:
        db.add(StepPhoto(session_id=session.id, step_number=session.current_step, file_id=file_id))
        await db.commit()
        staff = await _get_staff(db, chat_id)
        label = CHECKLIST_LABELS.get(session.checklist_id, session.checklist_id)
        manager_photo_msg = (
            f"📸 <b>{staff.name}</b> – {label} Step {session.current_step}" if staff else None
        )
        photo_file_id_for_manager = file_id

        # Metrics
        photos_submitted.labels(restaurant_id=session.restaurant_id).inc()

    next_step_num = session.current_step + 1
    if next_step_num > total_steps:
        return await _complete_checklist(
            db, session, total_steps, delete_message_id,
            manager_photo_msg, photo_file_id_for_manager
        )

    await update_session_step(db, session, next_step_num)
    next_step = await _get_step(db, session.restaurant_id, session.checklist_id, next_step_num)

    manager_chat_id = None
    if photo_file_id_for_manager:
        restaurant = await _get_restaurant(db, session.restaurant_id)
        manager_chat_id = restaurant.manager_chat_id if restaurant else None

    return {
        "reply": _format_step_message(next_step, total_steps),
        "use_buttons": True,
        "manager_msg": manager_photo_msg,
        "manager_chat_id": manager_chat_id,
        "completed": False,
        "delete_message_id": delete_message_id,
        "photo_to_manager": {
            "file_id": photo_file_id_for_manager,
            "caption": manager_photo_msg,
        } if photo_file_id_for_manager else None,
        "session": session,
    }


async def _complete_checklist(
    db, session, total_steps, delete_message_id, manager_photo_msg, photo_file_id_for_manager
) -> dict:
    await complete_session(db, session)

    photo_count = await _count_photos(db, session.id)
    end_time = datetime.utcnow()
    db.add(ChecklistRun(
        chat_id=session.chat_id,
        restaurant_id=session.restaurant_id,
        checklist_id=session.checklist_id,
        start_time=session.started_at,
        end_time=end_time,
        status="completed",
        photo_count=photo_count,
    ))
    await db.commit()

    duration_seconds = (end_time - session.started_at).total_seconds()
    minutes = int(duration_seconds // 60)
    label = CHECKLIST_LABELS.get(session.checklist_id, session.checklist_id)

    staff = await _get_staff(db, session.chat_id)
    restaurant = await _get_restaurant(db, session.restaurant_id)
    branch = _branch_label(restaurant)
    start_str = to_pht(session.started_at).strftime("%I:%M %p")
    end_str = to_pht(end_time).strftime("%I:%M %p")

    # Metrics
    checklist_completed.labels(
        restaurant_id=session.restaurant_id,
        checklist_id=session.checklist_id,
    ).inc()
    checklist_duration.labels(
        restaurant_id=session.restaurant_id,
        checklist_id=session.checklist_id,
    ).observe(duration_seconds)
    active_sessions.labels(restaurant_id=session.restaurant_id).dec()

    manager_msg = (
        f"✅ <b>{staff.name}</b> completed <b>{label}</b>\n"
        f"📍 {branch}\n"
        f"Start: {start_str} | Finish: {end_str} | Photos: {photo_count}"
        if staff else None
    )

    return {
        "reply": f"✅ <b>{label}</b> complete! Finished in {minutes} minutes.",
        "use_buttons": False,
        "manager_msg": manager_msg,
        "manager_chat_id": restaurant.manager_chat_id if restaurant else None,
        "completed": True,
        "delete_message_id": delete_message_id,
        "photo_to_manager": {
            "file_id": photo_file_id_for_manager,
            "caption": manager_photo_msg,
        } if photo_file_id_for_manager else None,
        "session": session,
    }


async def handle_abandon(db: AsyncSession, chat_id: str) -> dict:
    session = await get_active_or_paused_session(db, chat_id)
    if session is None:
        return {**_reply("No active checklist to cancel."), "delete_message_id": None}

    delete_message_id = session.last_message_id
    await abandon_session(db, session)

    photo_count = await _count_photos(db, session.id)
    db.add(ChecklistRun(
        chat_id=session.chat_id,
        restaurant_id=session.restaurant_id,
        checklist_id=session.checklist_id,
        start_time=session.started_at,
        end_time=datetime.utcnow(),
        status="abandoned",
        photo_count=photo_count,
    ))
    await db.commit()

    staff = await _get_staff(db, chat_id)
    label = CHECKLIST_LABELS.get(session.checklist_id, session.checklist_id)
    restaurant = await _get_restaurant(db, session.restaurant_id)

    # Metrics
    checklist_abandoned.labels(
        restaurant_id=session.restaurant_id,
        checklist_id=session.checklist_id,
    ).inc()
    active_sessions.labels(restaurant_id=session.restaurant_id).dec()

    return {
        "reply": f"❌ <b>{label}</b> checklist cancelled.",
        "use_buttons": False,
        "manager_msg": (
            f"❌ <b>{staff.name}</b> cancelled <b>{label}</b> at step {session.current_step}"
            if staff else None
        ),
        "manager_chat_id": restaurant.manager_chat_id if restaurant else None,
        "delete_message_id": delete_message_id,
        "completed": False,
        "photo_to_manager": None,
        "session": None,
    }


async def handle_issue_report(
    db: AsyncSession, chat_id: str, description: str, issue_type: str = "operational"
) -> dict:
    session = await get_active_session(db, chat_id)
    if session is None:
        return {**_reply("No active checklist. Start a checklist first."), "delete_message_id": None, "photo_to_manager": None}

    staff = await _get_staff(db, chat_id)
    label = CHECKLIST_LABELS.get(session.checklist_id, session.checklist_id)
    staff_name = staff.name if staff else chat_id

    issue = IssueReport(
        session_id=session.id,
        chat_id=chat_id,
        restaurant_id=session.restaurant_id,
        checklist_id=session.checklist_id,
        step_number=session.current_step,
        issue_type=issue_type,
        description=description,
    )
    db.add(issue)
    await db.commit()
    await db.refresh(issue)

    restaurant = await _get_restaurant(db, session.restaurant_id)
    branch = _branch_label(restaurant)
    manager_chat_id = restaurant.manager_chat_id if restaurant else None

    # Metrics
    issues_reported.labels(
        restaurant_id=session.restaurant_id,
        issue_type=issue_type,
    ).inc()

    if issue_type == "critical":
        await pause_session(db, session)
        active_sessions.labels(restaurant_id=session.restaurant_id).dec()

        manager_msg = (
            f"🔴 <b>CRITICAL Issue #{issue.id}</b>\n"
            f"Staff: {staff_name}\n"
            f"📍 {branch}\n"
            f"Checklist: {label} – Step {session.current_step}\n\n"
            f"📝 {description}\n\n"
            f"<b>Checklist is PAUSED.</b> Tap 'Resume' in Open Issues to unblock staff."
        )
        return {
            "reply": (
                "🔴 <b>Critical issue reported.</b>\n"
                "Your checklist has been <b>paused</b>.\n"
                "Your manager has been notified and must resume it before you can continue."
            ),
            "use_buttons": False,
            "manager_msg": manager_msg,
            "manager_chat_id": manager_chat_id,
            "delete_message_id": session.last_message_id,
            "photo_to_manager": None,
            "completed": False,
            "session": session,
            "issue_id": issue.id,
        }

    total_steps = await _count_steps(db, session.restaurant_id, session.checklist_id)
    next_step_num = session.current_step + 1

    manager_msg = (
        f"🟡 <b>Operational Issue #{issue.id}</b>\n"
        f"Staff: {staff_name}\n"
        f"📍 {branch}\n"
        f"Checklist: {label} – Step {session.current_step}\n\n"
        f"📝 {description}"
    )

    if next_step_num > total_steps:
        return await _complete_checklist(db, session, total_steps, session.last_message_id, None, None)

    await update_session_step(db, session, next_step_num)
    next_step = await _get_step(db, session.restaurant_id, session.checklist_id, next_step_num)

    return {
        "reply": (
            f"🟡 Operational issue logged. Moving to next step.\n\n"
            f"{_format_step_message(next_step, total_steps)}"
        ),
        "use_buttons": True,
        "manager_msg": manager_msg,
        "manager_chat_id": manager_chat_id,
        "delete_message_id": session.last_message_id,
        "photo_to_manager": None,
        "completed": False,
        "session": session,
        "issue_id": issue.id,
    }


async def resume_checklist_for_staff(db: AsyncSession, chat_id: str) -> dict:
    from app.services.session_service import get_paused_session
    session = await get_paused_session(db, chat_id)
    if session is None:
        return _reply("No paused checklist found for this staff member.")

    await resume_session(db, session)

    # Metrics — session is active again
    active_sessions.labels(restaurant_id=session.restaurant_id).inc()

    total_steps = await _count_steps(db, session.restaurant_id, session.checklist_id)
    current_step = await _get_step(db, session.restaurant_id, session.checklist_id, session.current_step)

    label = CHECKLIST_LABELS.get(session.checklist_id, session.checklist_id)
    step_msg = _format_step_message(current_step, total_steps) if current_step else ""

    return {
        "staff_chat_id": session.chat_id,
        "reply": (
            f"▶️ <b>Checklist Resumed</b>\n"
            f"Your manager has resolved the issue. Continue with <b>{label}</b>.\n\n"
            f"{step_msg}"
        ),
        "use_buttons": True,
        "session": session,
    }


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _empty_result() -> dict:
    return {
        "reply": None, "use_buttons": False, "manager_msg": None,
        "manager_chat_id": None, "session": None, "photo_to_manager": None,
        "completed": False, "delete_message_id": None,
    }


def _reply(text: str) -> dict:
    return {
        "reply": text, "use_buttons": False, "manager_msg": None,
        "manager_chat_id": None, "session": None, "photo_to_manager": None,
        "completed": False, "delete_message_id": None,
    }