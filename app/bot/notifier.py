"""Manager notification sender – sends Telegram messages via httpx."""

import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


async def get_client() -> httpx.AsyncClient:
    """Return a reusable async HTTP client."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=10.0)
    return _client


async def close_client() -> None:
    """Close the HTTP client on shutdown."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None


async def send_telegram_message(chat_id: str, text: str) -> bool:
    """Send a text message to a Telegram chat. Returns True on success."""
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


async def notify_manager(manager_chat_id: str | None, message: str | None) -> None:
    """Send a notification to the manager if both chat_id and message are provided."""
    if manager_chat_id and message:
        await send_telegram_message(manager_chat_id, message)
