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
from fastapi import APIRouter, Depends, HTTPException

from src.agent.notion_client import fetch_notion_page_content, list_notion_pages
from src.api.rate_limit import limit_light
from src.api.schemas import (
    NotionPageContentResponse,
    NotionPageListResponse,
    NotionPageRequest,
    NotionPageSummaryResponse,
)
from src.auth.deps import get_current_user
from src.storage import db

router = APIRouter(tags=["notion"])


def _require_token(user_token: str) -> str:
    """빈 문자열도 "값 없음"으로 거부한다.

    Pydantic의 `str`은 빈 문자열을 통과시키므로 스키마만으로는 못 막는다. 토큰이
    없으면 `notion_client`가 `settings.notion_token`(로컬 개발용 폴백)으로 넘어가는데,
    그러면 **다른 사용자가 개발자 본인의 노션 데이터를 끌어오는** 사고가 된다
    (docs/03-risk-fallback.md 리스크 6).
    """
    token = user_token.strip()
    if not token:
        raise HTTPException(status_code=422, detail="user_token은 필수입니다.")
    return token


@router.post("/notion/pages", response_model=NotionPageListResponse, dependencies=[Depends(limit_light)])
def list_pages(
    payload: NotionPageRequest, current_user: db.User = Depends(get_current_user)
) -> NotionPageListResponse:
    """고를 수 있는 페이지 목록 (Figma 3.0-b "최근 수정한 페이지 N건").

    **제목과 수정 시각만 돌려준다.** 본문을 읽지 않고, 카드를 만들지 않고, LLM을
    부르지 않는다 — 노션 내용이 밖으로 나가는 지점이 아니다.
    """
    token = _require_token(payload.user_token)
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
    token = _require_token(payload.user_token)
    try:
        entry = fetch_notion_page_content(page_id, user_token=token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    return NotionPageContentResponse(
        page_id=entry.page_id, title=entry.title, content=entry.content
    )
