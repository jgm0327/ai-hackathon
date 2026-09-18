"""노션 연동 — 페이지 목록 + 고른 페이지 하나의 본문 (Figma 3.0-b "노션 페이지 선택").

**9/18 전면 재작성.** `POST /api/notion/sync`(대량 가져오기)를 제거하고 두 개로 나눴다.

옛 엔드포인트는 `/v1/search`를 필터 없이 불러 **이 통합이 접근 가능한 모든 페이지**를
끝까지 긁고, 그 본문을 전부 `run_pipeline_batch()`로 LLM에 태워 카드로 저장했다.
노션은 부모 페이지를 공유하면 하위 트리 전체에 권한을 주기 때문에, 사용자가 의도하지
않은 문서까지 외부로 나갔다(사용자 신고, 9/18). 게다가 상한 50개는 정렬 보장 없이
앞에서부터 잘라서, **어떤 50개가 나갈지 예측할 수도 없었다.**

지금은 이렇게 동작한다:
  - `POST /api/notion/pages` — 제목과 수정 시각만. **본문도, LLM도, 저장도 없다.**
  - `POST /api/notion/pages/{id}/content` — 고른 **한 페이지**의 본문만. 역시 저장하지 않는다.

변환은 프론트가 그 본문을 입력창에 채운 뒤, 사용자가 [문장으로 바꾸기]를 눌러
기존 `POST /api/cards`를 타는 것으로 일어난다. 이 라우터는 카드를 만들지 않는다.

**토큰은 저장하지 않는다.** 요청마다 `user_token`을 받는다 — 서드파티 자격증명을
서버 DB에 평문으로 눕히지 않기 위해서다. 프론트가 세션 동안만 들고 있는다
(`web/lib/notionToken.ts`). `user_token`(노션 신원)과 `current_user`(이 앱의 로그인
유저)는 서로 다른 축이라 둘 다 필요하다.
"""
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from src.agent.notion_client import (
    NotionOAuthError,
    build_authorize_url,
    exchange_code_for_token,
    fetch_notion_page_content,
    list_notion_pages,
    oauth_enabled,
)
from src.api.rate_limit import limit_light
from src.api.schemas import (
    NotionConnectionResponse,
    NotionPageContentResponse,
    NotionPageListResponse,
    NotionPageRequest,
    NotionPageSummaryResponse,
)
from src.auth.deps import get_current_user
from src.config import settings
from src.storage import db

router = APIRouter(tags=["notion"])

_OAUTH_STATE_COOKIE = "notion_oauth_state"


def _resolve_token(user_id: int, user_token: str) -> str:
    """이 요청에 쓸 노션 토큰을 정한다 — **OAuth 연결이 있으면 그걸 우선한다.**

    두 경로를 같이 지원하는 이유: OAuth client_id 발급 전에도 앱이 굴러가야 하고,
    발급 뒤에는 사용자가 아무것도 안 해도 자동으로 더 안전한 경로로 넘어가야 한다.
      1. OAuth 연결(서버 보관 토큰) — 사용자가 인가 화면에서 **고른 페이지만** 보인다
      2. 없으면 요청이 실어 보낸 통합 토큰 — 그 통합에 공유된 것 **전부**가 보인다

    빈 문자열은 "값 없음"으로 거부한다. Pydantic의 `str`은 빈 문자열을 통과시키므로
    스키마만으로는 못 막고, 통과시키면 `notion_client`가 `settings.notion_token`
    (로컬 개발용 폴백)으로 넘어가 **개발자 본인의 노션이 열린다**
    (docs/03-risk-fallback.md 리스크 6).
    """
    connection = db.get_notion_connection(user_id)
    if connection:
        return connection.access_token

    token = user_token.strip()
    if not token:
        raise HTTPException(
            status_code=422, detail="노션 연결이 필요합니다. 먼저 연결해 주세요."
        )
    return token


@router.get("/notion/connection", response_model=NotionConnectionResponse)
def get_connection(current_user: db.User = Depends(get_current_user)) -> NotionConnectionResponse:
    """현재 연결 상태. **액세스 토큰은 절대 싣지 않는다** — 워크스페이스 이름만 준다.

    `oauth_available`이 false면 client_id가 아직 없다는 뜻이라, 프론트는 OAuth 버튼
    대신 통합 토큰 입력을 보여준다.
    """
    connection = db.get_notion_connection(current_user.id)
    return NotionConnectionResponse(
        connected=connection is not None,
        workspace_name=connection.workspace_name if connection else None,
        oauth_available=oauth_enabled(),
    )


