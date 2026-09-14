"""Track E 이식: POST/DELETE /api/push/subscribe, GET /api/push/vapid-public-key 테스트.

실제 Upstash/로컬 파일 접근 없이 subscription_store 함수 자체를 모킹한다.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_get_vapid_public_key_returns_configured_key(client):
    with patch("src.api.routers.push.settings") as mock_settings:
        mock_settings.vapid_public_key = "fake-public-key"
        response = client.get("/api/push/vapid-public-key")

    assert response.status_code == 200
    assert response.json() == {"public_key": "fake-public-key"}


def test_get_vapid_public_key_503_when_not_configured(client):
    with patch("src.api.routers.push.settings") as mock_settings:
        mock_settings.vapid_public_key = ""
        response = client.get("/api/push/vapid-public-key")

    assert response.status_code == 503


def test_subscribe_saves_with_hashed_endpoint_as_user_id(client):
    payload = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/abc123",
        "keys": {"p256dh": "p-key", "auth": "a-key"},
        "leave_time": "18:00",
    }
    with patch("src.api.routers.push.save_subscription") as mock_save:
        response = client.post("/api/push/subscribe", json=payload)

    assert response.status_code == 201
    mock_save.assert_called_once()
    user_id, subscription, leave_time = mock_save.call_args[0]
    assert len(user_id) == 64  # sha256 hexdigest
    assert subscription == {
        "endpoint": payload["endpoint"],
        "keys": {"p256dh": "p-key", "auth": "a-key"},
    }
    assert leave_time == "18:00"


def test_subscribe_is_deterministic_per_endpoint(client):
    """같은 endpoint로 다시 구독하면 같은 user_id로 upsert돼야 한다(중복 구독 방지)."""
    payload = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/same",
        "keys": {"p256dh": "p", "auth": "a"},
        "leave_time": "18:00",
    }
    with patch("src.api.routers.push.save_subscription") as mock_save:
        client.post("/api/push/subscribe", json=payload)
        client.post("/api/push/subscribe", json=payload)

    first_user_id = mock_save.call_args_list[0][0][0]
    second_user_id = mock_save.call_args_list[1][0][0]
    assert first_user_id == second_user_id


def test_unsubscribe_deletes_by_hashed_endpoint(client):
    with patch("src.api.routers.push.delete_subscription") as mock_delete:
        response = client.request(
            "DELETE",
            "/api/push/subscribe",
            json={"endpoint": "https://fcm.googleapis.com/fcm/send/abc123"},
        )

    assert response.status_code == 204
    mock_delete.assert_called_once()
    assert len(mock_delete.call_args[0][0]) == 64
