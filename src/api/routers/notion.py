"""POST /api/notion/sync — 노션 업무 일지를 가져와 한 번에 파싱하고 저장한다.

(P1, docs/05-api-contract.md 5장). `user_token`은 필수다 — `settings.notion_token`
(로컬 개발용 폴백)에 암묵적으로 의존하면 다른 사용자가 개발자 본인 노션 데이터를
끌어오는 사고로 이어진다(docs/03-risk-fallback.md 리스크 6, notion_client.py 모듈
docstring 참고). 빈 문자열도 "값 없음"으로 취급해 거부한다 — Pydantic의 `str` 타입은
빈 문자열도 통과시키므로 이 검증은 스키마만으로는 못 막는다.

투트랙(docs/03-risk-fallback.md 리스크 1과 별개, notion_client.py 모듈 docstring 참고):
`NOTION_MCP_SERVER_URL`이 설정돼 있으면 먼저 MCP 경로를 시도하고, 실패하면 조용히
REST로 폴백한다 — 어느 경로든 이 라우터의 응답 스키마는 동일하다.

**구현 노트 (9/14, 카카오 로그인 Phase B)**: 노션에서 가져온 카드도 가져온 로그인
유저 소유가 된다 — `user_token`(노션 쪽 신원)과 `current_user`(이 앱의 로그인 유저)는
서로 다른 축이라 둘 다 필요하다.
"""
from fastapi import APIRouter, Depends, HTTPException

from src.agent.notion_client import fetch_notion_entries, fetch_notion_entries_via_mcp
from src.agent.pipeline import run_pipeline_batch
from src.api.schemas import CardResponse, NotionSyncRequest, NotionSyncResponse
from src.api.rate_limit import limit_batch
from src.auth.deps import get_current_user
from src.config import settings
from src.storage import db

router = APIRouter(tags=["notion"])

# 한 요청에서 LLM으로 넘길 노션 페이지 수 상한 (9/17). 페이지당 parse_note() 1회라
# 이 값이 곧 "한 번 눌렀을 때 최대 LLM 호출 수"다.
MAX_NOTION_PAGES_PER_SYNC = 50


def _fetch_entries(user_token: str):
    """MCP가 설정돼 있으면 먼저 시도하고, 실패하면 REST로 폴백한다.

    MCP 쪽 실패는 서버 미가동/도구 이름 불일치 등 "이 서버 설정 문제"일 뿐 유저
    잘못이 아니므로 404/503으로 사용자에게 노출하지 않고 조용히 REST로 넘어간다.
    REST마저 실패하면(토큰 문제 등) 그 예외가 그대로 위로 전파된다.
    """
    if settings.notion_mcp_server_url:
        try:
            return fetch_notion_entries_via_mcp(user_token=user_token)
        except Exception:  # noqa: BLE001 — MCP 실패(서버 다운, 도구 이름 불일치 등)는 폴백 사유일 뿐
            pass
    return fetch_notion_entries(user_token=user_token)


@router.post("/notion/sync", response_model=NotionSyncResponse, dependencies=[Depends(limit_batch)])
def sync_notion(
    payload: NotionSyncRequest, current_user: db.User = Depends(get_current_user)
) -> NotionSyncResponse:
    if not payload.user_token.strip():
        raise HTTPException(status_code=422, detail="user_token은 필수입니다.")

    try:
        entries = _fetch_entries(payload.user_token)
    except ValueError as e:
        # REST 경로의 토큰 오류 (notion_client._raise_for_notion_error 참고)
        raise HTTPException(status_code=401, detail=str(e)) from e

    # 내용이 빈 페이지는 parse_note()에 넘길 근거가 없으니 건너뛴다.
    contents = [entry.content for entry in entries if entry.content.strip()]

    # 한 번에 처리할 페이지 수 상한 (9/17 신규). 페이지 하나당 parse_note()가 LLM을
    # 한 번씩 부르므로, 상한이 없으면 노션 워크스페이스가 큰 유저 한 명이 한 요청으로
    # 수백 회 호출을 발생시킨다(비용도 문제지만 요청이 수 분씩 걸려 서버도 붙잡힌다).
    # 넘치면 거절하지 않고 앞에서부터 잘라 처리한 뒤, 몇 개를 못 가져왔는지 알려준다 —
    # 다시 누르면 이어서 가져갈 수 있다.
    skipped = max(0, len(contents) - MAX_NOTION_PAGES_PER_SYNC)
    contents = contents[:MAX_NOTION_PAGES_PER_SYNC]

    results = run_pipeline_batch(current_user.id, contents)
    cards = [db.get_card(current_user.id, r["card_id"]) for r in results]

    return NotionSyncResponse(
        imported=len(cards),
        skipped=skipped,
        cards=[CardResponse.model_validate(c) for c in cards],
    )
