"""/api/push/* — 퇴근 알림 구독과 설정. Track E 이식 (P1, 9/13).

docs/06-migration.md 1장: 로직(`push_sender.py`, VAPID 키)은 그대로 두고 HTTP 레이어만
새로 얹는다.

**로그인 연결 (9/23)**: 이 라우터는 9/13에 "인증 없는 단일 유저 데모" 전제로 만들어져
`sha256(endpoint)`를 user_id 자리에 쓰고 있었다. 9/14에 카카오 로그인이 들어오면서
cards/projects/profile/notion은 전부 `Depends(get_current_user)`로 옮겨갔는데 **push만
남아 있었다.** 그 결과:

  - 알림 설정이 계정이 아니라 브라우저 하나에 붙었다 — 기기가 늘면 설정이 갈라진다.
  - 같은 브라우저에서 다른 계정으로 로그인하면 endpoint가 같아 앞사람 구독을 덮어썼다.
  - 로그아웃은 localStorage만 비우고 구독은 남겨서, 화면엔 "꺼짐"인데 알림은 계속
    오는 상태가 됐다(사용자 신고).

이제 다른 라우터와 같이 로그인 유저 기준으로 동작한다. 저장소도 Upstash Redis에서
SQLite로 옮겨왔다(`src/storage/db.py`의 `push_subscriptions` / `push_settings`).

**켜기/끄기의 비대칭**: 켜기는 브라우저 권한과 구독 생성이 필요해 반드시 기기에서
일어나지만(`POST /push/subscribe`), 끄기는 계정 단위다(`DELETE /push/subscribe`) —
보고 있는 기기 하나만 멈추면 나머지 기기에서 계속 오기 때문이다.
"""
from fastapi import APIRouter, Depends, HTTPException

from src.api.schemas import (
    PushSettingsResponse,
    PushSettingsUpdateRequest,
    PushSubscribeRequest,
    VapidPublicKeyResponse,
)
from src.auth.deps import get_current_user
from src.config import settings
from src.storage import db
from src.timeutil import now_local

router = APIRouter(tags=["push"])


def _settings_response(user_id: int) -> PushSettingsResponse:
    prefs = db.get_push_settings(user_id)
    devices = db.list_push_subscriptions(user_id)
    return PushSettingsResponse(
        # 기기가 한 대도 없으면 보낼 곳이 없으므로 "켜짐"이라고 말하지 않는다 —
        # 발송 루프도 같은 기준으로 대상을 고른다(`list_push_recipients`).
        enabled=prefs.enabled and bool(devices),
        leave_time=prefs.leave_time,
        skip_weekends=prefs.skip_weekends,
        device_count=len(devices),
    )


@router.get("/push/vapid-public-key", response_model=VapidPublicKeyResponse)
def get_vapid_public_key() -> VapidPublicKeyResponse:
    """프론트가 `pushManager.subscribe({applicationServerKey: ...})`에 쓸 공개키.

    공개키라 노출해도 안전하다(src/config.py의 vapid_public_key 주석 참고).
    로그인 없이도 준다 — 이 값 자체엔 유저 정보가 없다.
    """
    if not settings.vapid_public_key:
        raise HTTPException(
            status_code=503, detail="웹 푸시가 서버에 설정되어 있지 않습니다 (VAPID_PUBLIC_KEY)."
        )
    return VapidPublicKeyResponse(public_key=settings.vapid_public_key)


@router.get("/push/settings", response_model=PushSettingsResponse)
def get_push_settings(
    current_user: db.User = Depends(get_current_user),
) -> PushSettingsResponse:
    """설정 화면이 읽는 값. 한 번도 켠 적이 없으면 기본값(꺼짐)이 온다."""
    return _settings_response(current_user.id)


@router.post("/push/subscribe", response_model=PushSettingsResponse, status_code=201)
def subscribe(
    payload: PushSubscribeRequest, current_user: db.User = Depends(get_current_user)
) -> PushSettingsResponse:
    """이 기기를 등록하고 알림을 켠다. 같은 endpoint로 다시 불러도 upsert된다."""
    db.save_push_subscription(
        current_user.id,
        payload.endpoint,
        payload.keys.p256dh,
        payload.keys.auth,
        now_local().isoformat(timespec="seconds"),
    )
    db.save_push_settings(
        current_user.id, True, payload.leave_time, payload.skip_weekends
    )
    return _settings_response(current_user.id)


@router.put("/push/settings", response_model=PushSettingsResponse)
def update_push_settings(
    payload: PushSettingsUpdateRequest, current_user: db.User = Depends(get_current_user)
) -> PushSettingsResponse:
    """시각·주말만 고친다. 이미 켜져 있는 사람이 값만 바꾸는 경로.

    그전까지 이 경로가 없어서, 이미 구독 중이면 화면에서 시각을 바꿔도 서버엔 아무것도
    가지 않았다 — 계속 옛 시각에 알림이 왔다(9/23 수정).
    """
    prefs = db.get_push_settings(current_user.id)
    db.save_push_settings(
        current_user.id, prefs.enabled, payload.leave_time, payload.skip_weekends
    )
    return _settings_response(current_user.id)


@router.delete("/push/subscribe", response_model=PushSettingsResponse)
def unsubscribe(current_user: db.User = Depends(get_current_user)) -> PushSettingsResponse:
    """알림을 끈다 — **이 계정의 기기 전부**. 구독이 없어도 조용히 성공한다(멱등).

    기기 하나만 빼는 경로는 두지 않았다. 사용자가 보는 화면에는 "알림 끄기" 하나뿐이고,
    거기서 보고 있는 기기만 멈추면 다른 기기에서 계속 와서 "껐는데 온다"가 된다 —
    이 기능이 신고받은 문제가 정확히 그 모양이었다.
    """
    db.delete_push_subscriptions_for_user(current_user.id)
    prefs = db.get_push_settings(current_user.id)
    db.save_push_settings(current_user.id, False, prefs.leave_time, prefs.skip_weekends)
    return _settings_response(current_user.id)
