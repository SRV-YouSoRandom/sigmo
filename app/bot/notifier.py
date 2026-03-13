"""Manager notification sender – sends Telegram messages via httpx."""

import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


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


async def send_telegram_message(chat_id: str, text: str) -> bool:
    """Send a plain text message to a Telegram chat."""
    client = await get_client()
    settings = get_settings()
    url = f"{settings.telegram_api_url}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    try:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        logger.error("Failed to send Telegram message to %s: %s", chat_id, exc)
        return False


async def send_step_message(chat_id: str, text: str) -> bool:
    """Send a step instruction with Done and Report Issue inline buttons."""
    client = await get_client()
    settings = get_settings()
    url = f"{settings.telegram_api_url}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
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
        return True
    except httpx.HTTPError as exc:
        logger.error("Failed to send step message to %s: %s", chat_id, exc)
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
    """Send a notification to the manager if both chat_id and message are provided."""
    if manager_chat_id and message:
        await send_telegram_message(manager_chat_id, message)