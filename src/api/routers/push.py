"""POST/DELETE /api/push/subscribe, GET /api/push/vapid-public-key — Track E 이식 (P1, 9/13).

docs/06-migration.md 1장: 로직(`src/push/subscription_store.py`, `push_sender.py`,
VAPID 키)은 그대로 두고 HTTP 레이어만 새로 얹는다.

이 API엔 로그인이 없다(docs/05-api-contract.md 전제, 해커톤 단일 유저 데모).
`subscription_store`는 구독을 user_id로 구분하는데, PushSubscription의 endpoint
URL은 브라우저+기기 조합마다 고유하므로 이 값을 해시해 user_id로 그대로 쓴다 —
별도 로그인/클라이언트 UUID 발급 없이도 구독을 구분할 수 있다.
"""
import hashlib

from fastapi import APIRouter, HTTPException

from src.api.schemas import PushSubscribeRequest, PushUnsubscribeRequest, VapidPublicKeyResponse
from src.config import settings
from src.push.subscription_store import delete_subscription, save_subscription

router = APIRouter(tags=["push"])


def _endpoint_to_user_id(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()


@router.get("/push/vapid-public-key", response_model=VapidPublicKeyResponse)
def get_vapid_public_key() -> VapidPublicKeyResponse:
    """프론트가 `pushManager.subscribe({applicationServerKey: ...})`에 쓸 공개키.

    공개키라 노출해도 안전하다(src/config.py의 vapid_public_key 주석 참고).
    """
    if not settings.vapid_public_key:
        raise HTTPException(
            status_code=503, detail="웹 푸시가 서버에 설정되어 있지 않습니다 (VAPID_PUBLIC_KEY)."
        )
    return VapidPublicKeyResponse(public_key=settings.vapid_public_key)


@router.post("/push/subscribe", status_code=201)
def subscribe(payload: PushSubscribeRequest) -> None:
    user_id = _endpoint_to_user_id(payload.endpoint)
    subscription = {"endpoint": payload.endpoint, "keys": payload.keys.model_dump()}
    save_subscription(user_id, subscription, payload.leave_time)


@router.delete("/push/subscribe", status_code=204)
def unsubscribe(payload: PushUnsubscribeRequest) -> None:
    user_id = _endpoint_to_user_id(payload.endpoint)
    delete_subscription(user_id)  # 존재하지 않아도 조용히 무시됨(멱등)
