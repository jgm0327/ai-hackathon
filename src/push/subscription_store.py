"""PushSubscription 저장/조회 — Track E(Tier 2) 담당.

해커톤 규모에서는 JSON 파일 하나로 충분하다. 여러 유저를 지원해야 하면
가벼운 SQLite/DB로 교체를 고려하되, 인터페이스(save_subscription/list_subscriptions)는
그대로 유지해서 push_sender.py가 영향받지 않게 한다.
"""
import json
from pathlib import Path

_STORE_PATH = Path("data/push_subscriptions.json")


def save_subscription(user_id: str, subscription: dict, leave_time: str) -> None:
    """유저의 PushSubscription 객체와 퇴근 시각을 저장한다.

    subscription: 브라우저 Push API가 발급하는 {"endpoint": ..., "keys": {...}} 형태.
    leave_time: "HH:MM" 형식. 서버가 이 시각-15분에 맞춰 발송할 때 사용.
    """
    data = _load_all()
    data[user_id] = {"subscription": subscription, "leave_time": leave_time}
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def list_subscriptions() -> dict:
    """모든 유저의 구독 정보를 반환한다. GitHub Actions 트리거가 이걸 순회하며 발송."""
    return _load_all()


def _load_all() -> dict:
    if not _STORE_PATH.exists():
        return {}
    return json.loads(_STORE_PATH.read_text(encoding="utf-8"))
