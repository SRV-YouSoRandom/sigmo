"""Telegram webhook update handler – routes incoming messages to the checklist engine."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.commands import parse_command
from app.bot.notifier import (
    answer_callback_query,
    notify_manager,
    send_step_message,
    send_telegram_message,
)
from app.core.database import get_async_session
from app.metrics.prometheus import (
    checklist_started,
    webhook_latency,
)
from app.services.checklist_engine import (
    handle_abandon,
    handle_issue_report,
    progress_step,
    start_checklist,
)

logger = logging.getLogger(__name__)

# Tracks staff who are mid-issue-report flow, waiting to type their description
# Format: { chat_id: True }
_awaiting_issue_description: dict[str, bool] = {}


async def process_update(data: dict) -> None:
    """Process a single Telegram update."""
    with webhook_latency.time():
        # Handle inline button callbacks
        callback_query = data.get("callback_query")
        if callback_query:
            await _handle_callback_query(callback_query)
            return

        message = data.get("message")
        if not message:
            return

        chat_id = str(message["chat"]["id"])
        text = (message.get("text") or "").strip()
        photo_list = message.get("photo")

        factory = get_async_session()
        async with factory() as db:
            # Staff is in the middle of typing an issue description
            if _awaiting_issue_description.get(chat_id):
                _awaiting_issue_description.pop(chat_id)
                await _handle_issue_description(db, chat_id, text)
            elif photo_list:
                await _handle_photo(db, chat_id, photo_list)
            elif text.lower() == "abandon":
                await _handle_abandon(db, chat_id)
            elif text.lower() == "done":
                await _handle_done(db, chat_id)
            elif parse_command(text):
                await _handle_command(db, chat_id, text)
            else:
                pass


async def _handle_callback_query(callback_query: dict) -> None:
    """Handle inline button taps from staff."""
    callback_id = callback_query["id"]
    chat_id = str(callback_query["from"]["id"])
    data = callback_query.get("data", "")

    factory = get_async_session()
    async with factory() as db:
        if data == "done":
            await answer_callback_query(callback_id, "Marked as done")
            await _handle_done(db, chat_id)
        elif data == "report_issue":
            await answer_callback_query(callback_id, "Describe the issue")
            _awaiting_issue_description[chat_id] = True
            await send_telegram_message(
                chat_id,
                "Please describe the issue and send it as a message."
            )


async def _handle_command(db: AsyncSession, chat_id: str, text: str) -> None:
    result = await start_checklist(db, chat_id, text)
    if result["reply"]:
        if result.get("use_buttons"):
            await send_step_message(chat_id, result["reply"])
        else:
            await send_telegram_message(chat_id, result["reply"])
    if result["manager_msg"]:
        await notify_manager(result["manager_chat_id"], result["manager_msg"])
        if result["session"] and result["session"].status == "active":
            checklist_started.labels(
                restaurant_id=result["session"].restaurant_id,
                checklist_id=result["session"].checklist_id,
            ).inc()


async def _handle_done(db: AsyncSession, chat_id: str) -> None:
    result = await progress_step(db, chat_id, is_photo=False)
    if result["reply"]:
        if result.get("use_buttons"):
            await send_step_message(chat_id, result["reply"])
        else:
            await send_telegram_message(chat_id, result["reply"])
    if result["manager_msg"]:
        await notify_manager(result["manager_chat_id"], result["manager_msg"])


async def _handle_photo(db: AsyncSession, chat_id: str, photo_list: list) -> None:
    file_id = photo_list[-1]["file_id"]
    result = await progress_step(db, chat_id, is_photo=True, file_id=file_id)
    if result["reply"]:
        if result.get("use_buttons"):
            await send_step_message(chat_id, result["reply"])
        else:
            await send_telegram_message(chat_id, result["reply"])
    if result["manager_msg"]:
        await notify_manager(result["manager_chat_id"], result["manager_msg"])


async def _handle_abandon(db: AsyncSession, chat_id: str) -> None:
    result = await handle_abandon(db, chat_id)
    if result["reply"]:
        await send_telegram_message(chat_id, result["reply"])


async def _handle_issue_description(db: AsyncSession, chat_id: str, description: str) -> None:
    if not description:
        await send_telegram_message(chat_id, "Issue description cannot be empty. Please describe the issue.")
        _awaiting_issue_description[chat_id] = True
        return

    result = await handle_issue_report(db, chat_id, description)
    if result["reply"]:
        if result.get("use_buttons"):
            await send_step_message(chat_id, result["reply"])
        else:
            await send_telegram_message(chat_id, result["reply"])
    if result["manager_msg"]:
        await notify_manager(result["manager_chat_id"], result["manager_msg"])