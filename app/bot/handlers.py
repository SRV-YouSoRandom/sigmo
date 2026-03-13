"""Telegram webhook update handler."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.commands import parse_command
from app.bot.notifier import (
    CHECKLIST_KEYBOARD,
    answer_callback_query,
    notify_manager,
    send_step_message,
    send_telegram_message,
)
from app.core.database import get_async_session
from app.metrics.prometheus import checklist_started, webhook_latency
from app.services.checklist_engine import (
    handle_abandon,
    handle_issue_report,
    progress_step,
    start_checklist,
)

logger = logging.getLogger(__name__)

# Tracks staff mid-issue-report flow waiting to type their description
_awaiting_issue_description: dict[str, bool] = {}

# Maps reply keyboard button text to checklist commands
KEYBOARD_COMMAND_MAP = {
    "🍳 Kitchen Opening": "kitchen opening",
    "🔒 Kitchen Closing": "kitchen closing",
    "🍽️ Dining Opening": "dining opening",
    "🔒 Dining Closing": "dining closing",
}

WELCOME_MESSAGE = (
    "👋 <b>Welcome to Sigmo</b>\n\n"
    "I'll guide you through your operational checklists step by step.\n\n"
    "Tap a checklist below to get started, or type <b>/help</b> for more info."
)

HELP_MESSAGE = (
    "📋 <b>Sigmo Checklist Bot</b>\n\n"
    "<b>Available checklists:</b>\n"
    "🍳 /kitchen_opening – Kitchen Opening\n"
    "🔒 /kitchen_closing – Kitchen Closing\n"
    "🍽️ /dining_opening – Dining Opening\n"
    "🔒 /dining_closing – Dining Closing\n\n"
    "<b>During a checklist:</b>\n"
    "• Tap <b>✅ Done</b> to complete a step\n"
    "• Tap <b>⚠️ Report Issue</b> to flag a problem\n"
    "• Send a 📷 photo when a step requires it\n"
    "• Use /cancel to stop the current checklist\n\n"
    "<b>Need help?</b> Contact your manager."
)


async def process_update(data: dict) -> None:
    """Process a single Telegram update."""
    with webhook_latency.time():
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

        # Normalize keyboard button taps to their command equivalents
        if text in KEYBOARD_COMMAND_MAP:
            text = KEYBOARD_COMMAND_MAP[text]

        factory = get_async_session()
        async with factory() as db:
            if _awaiting_issue_description.get(chat_id):
                _awaiting_issue_description.pop(chat_id)
                await _handle_issue_description(db, chat_id, text)
            elif photo_list:
                await _handle_photo(db, chat_id, photo_list)
            elif text.lower() in ("/cancel", "cancel"):
                await _handle_abandon(db, chat_id)
            elif text.lower() in ("/start", "/help"):
                await _handle_system_command(chat_id, text.lower())
            elif text.lower() == "done":
                await _handle_done(db, chat_id)
            elif parse_command(text):
                await _handle_command(db, chat_id, text)
            else:
                await send_telegram_message(
                    chat_id,
                    "Tap a checklist button below or type /help for available commands.",
                    reply_markup=CHECKLIST_KEYBOARD,
                )


async def _handle_system_command(chat_id: str, command: str) -> None:
    """Handle /start and /help."""
    if command == "/start":
        await send_telegram_message(chat_id, WELCOME_MESSAGE, reply_markup=CHECKLIST_KEYBOARD)
    elif command == "/help":
        await send_telegram_message(chat_id, HELP_MESSAGE, reply_markup=CHECKLIST_KEYBOARD)


async def _handle_callback_query(callback_query: dict) -> None:
    """Handle inline button taps."""
    callback_id = callback_query["id"]
    chat_id = str(callback_query["from"]["id"])
    data = callback_query.get("data", "")

    factory = get_async_session()
    async with factory() as db:
        if data == "done":
            await answer_callback_query(callback_id, "✅ Marked as done")
            await _handle_done(db, chat_id)
        elif data == "report_issue":
            await answer_callback_query(callback_id, "⚠️ Describe the issue")
            _awaiting_issue_description[chat_id] = True
            await send_telegram_message(
                chat_id,
                "⚠️ <b>Report Issue</b>\n\nPlease describe the issue and send it as a message.",
            )


async def _handle_command(db: AsyncSession, chat_id: str, text: str) -> None:
    result = await start_checklist(db, chat_id, text)
    if result["reply"]:
        if result.get("use_buttons"):
            await send_step_message(chat_id, result["reply"])
        else:
            await send_telegram_message(chat_id, result["reply"], reply_markup=CHECKLIST_KEYBOARD)
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
            # Checklist complete, show keyboard again
            await send_telegram_message(chat_id, result["reply"], reply_markup=CHECKLIST_KEYBOARD)
    if result["manager_msg"]:
        await notify_manager(result["manager_chat_id"], result["manager_msg"])


async def _handle_photo(db: AsyncSession, chat_id: str, photo_list: list) -> None:
    file_id = photo_list[-1]["file_id"]
    result = await progress_step(db, chat_id, is_photo=True, file_id=file_id)
    if result["reply"]:
        if result.get("use_buttons"):
            await send_step_message(chat_id, result["reply"])
        else:
            await send_telegram_message(chat_id, result["reply"], reply_markup=CHECKLIST_KEYBOARD)
    if result["manager_msg"]:
        await notify_manager(result["manager_chat_id"], result["manager_msg"])


async def _handle_abandon(db: AsyncSession, chat_id: str) -> None:
    result = await handle_abandon(db, chat_id)
    if result["reply"]:
        await send_telegram_message(chat_id, result["reply"], reply_markup=CHECKLIST_KEYBOARD)


async def _handle_issue_description(db: AsyncSession, chat_id: str, description: str) -> None:
    if not description:
        await send_telegram_message(chat_id, "⚠️ Issue description cannot be empty. Please describe the issue.")
        _awaiting_issue_description[chat_id] = True
        return

    result = await handle_issue_report(db, chat_id, description)
    if result["reply"]:
        if result.get("use_buttons"):
            await send_step_message(chat_id, result["reply"])
        else:
            await send_telegram_message(chat_id, result["reply"], reply_markup=CHECKLIST_KEYBOARD)
    if result["manager_msg"]:
        await notify_manager(result["manager_chat_id"], result["manager_msg"])