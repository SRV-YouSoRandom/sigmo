"""APScheduler daily summary cron job."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.bot.notifier import send_telegram_message
from app.core.database import get_async_session
from app.models.restaurant import Restaurant
from app.services.report_service import build_summary_message, get_runs_for_yesterday

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


@scheduler.scheduled_job("cron", hour=8, minute=0, id="daily_summary")
async def send_daily_summary() -> None:
    """Send daily summary to all restaurant managers at 08:00."""
    logger.info("Running daily summary job")
    factory = get_async_session()
    async with factory() as db:
        result = await db.execute(select(Restaurant))
        restaurants = result.scalars().all()

        for restaurant in restaurants:
            runs = await get_runs_for_yesterday(db, restaurant.restaurant_id)
            if runs:
                message = build_summary_message(runs)
                await send_telegram_message(restaurant.manager_chat_id, message)
                logger.info(
                    "Sent daily summary to restaurant %s", restaurant.restaurant_id
                )
            else:
                logger.debug(
                    "No runs yesterday for restaurant %s", restaurant.restaurant_id
                )
