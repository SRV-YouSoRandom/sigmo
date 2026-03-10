"""Tests for the webhook endpoint."""

import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a FastAPI test client with mocked startup dependencies."""
    with patch("app.core.scheduler.scheduler"):
        from app.main import app
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
