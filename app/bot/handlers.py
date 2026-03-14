"""Telegram webhook update handler."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.commands import parse_command
from app.bot.notifier import (
    CHECKLIST_KEYBOARD,
    MANAGER_KEYBOARD,
    answer_callback_query,
    delete_message,
    edit_message_reply_markup,
    notify_manager,
    send_photo_to_manager,
    send_step_message,
    send_telegram_message,
)
from app.core.database import get_async_session
from app.metrics.prometheus import checklist_started, webhook_latency
from app.services.checklist_engine import (
    handle_abandon,
    handle_issue_report,
    progress_step,
    resume_checklist_for_staff,
    start_checklist,
)
from app.services.manager_service import (
    build_issues_messages,
    get_manager_by_chat_id,
    get_open_issues,
    get_today_staff_status,
    resolve_issue,
)
from app.services.session_service import save_last_message_id, get_active_session

logger = logging.getLogger(__name__)

# chat_id → waiting for description text after type was chosen
_awaiting_issue_description: dict[str, str] = {}  # value = issue_type

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

MANAGER_WELCOME_MESSAGE = (
    "👋 <b>Welcome to Sigmo – Manager View</b>\n\n"
    "Use the buttons below to check on your team."
)

HELP_MESSAGE = (
    "📋 <b>Sigmo Checklist Bot</b>\n\n"
    "<b>Available checklists:</b>\n"
    "🍳 Kitchen Opening\n"
    "🔒 Kitchen Closing\n"
    "🍽️ Dining Opening\n"
    "🔒 Dining Closing\n\n"
    "<b>During a checklist:</b>\n"
    "• Tap <b>✅ Done</b> to complete a step\n"
    "• Tap <b>⚠️ Report Issue</b> to flag a problem\n"
    "• Send a 📷 photo when a step requires it\n"
    "• Use /cancel to stop the current checklist\n\n"
    "<b>Need help?</b> Contact your manager."
)

MANAGER_HELP_MESSAGE = (
    "📋 <b>Sigmo – Manager Commands</b>\n\n"
    "• <b>👥 Staff Status</b> – see who is active, paused, or done today\n"
    "• <b>⚠️ Open Issues</b> – view and resolve reported issues\n\n"
    "Critical issues will pause a staff member's checklist until you resolve them here."
)


async def process_update(data: dict) -> None:
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

        factory = get_async_session()
        async with factory() as db:
            # Check manager BEFORE normalizing keyboard buttons
            # so a manager who accidentally taps a checklist button
            # still gets the manager response, not a checklist flow.
            manager = await get_manager_by_chat_id(db, chat_id)
            if manager:
                await _handle_manager_message(db, chat_id, text, manager)
                return

            # Only normalize keyboard buttons for staff
            if text in KEYBOARD_COMMAND_MAP:
                text = KEYBOARD_COMMAND_MAP[text]

            # Staff: waiting for issue description
            if chat_id in _awaiting_issue_description:
                issue_type = _awaiting_issue_description.pop(chat_id)
                await _handle_issue_description(db, chat_id, text, issue_type)
                return

            if photo_list:
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


# ---------------------------------------------------------------------------
# Manager handlers
# ---------------------------------------------------------------------------

async def _handle_manager_message(db: AsyncSession, chat_id: str, text: str, manager) -> None:
    if text.lower() in ("/start",):
        await send_telegram_message(chat_id, MANAGER_WELCOME_MESSAGE, reply_markup=MANAGER_KEYBOARD)
        return

    if text.lower() in ("/help",):
        await send_telegram_message(chat_id, MANAGER_HELP_MESSAGE, reply_markup=MANAGER_KEYBOARD)
        return

    if text in ("👥 Staff Status", "/status"):
        msg = await get_today_staff_status(db, manager.restaurant_id)
        await send_telegram_message(chat_id, msg, reply_markup=MANAGER_KEYBOARD)
        return

    if text in ("⚠️ Open Issues", "/issues"):
        issues = await get_open_issues(db, manager.restaurant_id)
        if not issues:
            await send_telegram_message(chat_id, "✅ No open issues right now.", reply_markup=MANAGER_KEYBOARD)
            return
        msgs = await build_issues_messages(db, issues)
        for m in msgs:
            await send_telegram_message(chat_id, m["text"], reply_markup=m["reply_markup"])
        return

    # Catch-all — always show manager keyboard, never checklist keyboard
    await send_telegram_message(
        chat_id,
        "Use the buttons below to manage your team.",
        reply_markup=MANAGER_KEYBOARD,
    )


# ---------------------------------------------------------------------------
# Callback query handler (inline buttons)
# ---------------------------------------------------------------------------

async def _handle_callback_query(callback_query: dict) -> None:
    callback_id = callback_query["id"]
    chat_id = str(callback_query["from"]["id"])
    data = callback_query.get("data", "")
    message_id = callback_query.get("message", {}).get("message_id")

    factory = get_async_session()
    async with factory() as db:

        # ── Manager: resolve operational issue ─────────────────────────────
        if data.startswith("resolve_issue:"):
            issue_id = int(data.split(":")[1])
            issue = await resolve_issue(db, issue_id, chat_id)
            if issue:
                await answer_callback_query(callback_id, "✅ Issue resolved")
                await edit_message_reply_markup(chat_id, message_id, reply_markup={"inline_keyboard": []})
                await send_telegram_message(
                    chat_id,
                    f"✅ <b>Issue #{issue.id} resolved</b> at {issue.resolved_at.strftime('%I:%M %p')}",
                    reply_markup=MANAGER_KEYBOARD,
                )
            else:
                await answer_callback_query(callback_id, "Issue not found.")
            return

        # ── Manager: resolve critical issue + resume staff ─────────────────
        if data.startswith("resolve_resume:"):
            _, issue_id_str, staff_chat_id = data.split(":")
            issue_id = int(issue_id_str)
            issue = await resolve_issue(db, issue_id, chat_id)
            if issue:
                await answer_callback_query(callback_id, "✅ Resolved – resuming staff")
                await edit_message_reply_markup(chat_id, message_id, reply_markup={"inline_keyboard": []})
                await send_telegram_message(
                    chat_id,
                    f"✅ <b>Issue #{issue.id} resolved.</b> Staff checklist has been resumed.",
                    reply_markup=MANAGER_KEYBOARD,
                )
                resume_result = await resume_checklist_for_staff(db, staff_chat_id)
                if resume_result.get("reply"):
                    msg_id = await send_step_message(staff_chat_id, resume_result["reply"]) \
                        if resume_result.get("use_buttons") \
                        else await send_telegram_message(staff_chat_id, resume_result["reply"])
                    if msg_id and resume_result.get("session"):
                        await save_last_message_id(db, resume_result["session"], msg_id)
            else:
                await answer_callback_query(callback_id, "Issue not found.")
            return

        # ── Staff: issue type selection ────────────────────────────────────
        if data == "issue_type_critical":
            await answer_callback_query(callback_id, "🔴 Critical issue selected")
            await edit_message_reply_markup(chat_id, message_id, reply_markup={"inline_keyboard": []})
            _awaiting_issue_description[chat_id] = "critical"
            await send_telegram_message(
                chat_id,
                "🔴 <b>Critical Issue</b>\n\nDescribe the issue (e.g. gas leak, power outage, fire).\nYour checklist will be paused until your manager resolves it.",
            )
            return

        if data == "issue_type_operational":
            await answer_callback_query(callback_id, "🟡 Operational issue selected")
            await edit_message_reply_markup(chat_id, message_id, reply_markup={"inline_keyboard": []})
            _awaiting_issue_description[chat_id] = "operational"
            await send_telegram_message(
                chat_id,
                "🟡 <b>Operational Issue</b>\n\nDescribe the issue (e.g. broken equipment, missing item).\nThe checklist will continue after logging.",
            )
            return

        # ── Staff: done ────────────────────────────────────────────────────
        if data == "done":
            await answer_callback_query(callback_id, "✅ Marked as done")
            await _handle_done(db, chat_id, inline_message_id=message_id)
            return

        # ── Staff: report issue → show type selection ──────────────────────
        if data == "report_issue":
            await answer_callback_query(callback_id, "⚠️ Select issue type")
            await send_telegram_message(
                chat_id,
                "⚠️ <b>Report Issue</b>\n\nWhat type of issue is this?",
                reply_markup={
                    "inline_keyboard": [
                        [
                            {"text": "🔴 Critical", "callback_data": "issue_type_critical"},
                            {"text": "🟡 Operational", "callback_data": "issue_type_operational"},
                        ]
                    ]
                },
            )
            return


# ---------------------------------------------------------------------------
# Staff message handlers
# ---------------------------------------------------------------------------

async def _handle_system_command(chat_id: str, command: str) -> None:
    if command == "/start":
        await send_telegram_message(chat_id, WELCOME_MESSAGE, reply_markup=CHECKLIST_KEYBOARD)
    elif command == "/help":
        await send_telegram_message(chat_id, HELP_MESSAGE, reply_markup=CHECKLIST_KEYBOARD)


async def _handle_command(db: AsyncSession, chat_id: str, text: str) -> None:
    result = await start_checklist(db, chat_id, text)
    if result["reply"]:
        if result.get("use_buttons"):
            msg_id = await send_step_message(chat_id, result["reply"])
            if msg_id and result.get("session"):
                await save_last_message_id(db, result["session"], msg_id)
        else:
            await send_telegram_message(chat_id, result["reply"], reply_markup=CHECKLIST_KEYBOARD)
    if result["manager_msg"]:
        await notify_manager(result["manager_chat_id"], result["manager_msg"])
        if result["session"] and result["session"].status == "active":
            checklist_started.labels(
                restaurant_id=result["session"].restaurant_id,
                checklist_id=result["session"].checklist_id,
            ).inc()


async def _handle_done(
    db: AsyncSession, chat_id: str, inline_message_id: int | None = None
) -> None:
    result = await progress_step(db, chat_id, is_photo=False)

    del_id = result.get("delete_message_id") or inline_message_id
    if del_id:
        await delete_message(chat_id, del_id)

    if result["reply"]:
        if result.get("use_buttons"):
            msg_id = await send_step_message(chat_id, result["reply"])
            if msg_id:
                session = await get_active_session(db, chat_id)
                if session:
                    await save_last_message_id(db, session, msg_id)
        else:
            await send_telegram_message(chat_id, result["reply"], reply_markup=CHECKLIST_KEYBOARD)

    if result.get("photo_to_manager") and result.get("manager_chat_id"):
        p = result["photo_to_manager"]
        await send_photo_to_manager(result["manager_chat_id"], p["file_id"], p["caption"] or "")

    if result.get("manager_msg"):
        await notify_manager(result["manager_chat_id"], result["manager_msg"])


async def _handle_photo(db: AsyncSession, chat_id: str, photo_list: list) -> None:
    file_id = photo_list[-1]["file_id"]
    result = await progress_step(db, chat_id, is_photo=True, file_id=file_id)

    if result.get("delete_message_id"):
        await delete_message(chat_id, result["delete_message_id"])

    if result["reply"]:
        if result.get("use_buttons"):
            msg_id = await send_step_message(chat_id, result["reply"])
            if msg_id:
                session = await get_active_session(db, chat_id)
                if session:
                    await save_last_message_id(db, session, msg_id)
        else:
            await send_telegram_message(chat_id, result["reply"], reply_markup=CHECKLIST_KEYBOARD)

    if result.get("photo_to_manager") and result.get("manager_chat_id"):
        p = result["photo_to_manager"]
        await send_photo_to_manager(result["manager_chat_id"], p["file_id"], p["caption"] or "")
    elif result.get("manager_msg"):
        await notify_manager(result["manager_chat_id"], result["manager_msg"])


async def _handle_abandon(db: AsyncSession, chat_id: str) -> None:
    result = await handle_abandon(db, chat_id)

    if result.get("delete_message_id"):
        await delete_message(chat_id, result["delete_message_id"])

    if result["reply"]:
        await send_telegram_message(chat_id, result["reply"], reply_markup=CHECKLIST_KEYBOARD)

    if result.get("manager_msg"):
        await notify_manager(result.get("manager_chat_id"), result["manager_msg"])


async def _handle_issue_description(
    db: AsyncSession, chat_id: str, description: str, issue_type: str
) -> None:
    if not description.strip():
        await send_telegram_message(chat_id, "⚠️ Description cannot be empty. Please describe the issue.")
        _awaiting_issue_description[chat_id] = issue_type
        return

    result = await handle_issue_report(db, chat_id, description, issue_type)

    if result.get("delete_message_id"):
        await delete_message(chat_id, result["delete_message_id"])

    if result["reply"]:
        if result.get("use_buttons"):
            msg_id = await send_step_message(chat_id, result["reply"])
            if msg_id:
                session = await get_active_session(db, chat_id)
                if session:
                    await save_last_message_id(db, session, msg_id)
        else:
            await send_telegram_message(chat_id, result["reply"], reply_markup=CHECKLIST_KEYBOARD)

    if result.get("manager_msg"):
        await notify_manager(result["manager_chat_id"], result["manager_msg"])