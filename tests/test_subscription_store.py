"""Track E 담당: save_subscription()/list_subscriptions()의 Upstash 연동 +
로컬 폴백 테스트. 실제 Upstash API를 호출하지 않도록 requests.post를 모킹한다.
"""
from unittest.mock import MagicMock, patch

import pytest

from src.push import subscription_store as store


@pytest.fixture(autouse=True)
def _isolate_store_path(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "_STORE_PATH", tmp_path / "push_subscriptions.json")
    yield


def _fake_settings(**overrides):
    class _S:
        upstash_redis_rest_url = ""
        upstash_redis_rest_token = ""

    s = _S()
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def test_local_fallback_when_upstash_not_configured():
    with patch.object(store, "settings", _fake_settings()):
        store.save_subscription("user1", {"endpoint": "https://x", "keys": {}}, "18:00")
        data = store.list_subscriptions()
        assert data["user1"]["leave_time"] == "18:00"


def test_save_subscription_calls_upstash_hset_when_configured():
    settings_obj = _fake_settings(
        upstash_redis_rest_url="https://fake.upstash.io", upstash_redis_rest_token="tok"
    )
    with patch.object(store, "settings", settings_obj):
        with patch("src.push.subscription_store.requests") as mock_requests:
            mock_requests.post.return_value = MagicMock(
                status_code=200, json=lambda: {"result": 1}
            )
            store.save_subscription("user1", {"endpoint": "https://x", "keys": {}}, "18:00")

            mock_requests.post.assert_called_once()
            args, kwargs = mock_requests.post.call_args
            assert args[0] == "https://fake.upstash.io"
            assert kwargs["headers"]["Authorization"] == "Bearer tok"
            command = kwargs["json"]
            assert command[0] == "HSET"
            assert command[1] == "push_subscriptions"
            assert command[2] == "user1"


def test_list_subscriptions_parses_upstash_hgetall_response():
    settings_obj = _fake_settings(
        upstash_redis_rest_url="https://fake.upstash.io", upstash_redis_rest_token="tok"
    )
    with patch.object(store, "settings", settings_obj):
        with patch("src.push.subscription_store.requests") as mock_requests:
            mock_requests.post.return_value = MagicMock(
                status_code=200,
                json=lambda: {
                    "result": [
                        "user1",
                        '{"subscription": {"endpoint": "https://x"}, "leave_time": "18:00"}',
                    ]
                },
            )
            data = store.list_subscriptions()
            assert data == {
                "user1": {"subscription": {"endpoint": "https://x"}, "leave_time": "18:00"}
            }


def test_list_subscriptions_empty_when_upstash_returns_none():
    settings_obj = _fake_settings(
        upstash_redis_rest_url="https://fake.upstash.io", upstash_redis_rest_token="tok"
    )
    with patch.object(store, "settings", settings_obj):
        with patch("src.push.subscription_store.requests") as mock_requests:
            mock_requests.post.return_value = MagicMock(status_code=200, json=lambda: {"result": None})
            assert store.list_subscriptions() == {}


def test_delete_subscription_removes_from_local_fallback():
    with patch.object(store, "settings", _fake_settings()):
        store.save_subscription("user1", {"endpoint": "https://x", "keys": {}}, "18:00")
        store.delete_subscription("user1")
        assert store.list_subscriptions() == {}


def test_delete_subscription_is_idempotent_when_missing():
    with patch.object(store, "settings", _fake_settings()):
        store.delete_subscription("no-such-user")  # 에러 없이 조용히 무시
        assert store.list_subscriptions() == {}


def test_delete_subscription_calls_upstash_hdel_when_configured():
    settings_obj = _fake_settings(
        upstash_redis_rest_url="https://fake.upstash.io", upstash_redis_rest_token="tok"
    )
    with patch.object(store, "settings", settings_obj):
        with patch("src.push.subscription_store.requests") as mock_requests:
            mock_requests.post.return_value = MagicMock(status_code=200, json=lambda: {"result": 1})
            store.delete_subscription("user1")

            mock_requests.post.assert_called_once()
            _, kwargs = mock_requests.post.call_args
            assert kwargs["json"] == ["HDEL", "push_subscriptions", "user1"]
