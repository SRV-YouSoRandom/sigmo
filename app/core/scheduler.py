"""APScheduler jobs: daily summary, opening/closing reminders, not-started follow-up.

Job store: SQLAlchemyJobStore backed by Postgres.
All jobs are persisted in the `apscheduler_jobs` table. This means:
- Jobs survive container restarts automatically.
- Any call to _add_or_replace_job() writes directly to the DB, so manage.sh
  changes are picked up on the next scheduler cycle without a restart.
"""

import logging
from datetime import datetime, timedelta

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.bot.notifier import send_telegram_message
from app.core.config import get_settings
from app.core.database import get_async_session
from app.models.restaurant import Restaurant
from app.models.session import Session
from app.models.staff import Staff
from app.services.checklist_engine import CLOSING_CHECKLISTS, OPENING_CHECKLISTS
from app.services.report_service import build_summary_message, get_runs_for_yesterday

logger = logging.getLogger(__name__)


def _build_scheduler() -> AsyncIOScheduler:
    settings = get_settings()
    jobstore = SQLAlchemyJobStore(url=settings.scheduler_database_url)
    return AsyncIOScheduler(
        jobstores={"default": jobstore},
        job_defaults={
            # If a job was missed (e.g. server was down), don't fire it late
            "misfire_grace_time": 60,
            # Only ever run one instance of each job at a time
            "coalesce": True,
            "max_instances": 1,
        },
    )


scheduler = _build_scheduler()


# ---------------------------------------------------------------------------
# Daily summary – fixed at 08:00 UTC
# ---------------------------------------------------------------------------

async def _send_daily_summary() -> None:
    logger.info("Running daily summary job")
    factory = get_async_session()
    async with factory() as db:
        result = await db.execute(select(Restaurant))
        restaurants = result.scalars().all()
        for restaurant in restaurants:
            runs = await get_runs_for_yesterday(db, restaurant.restaurant_id)
            msg = build_summary_message(runs, restaurant=restaurant)
            await send_telegram_message(restaurant.manager_chat_id, msg)
            logger.info("Sent daily summary to restaurant %s", restaurant.restaurant_id)


# ---------------------------------------------------------------------------
# Dynamic reminder jobs – loaded/refreshed at startup from DB
# ---------------------------------------------------------------------------

async def schedule_restaurant_reminders() -> None:
    """
    Read all restaurants from DB and register/update all jobs in the persistent
    job store. Safe to call again at any time — existing jobs are replaced.
    Also registers the daily summary job if it doesn't exist yet.
    """
    # Daily summary — register once, persists across restarts
    _add_or_replace_job(
        "daily_summary",
        _send_daily_summary,
        hour=8,
        minute=0,
        kwargs={},
    )

    factory = get_async_session()
    async with factory() as db:
        result = await db.execute(select(Restaurant))
        restaurants = result.scalars().all()

    for r in restaurants:
        _register_reminders_for_restaurant(r)

    logger.info("Registered/refreshed jobs for %d restaurant(s)", len(restaurants))


def _register_reminders_for_restaurant(restaurant: Restaurant) -> None:
    """Register or update opening and closing reminder + follow-up jobs for one restaurant."""
    rid = restaurant.restaurant_id

    if restaurant.opening_reminder_time:
        h, m = _parse_time(restaurant.opening_reminder_time)
        _add_or_replace_job(
            f"opening_reminder_{rid}",
            _send_opening_reminder,
            h, m,
            kwargs={"restaurant_id": rid},
        )
        fh, fm = _add_minutes(h, m, restaurant.reminder_followup_minutes)
        _add_or_replace_job(
            f"opening_followup_{rid}",
            _send_opening_followup,
            fh, fm,
            kwargs={"restaurant_id": rid},
        )
    else:
        # Remove jobs if reminder time was cleared
        _remove_job_if_exists(f"opening_reminder_{rid}")
        _remove_job_if_exists(f"opening_followup_{rid}")

    if restaurant.closing_reminder_time:
        h, m = _parse_time(restaurant.closing_reminder_time)
        _add_or_replace_job(
            f"closing_reminder_{rid}",
            _send_closing_reminder,
            h, m,
            kwargs={"restaurant_id": rid},
        )
        fh, fm = _add_minutes(h, m, restaurant.reminder_followup_minutes)
        _add_or_replace_job(
            f"closing_followup_{rid}",
            _send_closing_followup,
            fh, fm,
            kwargs={"restaurant_id": rid},
        )
    else:
        # Remove jobs if reminder time was cleared
        _remove_job_if_exists(f"closing_reminder_{rid}")
        _remove_job_if_exists(f"closing_followup_{rid}")


def _add_or_replace_job(job_id: str, func, hour: int, minute: int, kwargs: dict) -> None:
    """Add or replace a cron job in the persistent job store."""
    scheduler.add_job(
        func,
        "cron",
        hour=hour,
        minute=minute,
        id=job_id,
        kwargs=kwargs,
        replace_existing=True,
    )
    logger.debug("Scheduled job %s at %02d:%02d UTC", job_id, hour, minute)


