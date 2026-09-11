"""PushSubscription 저장/조회 — Track E(Tier 2) 담당.

저장소: **Upstash Redis**(REST API, 무료 티어)를 기본으로 쓴다.
`UPSTASH_REDIS_REST_URL`/`UPSTASH_REDIS_REST_TOKEN`이 없으면(로컬 개발 등) 로컬 JSON
파일(`data/push_subscriptions.json`)로 자동 폴백한다 — 이 프로젝트의 LLM_PROVIDER,
EMBEDDING_PROVIDER와 동일한 "설정 있으면 실제 서비스, 없으면 로컬 폴백" 패턴이다.

Upstash를 쓰는 이유(9/10): 배포된 Streamlit 앱(구독을 "쓰는" 쪽)과 GitHub Actions
스케줄 워크플로(발송 대상을 "읽는" 쪽)는 서로 다른 프로세스라 파일시스템을 공유하지
않는다. 처음엔 이 문제를 "구독 데이터를 저장소에 git 커밋"으로 풀었는데, 저장소를
나중에 public으로 전환할 계획이 생기면서 구독 정보(사실상 기기 식별자)가 커밋
히스토리에 영구 노출되는 문제가 있어 외부 key-value 저장소로 교체함
(docs/03-risk-fallback.md 리스크 1의 두 번째 폴백안).
"""
import json
from pathlib import Path
from typing import Any

import requests

from src.config import settings

_STORE_PATH = Path("data/push_subscriptions.json")  # Upstash 미설정 시 로컬 폴백용
_REDIS_KEY = "push_subscriptions"


def save_subscription(user_id: str, subscription: dict, leave_time: str) -> None:
    """유저의 PushSubscription 객체와 퇴근 시각을 저장한다.

    subscription: 브라우저 Push API가 발급하는 {"endpoint": ..., "keys": {...}} 형태.
    leave_time: "HH:MM" 형식. 서버가 이 시각-15분에 맞춰 발송할 때 사용.
    """
    entry = {"subscription": subscription, "leave_time": leave_time}
    if _upstash_configured():
        _upstash_command("HSET", _REDIS_KEY, user_id, json.dumps(entry, ensure_ascii=False))
    else:
        data = _load_local()
        data[user_id] = entry
        _save_local(data)


def list_subscriptions() -> dict:
    """모든 유저의 구독 정보를 반환한다. GitHub Actions 트리거가 이걸 순회하며 발송."""
    if _upstash_configured():
        flat = _upstash_command("HGETALL", _REDIS_KEY) or []
        return {flat[i]: json.loads(flat[i + 1]) for i in range(0, len(flat), 2)}
    return _load_local()


def _upstash_configured() -> bool:
    return bool(settings.upstash_redis_rest_url and settings.upstash_redis_rest_token)


def _upstash_command(*args: str) -> Any:
    """Upstash REST API 단일 명령 실행. https://upstash.com/docs/redis/features/restapi"""
    response = requests.post(
        settings.upstash_redis_rest_url,
        headers={"Authorization": f"Bearer {settings.upstash_redis_rest_token}"},
        json=list(args),
        timeout=10,
    )
    response.raise_for_status()
    return response.json().get("result")


def _load_local() -> dict:
    if not _STORE_PATH.exists():
        return {}
    return json.loads(_STORE_PATH.read_text(encoding="utf-8"))


def _save_local(data: dict) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