@router.delete("/notion/connection", status_code=204)
def disconnect(current_user: db.User = Depends(get_current_user)) -> None:
    """연결 해제 — 보관 중인 액세스 토큰을 **지운다**. 없어도 204(멱등)."""
    db.delete_notion_connection(current_user.id)


@router.get("/notion/oauth/start")
def oauth_start(current_user: db.User = Depends(get_current_user)) -> RedirectResponse:
    """노션 인가 화면으로 보낸다 (Figma 3.0-a).

    그 화면에는 **노션이 그리는 페이지 선택기**가 있어서, 사용자가 거기서 고른 것만
    이 통합이 볼 수 있게 된다 — 통합 토큰 방식에서 "허용하지 않은 페이지까지 보이던"
    문제의 근본 해법이다.

    CSRF 방지용 state를 임시 쿠키에 저장해뒀다가 콜백에서 대조한다(카카오와 동일).
    """
    if not oauth_enabled():
        raise HTTPException(
            status_code=503, detail="노션 OAuth가 아직 설정되지 않았습니다."
        )

    state = secrets.token_urlsafe(16)
    response = RedirectResponse(url=build_authorize_url(state))
    response.set_cookie(
        _OAUTH_STATE_COOKIE,
        state,
        max_age=600,  # 10분 — 인가 화면에서 페이지를 고르는 시간까지 넉넉하게
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/notion/oauth/callback")
def oauth_callback(
    request: Request,
    code: str,
    state: str,
    current_user: db.User = Depends(get_current_user),
) -> RedirectResponse:
    """노션이 인가 코드와 함께 돌아오는 지점. 토큰으로 교환해 보관한다.

    `Depends(get_current_user)`가 붙어 있는 게 중요하다 — 이 콜백은 **이미 로그인한
    유저의 연결을 맺는 것**이라, 세션이 없으면 어느 유저에게 붙일지 알 수 없다.
    """
    saved_state = request.cookies.get(_OAUTH_STATE_COOKIE)
    if not saved_state or saved_state != state:
        raise HTTPException(
            status_code=400, detail="잘못된 연결 요청입니다(state 불일치). 다시 시도해 주세요."
        )

    try:
        result = exchange_code_for_token(code)
    except NotionOAuthError as e:
        raise HTTPException(status_code=502, detail=f"노션 연결에 실패했습니다: {e}") from e

    db.save_notion_connection(
        current_user.id,
        result.access_token,
        result.workspace_name,
        datetime.now(timezone.utc).isoformat(),
    )

    # 연결을 시작한 자리(기록 화면)로 돌려보낸다.
    response = RedirectResponse(url=f"{settings.frontend_base_url}/record?notion=connected")
    response.delete_cookie(_OAUTH_STATE_COOKIE, path="/")
    return response


@router.post("/notion/pages", response_model=NotionPageListResponse, dependencies=[Depends(limit_light)])
def list_pages(
    payload: NotionPageRequest, current_user: db.User = Depends(get_current_user)
) -> NotionPageListResponse:
    """고를 수 있는 페이지 목록 (Figma 3.0-b "최근 수정한 페이지 N건").

    **제목과 수정 시각만 돌려준다.** 본문을 읽지 않고, 카드를 만들지 않고, LLM을
    부르지 않는다 — 노션 내용이 밖으로 나가는 지점이 아니다.
    """
    token = _resolve_token(current_user.id, payload.user_token)
    try:
        pages = list_notion_pages(user_token=token)
    except ValueError as e:
        # 토큰 오류 (notion_client._raise_for_notion_error 참고)
        raise HTTPException(status_code=401, detail=str(e)) from e

    return NotionPageListResponse(
        pages=[NotionPageSummaryResponse.model_validate(p) for p in pages]
    )


@router.post(
    "/notion/pages/{page_id}/content",
    response_model=NotionPageContentResponse,
    dependencies=[Depends(limit_light)],
)
def get_page_content(
    page_id: str,
    payload: NotionPageRequest,
    current_user: db.User = Depends(get_current_user),
) -> NotionPageContentResponse:
    """**사용자가 고른 페이지 하나**의 본문 (Figma 3.0-b "선택한 페이지 본문이 입력창에 삽입됩니다").

    저장하지 않고 그대로 돌려준다. 프론트가 입력창에 채우고, 사용자가 읽고 고친 뒤
    [문장으로 바꾸기]를 눌러야 변환된다 — 무엇이 LLM으로 나가는지 사용자가 보고
    정하게 하는 게 이 구조의 요점이다.
    """
    token = _resolve_token(current_user.id, payload.user_token)
    try:
        entry = fetch_notion_page_content(page_id, user_token=token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    return NotionPageContentResponse(
        page_id=entry.page_id, title=entry.title, content=entry.content
    )