def _remove_job_if_exists(job_id: str) -> None:
    """Remove a job from the store if it exists, silently ignore if not."""
    try:
        scheduler.remove_job(job_id)
        logger.debug("Removed job %s", job_id)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Reminder job functions
# ---------------------------------------------------------------------------

async def _send_opening_reminder(restaurant_id: str) -> None:
    logger.info("Sending opening reminder for restaurant %s", restaurant_id)
    factory = get_async_session()
    async with factory() as db:
        restaurant, staff_list = await _get_restaurant_and_staff(db, restaurant_id)
        if not restaurant:
            return
        branch = f" – {restaurant.branch}" if restaurant.branch else ""
        msg = (
            f"☀️ <b>Good morning{branch}!</b>\n\n"
            "Time to start operations. Please begin your opening checklist.\n\n"
            "Tap <b>🍳 Kitchen Opening</b> or <b>🍽️ Dining Opening</b> to get started."
        )
        for staff in staff_list:
            await send_telegram_message(staff.chat_id, msg)


async def _send_closing_reminder(restaurant_id: str) -> None:
    logger.info("Sending closing reminder for restaurant %s", restaurant_id)
    factory = get_async_session()
    async with factory() as db:
        restaurant, staff_list = await _get_restaurant_and_staff(db, restaurant_id)
        if not restaurant:
            return
        branch = f" – {restaurant.branch}" if restaurant.branch else ""
        msg = (
            f"🌙 <b>Closing time{branch}!</b>\n\n"
            "Please begin your closing checklist.\n\n"
            "Tap <b>🔒 Kitchen Closing</b> or <b>🔒 Dining Closing</b> to get started."
        )
        for staff in staff_list:
            await send_telegram_message(staff.chat_id, msg)


async def _send_opening_followup(restaurant_id: str) -> None:
    """Send follow-up if no opening checklist has been started yet."""
    factory = get_async_session()
    async with factory() as db:
        restaurant, staff_list = await _get_restaurant_and_staff(db, restaurant_id)
        if not restaurant:
            return
        started = await _any_checklist_started_today(db, restaurant_id, OPENING_CHECKLISTS)
        if started:
            logger.debug("Opening already started for %s, skipping follow-up", restaurant_id)
            return
        logger.info("Sending opening follow-up for restaurant %s", restaurant_id)
        msg = (
            "⏰ <b>Reminder:</b> The opening checklist has not been started yet.\n\n"
            "Please begin now."
        )
        for staff in staff_list:
            await send_telegram_message(staff.chat_id, msg)
        await send_telegram_message(
            restaurant.manager_chat_id,
            f"⚠️ Opening checklist not yet started at <b>{restaurant.name}"
            f"{' – ' + restaurant.branch if restaurant.branch else ''}</b>.",
        )


async def _send_closing_followup(restaurant_id: str) -> None:
    """Send follow-up if no closing checklist has been started yet."""
    factory = get_async_session()
    async with factory() as db:
        restaurant, staff_list = await _get_restaurant_and_staff(db, restaurant_id)
        if not restaurant:
            return
        started = await _any_checklist_started_today(db, restaurant_id, CLOSING_CHECKLISTS)
        if started:
            logger.debug("Closing already started for %s, skipping follow-up", restaurant_id)
            return
        logger.info("Sending closing follow-up for restaurant %s", restaurant_id)
        msg = (
            "⏰ <b>Reminder:</b> The closing checklist has not been started yet.\n\n"
            "Please begin now."
        )
        for staff in staff_list:
            await send_telegram_message(staff.chat_id, msg)
        await send_telegram_message(
            restaurant.manager_chat_id,
            f"⚠️ Closing checklist not yet started at <b>{restaurant.name}"
            f"{' – ' + restaurant.branch if restaurant.branch else ''}</b>.",
        )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

async def _get_restaurant_and_staff(db, restaurant_id: str):
    from app.models.restaurant import Restaurant as R
    res = await db.execute(select(R).where(R.restaurant_id == restaurant_id))
    restaurant = res.scalars().first()
    if not restaurant:
        return None, []
    staff_res = await db.execute(select(Staff).where(Staff.restaurant_id == restaurant_id))
    staff_list = staff_res.scalars().all()
    return restaurant, staff_list


async def _any_checklist_started_today(db, restaurant_id: str, checklist_types: set) -> bool:
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(Session).where(
            Session.restaurant_id == restaurant_id,
            Session.checklist_id.in_(checklist_types),
            Session.started_at >= today_start,
        )
    )
    return result.scalars().first() is not None


def _parse_time(time_str: str) -> tuple[int, int]:
    h, m = time_str.strip().split(":")
    return int(h), int(m)


def _add_minutes(hour: int, minute: int, delta: int) -> tuple[int, int]:
    total = hour * 60 + minute + delta
    return (total // 60) % 24, total % 60