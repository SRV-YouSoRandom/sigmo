"""Telegram webhook update handler – routes incoming messages to the checklist engine."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.commands import parse_command
from app.bot.notifier import notify_manager, send_telegram_message
from app.core.database import get_async_session
from app.metrics.prometheus import (
    checklist_abandoned,
    checklist_completed,
    checklist_started,
    webhook_latency,
)
from app.services.checklist_engine import handle_abandon, progress_step, start_checklist

logger = logging.getLogger(__name__)


async def process_update(data: dict) -> None:
    """Process a single Telegram update.

    Called as a background task from the webhook endpoint.
    """
    with webhook_latency.time():
        message = data.get("message")
        if not message:
            return

        chat_id = str(message["chat"]["id"])
        text = (message.get("text") or "").strip()
        photo_list = message.get("photo")

        factory = get_async_session()
        async with factory() as db:
            if photo_list:
                await _handle_photo(db, chat_id, photo_list)
            elif text.lower() == "abandon":
                await _handle_abandon(db, chat_id)
            elif text.lower() == "done":
                await _handle_done(db, chat_id)
            elif parse_command(text):
                await _handle_command(db, chat_id, text)
            else:
                # Unknown input – ignore or send help
                pass


async def _handle_command(db: AsyncSession, chat_id: str, text: str) -> None:
    """Handle a checklist start command."""
    result = await start_checklist(db, chat_id, text)
    if result["reply"]:
        await send_telegram_message(chat_id, result["reply"])
    if result["manager_msg"]:
        await notify_manager(result["manager_chat_id"], result["manager_msg"])
        if result["session"] and result["session"].status == "active":
            checklist_started.labels(
                restaurant_id=result["session"].restaurant_id,
                checklist_id=result["session"].checklist_id,
            ).inc()


async def _handle_done(db: AsyncSession, chat_id: str) -> None:
    """Handle a 'done' reply from staff."""
    result = await progress_step(db, chat_id, is_photo=False)
    if result["reply"]:
        await send_telegram_message(chat_id, result["reply"])
    if result["manager_msg"]:
        await notify_manager(result["manager_chat_id"], result["manager_msg"])


async def _handle_photo(db: AsyncSession, chat_id: str, photo_list: list) -> None:
    """Handle a photo message from staff."""
    # Telegram sends multiple sizes; use the largest (last in list)
    file_id = photo_list[-1]["file_id"]
    result = await progress_step(db, chat_id, is_photo=True, file_id=file_id)
    if result["reply"]:
        await send_telegram_message(chat_id, result["reply"])
    if result["manager_msg"]:
        await notify_manager(result["manager_chat_id"], result["manager_msg"])


async def _handle_abandon(db: AsyncSession, chat_id: str) -> None:
    """Handle an 'abandon' command from staff."""
    result = await handle_abandon(db, chat_id)
    if result["reply"]:
        await send_telegram_message(chat_id, result["reply"])
