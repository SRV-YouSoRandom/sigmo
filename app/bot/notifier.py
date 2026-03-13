"""Manager notification sender – sends Telegram messages via httpx."""

import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None

# Reply keyboard for staff – shown after /start and after checklist completion
CHECKLIST_KEYBOARD = {
    "keyboard": [
        [
            {"text": "🍳 Kitchen Opening"},
            {"text": "🔒 Kitchen Closing"},
        ],
        [
            {"text": "🍽️ Dining Opening"},
            {"text": "🔒 Dining Closing"},
        ],
    ],
    "resize_keyboard": True,
    "persistent": True,
    "input_field_placeholder": "Tap a checklist to begin...",
}

# Reply keyboard for managers
MANAGER_KEYBOARD = {
    "keyboard": [
        [
            {"text": "👥 Staff Status"},
            {"text": "⚠️ Open Issues"},
        ],
    ],
    "resize_keyboard": True,
    "persistent": True,
    "input_field_placeholder": "Select an option...",
}

REMOVE_KEYBOARD = {"remove_keyboard": True}


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=10.0)
    return _client


async def close_client() -> None:
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None


async def send_telegram_message(
    chat_id: str,
    text: str,
    reply_markup: dict | None = None,
) -> int | None:
    """Send a plain text message. Returns the Telegram message_id on success, else None."""
    client = await get_client()
    settings = get_settings()
    url = f"{settings.telegram_api_url}/sendMessage"
    payload: dict = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("result", {}).get("message_id")
    except httpx.HTTPError as exc:
        logger.error("Failed to send Telegram message to %s: %s", chat_id, exc)
        return None


async def send_step_message(chat_id: str, text: str) -> int | None:
    """Send a step instruction with Done and Report Issue inline buttons.
    Returns message_id on success, else None."""
    client = await get_client()
    settings = get_settings()
    url = f"{settings.telegram_api_url}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": "✅ Done", "callback_data": "done"},
                    {"text": "⚠️ Report Issue", "callback_data": "report_issue"},
                ]
            ]
        },
    }
    try:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("result", {}).get("message_id")
    except httpx.HTTPError as exc:
        logger.error("Failed to send step message to %s: %s", chat_id, exc)
        return None


async def delete_message(chat_id: str, message_id: int) -> bool:
    """Delete a specific message in a chat."""
    client = await get_client()
    settings = get_settings()
    url = f"{settings.telegram_api_url}/deleteMessage"
    payload = {"chat_id": chat_id, "message_id": message_id}
    try:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        logger.warning("Failed to delete message %s in chat %s: %s", message_id, chat_id, exc)
        return False


async def send_photo_to_manager(
    manager_chat_id: str,
    file_id: str,
    caption: str,
) -> bool:
    """Forward a staff photo to the manager with a caption."""
    client = await get_client()
    settings = get_settings()
    url = f"{settings.telegram_api_url}/sendPhoto"
    payload = {
        "chat_id": manager_chat_id,
        "photo": file_id,
        "caption": caption,
        "parse_mode": "HTML",
    }
    try:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        logger.error("Failed to send photo to manager %s: %s", manager_chat_id, exc)
        return False


async def edit_message_reply_markup(
    chat_id: str, message_id: int, reply_markup: dict | None = None
) -> bool:
    """Edit (or remove) inline keyboard on an existing message."""
    client = await get_client()
    settings = get_settings()
    url = f"{settings.telegram_api_url}/editMessageReplyMarkup"
    payload: dict = {"chat_id": chat_id, "message_id": message_id}
    payload["reply_markup"] = reply_markup or {}
    try:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        logger.warning("Failed to edit reply markup for msg %s: %s", message_id, exc)
        return False


async def answer_callback_query(callback_query_id: str, text: str = "") -> None:
    """Acknowledge a Telegram callback query to dismiss the loading spinner."""
    client = await get_client()
    settings = get_settings()
    url = f"{settings.telegram_api_url}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id, "text": text}
    try:
        response = await client.post(url, json=payload)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("Failed to answer callback query %s: %s", callback_query_id, exc)


async def notify_manager(manager_chat_id: str | None, message: str | None) -> None:
    """Send a text notification to the manager."""
    if manager_chat_id and message:
        await send_telegram_message(manager_chat_id, message)


async def register_bot_commands() -> None:
    """Register slash commands with Telegram so they appear in the menu."""
    from app.bot.commands import BOT_COMMANDS
    client = await get_client()
    settings = get_settings()
    url = f"{settings.telegram_api_url}/setMyCommands"
    try:
        response = await client.post(url, json={"commands": BOT_COMMANDS})
        response.raise_for_status()
        logger.info("Bot commands registered successfully")
    except httpx.HTTPError as exc:
        logger.error("Failed to register bot commands: %s", exc)