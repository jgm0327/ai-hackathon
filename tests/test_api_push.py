"""/api/push/* 테스트 — Track E 이식(9/13), 9/23 로그인 연결에 맞춰 재작성.

그전 버전은 `subscription_store` 함수를 모킹하고 "endpoint 해시가 user_id로 쓰이는지"를
검증했다. 그 구조 자체가 문제였다 — 알림 설정이 계정이 아니라 브라우저에 붙어서,
로그아웃해도 구독이 남고 기기마다 설정이 갈라졌다. 지금은 다른 라우터와 같이 로그인
유저 기준이라 conftest의 `current_user_id` 픽스처 위에서 실제 DB로 검증한다.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.storage import db


@pytest.fixture
def client():
    return TestClient(app)


def _payload(endpoint="https://fcm.googleapis.com/fcm/send/abc123", **kwargs):
    body = {
        "endpoint": endpoint,
        "keys": {"p256dh": "p-key", "auth": "a-key"},
        "leave_time": "18:00",
    }
    body.update(kwargs)
    return body


# --- VAPID 공개키 ---


def test_get_vapid_public_key_returns_configured_key(client):
    # settings는 frozen dataclass라 필드를 못 바꾼다 — 객체 자체를 갈아끼운다.
    with patch("src.api.routers.push.settings") as mock_settings:
        mock_settings.vapid_public_key = "fake-public-key"
        response = client.get("/api/push/vapid-public-key")
    assert response.status_code == 200
    assert response.json() == {"public_key": "fake-public-key"}


def test_get_vapid_public_key_503_when_not_configured(client):
    with patch("src.api.routers.push.settings") as mock_settings:
        mock_settings.vapid_public_key = ""
        assert client.get("/api/push/vapid-public-key").status_code == 503


# --- 로그인 ---


@pytest.mark.parametrize(
    "method,path,json_body",
    [
        ("get", "/api/push/settings", None),
        ("post", "/api/push/subscribe", _payload()),
        ("put", "/api/push/settings", {"leave_time": "18:00"}),
        ("delete", "/api/push/subscribe", None),
    ],
)
def test_requires_login(client, method, path, json_body):
    """9/23 — 그전까지 이 엔드포인트들엔 인증이 없었다."""
    response = client.request(method.upper(), path, json=json_body)
    assert response.status_code == 401


# --- 구독 ---


def test_subscribe_stores_device_under_current_user(client, current_user_id):
    response = client.post("/api/push/subscribe", json=_payload())
    assert response.status_code == 201
    assert response.json() == {
        "enabled": True,
        "leave_time": "18:00",
        "skip_weekends": False,
        "device_count": 1,
    }

    devices = db.list_push_subscriptions(current_user_id)
    assert len(devices) == 1
    assert devices[0].endpoint == _payload()["endpoint"]
    assert devices[0].user_id == current_user_id


def test_subscribe_twice_from_same_browser_is_one_device(client, current_user_id):
    """같은 endpoint면 upsert — 기기 목록이 불어나지 않는다."""
    client.post("/api/push/subscribe", json=_payload())
    response = client.post("/api/push/subscribe", json=_payload())
    assert response.json()["device_count"] == 1


def test_subscribing_from_second_device_keeps_one_setting(client, current_user_id):
    """기기는 늘어도 설정은 한 벌이다."""
    client.post("/api/push/subscribe", json=_payload(leave_time="18:00"))
    response = client.post(
        "/api/push/subscribe", json=_payload("https://example.test/second", leave_time="19:00")
    )
    assert response.json() == {
        "enabled": True,
        "leave_time": "19:00",
        "skip_weekends": False,
        "device_count": 2,
    }
    assert db.get_push_settings(current_user_id).leave_time == "19:00"


def test_subscribe_passes_skip_weekends_through(client, current_user_id):
    """온보딩 4/4 "주말에는 쉬어요" 토글 (9/18)."""
    response = client.post("/api/push/subscribe", json=_payload(skip_weekends=True))
    assert response.json()["skip_weekends"] is True


@pytest.mark.parametrize("bad", ["25:00", "8:00", "1800", "", "이상한값"])
def test_subscribe_rejects_malformed_leave_time(client, current_user_id, bad):
    """형식이 깨지면 발송 루프가 그 유저를 통째로 건너뛰므로 입력에서 막는다."""
    assert client.post("/api/push/subscribe", json=_payload(leave_time=bad)).status_code == 422


# --- 설정 조회 / 변경 ---


def test_settings_default_to_off(client, current_user_id):
    """한 번도 켠 적 없으면 꺼짐. 화면은 이 값을 보고 그린다."""
    response = client.get("/api/push/settings")
    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "leave_time": "18:00",
        "skip_weekends": True,
        "device_count": 0,
    }


def test_settings_survive_logout(client, current_user_id):
    """9/23 신고의 핵심 — 브라우저 저장소가 비어도 서버가 진실을 알고 있어야 한다.

    그전엔 설정 화면이 localStorage만 봤고 로그아웃이 그 키를 지워서, 구독이 살아
    있는데도 화면엔 "꺼짐"으로 보였다. 서버 조회에는 브라우저 상태가 섞이지 않는다.
    """
    client.post("/api/push/subscribe", json=_payload())
    assert client.get("/api/push/settings").json()["enabled"] is True


def test_update_settings_changes_time_without_resubscribing(client, current_user_id):
    """이미 구독 중인 사람이 시각만 바꾸는 경로.

    그전엔 이 경로가 없어서 화면에서 시각을 바꿔도 서버엔 아무것도 가지 않았다.
    """
    client.post("/api/push/subscribe", json=_payload(leave_time="18:00"))
    response = client.put(
        "/api/push/settings", json={"leave_time": "17:00", "skip_weekends": True}
    )
    assert response.json() == {
        "enabled": True,
        "leave_time": "17:00",
        "skip_weekends": True,
        "device_count": 1,
    }


def test_update_settings_does_not_turn_notifications_on(client, current_user_id):
    """켜는 건 구독 생성이 필요하므로 이 경로로는 안 켜진다."""
    response = client.put("/api/push/settings", json={"leave_time": "17:00"})
    assert response.json()["enabled"] is False
    assert db.get_push_settings(current_user_id).leave_time == "17:00"


# --- 끄기 ---


def test_unsubscribe_removes_every_device(client, current_user_id):
    """끄기는 계정 단위 — 보고 있는 기기만 멈추면 다른 기기에서 계속 온다."""
    client.post("/api/push/subscribe", json=_payload())
    client.post("/api/push/subscribe", json=_payload("https://example.test/second"))

    response = client.delete("/api/push/subscribe")
    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "leave_time": "18:00",
        "skip_weekends": False,
        "device_count": 0,
    }
    assert db.list_push_subscriptions(current_user_id) == []
    assert db.get_push_settings(current_user_id).enabled is False


def test_unsubscribe_is_idempotent(client, current_user_id):
    """구독이 없어도 조용히 성공한다."""
    assert client.delete("/api/push/subscribe").status_code == 200
    assert client.delete("/api/push/subscribe").json()["enabled"] is False


def test_unsubscribe_clears_sent_mark_so_same_day_reenable_works(client, current_user_id):
    """껐다가 같은 날 다시 켜면 그날 알림을 받을 수 있어야 한다."""
    client.post("/api/push/subscribe", json=_payload())
    db.mark_push_sent(current_user_id, "2026-09-23")
    client.delete("/api/push/subscribe")
    assert db.get_push_settings(current_user_id).last_sent_date is None


def test_unsubscribe_keeps_chosen_time_for_next_time(client, current_user_id):
    """다시 켤 때 시각을 처음부터 고르게 하지 않는다."""
    client.post("/api/push/subscribe", json=_payload(leave_time="17:00"))
    client.delete("/api/push/subscribe")
    assert client.get("/api/push/settings").json()["leave_time"] == "17:00"


# --- 계정 경계 ---


def test_device_moves_to_the_account_that_last_logged_in(client, current_user_id):
    """같은 브라우저에서 다른 계정으로 로그인하면 그 기기는 새 계정 것이 된다.

    예전 구조에서는 endpoint 해시가 곧 user_id라 앞사람 구독을 덮어쓰면서도 그게
    누구 것인지 알 수 없었다.
    """
    from src.auth.deps import get_current_user

    client.post("/api/push/subscribe", json=_payload())

    other_id = db.upsert_user("other-kakao", "다른 사람", None, "2026-01-01T00:00:00")
    app.dependency_overrides[get_current_user] = lambda: db.get_user(other_id)
    try:
        client.post("/api/push/subscribe", json=_payload())
        assert db.list_push_subscriptions(other_id)[0].user_id == other_id
    finally:
        app.dependency_overrides[get_current_user] = lambda: db.get_user(current_user_id)

    assert db.list_push_subscriptions(current_user_id) == []
