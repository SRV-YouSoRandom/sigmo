"""Tests for manager notification triggers."""

import pytest
from unittest.mock import AsyncMock, patch

from app.bot.notifier import notify_manager, send_telegram_message


@pytest.mark.asyncio
async def test_send_telegram_message_success():
    """Successful Telegram API call returns True."""
    with patch("app.bot.notifier.get_client") as mock_get:
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.raise_for_status = lambda: None
        mock_client.post.return_value = mock_response
        mock_get.return_value = mock_client

        result = await send_telegram_message("12345", "hello")
        assert result is True
        mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_send_telegram_message_failure():
    """Failed Telegram API call returns False."""
    import httpx

    with patch("app.bot.notifier.get_client") as mock_get:
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.HTTPError("fail")
        mock_get.return_value = mock_client

        result = await send_telegram_message("12345", "hello")
        assert result is False


@pytest.mark.asyncio
async def test_notify_manager_with_values():
    """notify_manager sends a message when both args are provided."""
    with patch("app.bot.notifier.send_telegram_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        await notify_manager("999", "test message")
        mock_send.assert_called_once_with("999", "test message")


@pytest.mark.asyncio
async def test_notify_manager_skips_none():
    """notify_manager does nothing when chat_id or message is None."""
    with patch("app.bot.notifier.send_telegram_message", new_callable=AsyncMock) as mock_send:
        await notify_manager(None, "test")
        mock_send.assert_not_called()

        await notify_manager("999", None)
        mock_send.assert_not_called()
