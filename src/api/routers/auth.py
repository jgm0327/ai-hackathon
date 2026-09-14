"""GET/POST /api/auth/* — 카카오 소셜 로그인 — Track B 담당 (9/14 신규).

`docs/05-api-contract.md`에 있던 "인증 없음" 전제를 이번 개정으로 뒤집는다.
플로우 전체는 계획서(카카오 소셜 로그인 + 진입 게이팅) 1~5장 참고:

1. `GET /kakao/login` — 카카오 인가 화면으로 리다이렉트 (CSRF 방지용 state를
   임시 쿠키에 저장)
2. `GET /kakao/callback` — 카카오가 되돌아오는 지점. state 검증 → 토큰 교환 →
   사용자 정보 조회 → 유저 upsert → 세션 생성 → session_id 쿠키 설정 → 프론트로 리다이렉트
3. `GET /me` — 지금 로그인한 유저 정보. 401이면 로그아웃 상태(프론트가 이걸로 판단)
4. `POST /logout` — 세션 삭제 + 쿠키 제거
"""
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from src.auth.deps import SESSION_COOKIE_NAME, get_current_user
from src.auth.kakao_client import KakaoOAuthError, build_authorize_url, exchange_code_for_token, fetch_kakao_user
from src.api.schemas import MeResponse
from src.config import settings
from src.storage import db

router = APIRouter(prefix="/auth", tags=["auth"])

_OAUTH_STATE_COOKIE = "oauth_state"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/kakao/login")
def kakao_login() -> RedirectResponse:
    """카카오 인가 화면으로 리다이렉트한다. CSRF 방지용 state를 임시 쿠키에 저장해뒀다가
    콜백에서 대조한다."""
    state = secrets.token_urlsafe(16)
    response = RedirectResponse(url=build_authorize_url(state))
    response.set_cookie(
        _OAUTH_STATE_COOKIE,
        state,
        max_age=600,  # 10분 — 로그인 화면에서 오래 머물러도 넉넉하게, 그래도 짧게 유지
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/kakao/callback")
def kakao_callback(request: Request, code: str, state: str) -> RedirectResponse:
    """카카오가 인가 코드와 함께 되돌아오는 지점. 여기서 실제 로그인이 완성된다."""
    saved_state = request.cookies.get(_OAUTH_STATE_COOKIE)
    if not saved_state or saved_state != state:
        raise HTTPException(status_code=400, detail="잘못된 로그인 요청입니다(state 불일치). 다시 시도해 주세요.")

    try:
        token = exchange_code_for_token(code)
        kakao_user = fetch_kakao_user(token.access_token)
    except KakaoOAuthError as e:
        raise HTTPException(status_code=502, detail=f"카카오 로그인에 실패했습니다: {e}") from e

    now = _now_iso()
    user_id = db.upsert_user(kakao_user.kakao_id, kakao_user.nickname, kakao_user.profile_image_url, now)
    session = db.create_session(user_id, ttl_days=settings.session_ttl_days)

    response = RedirectResponse(url=settings.frontend_base_url + "/")
    response.delete_cookie(_OAUTH_STATE_COOKIE, path="/")
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session.id,
        max_age=settings.session_ttl_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/me", response_model=MeResponse)
def get_me(current_user: db.User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        id=current_user.id,
        nickname=current_user.nickname,
        profile_image_url=current_user.profile_image_url,
    )


@router.post("/logout", status_code=204)
def logout(request: Request) -> Response:
    """세션을 지운다(로그아웃). 세션 쿠키가 없거나 이미 만료됐어도 조용히 204(멱등)."""
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        db.delete_session(session_id)
    # 응답 자체에 delete_cookie를 걸어야 해서, 데코레이터의 status_code=204에
    # 기대는 대신 Response 객체를 직접 만들어 반환한다.
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return response
