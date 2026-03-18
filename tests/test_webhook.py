"""Tests for the webhook endpoint."""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture
def client():
    """Create a FastAPI test client with mocked startup dependencies."""
    with patch("app.core.scheduler.scheduler"), \
         patch("app.core.scheduler.schedule_restaurant_reminders", new_callable=AsyncMock), \
         patch("app.bot.notifier.register_bot_commands", new_callable=AsyncMock), \
         patch("app.bot.handlers.process_update", new_callable=AsyncMock):
        from app.main import app
        from fastapi.testclient import TestClient
        return TestClient(app)


def test_webhook_returns_ok(client):
    """POST /webhook returns {ok: true} immediately."""
    payload = {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "chat": {"id": 123},
            "text": "hello",
        },
    }
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_webhook_empty_body(client):
    """POST /webhook with empty update still returns ok."""
    response = client.post("/webhook", json={"update_id": 2})
    assert response.status_code == 200
    assert response.json() == {"ok": True}
