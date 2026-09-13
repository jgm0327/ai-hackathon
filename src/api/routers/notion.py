"""POST /api/notion/sync — 노션 업무 일지를 가져와 한 번에 파싱하고 저장한다.

(P1, docs/05-api-contract.md 5장). `user_token`은 필수다 — `settings.notion_token`
(로컬 개발용 폴백)에 암묵적으로 의존하면 다른 사용자가 개발자 본인 노션 데이터를
끌어오는 사고로 이어진다(docs/03-risk-fallback.md 리스크 6, notion_client.py 모듈
docstring 참고). 빈 문자열도 "값 없음"으로 취급해 거부한다 — Pydantic의 `str` 타입은
빈 문자열도 통과시키므로 이 검증은 스키마만으로는 못 막는다.
"""
from fastapi import APIRouter, HTTPException

from src.agent.notion_client import fetch_notion_entries
from src.agent.pipeline import run_pipeline_batch
from src.api.schemas import CardResponse, NotionSyncRequest, NotionSyncResponse
from src.storage import db

router = APIRouter(tags=["notion"])


@router.post("/notion/sync", response_model=NotionSyncResponse)
def sync_notion(payload: NotionSyncRequest) -> NotionSyncResponse:
    if not payload.user_token.strip():
        raise HTTPException(status_code=422, detail="user_token은 필수입니다.")

    try:
        entries = fetch_notion_entries(user_token=payload.user_token)
    except ValueError as e:
        # 토큰이 없거나 유효하지 않음 (notion_client._raise_for_notion_error 참고)
        raise HTTPException(status_code=401, detail=str(e)) from e

    # 내용이 빈 페이지는 parse_note()에 넘길 근거가 없으니 건너뛴다.
    contents = [entry.content for entry in entries if entry.content.strip()]
    results = run_pipeline_batch(contents)
    cards = [db.get_card(r["card_id"]) for r in results]

    return NotionSyncResponse(
        imported=len(cards),
        cards=[CardResponse.model_validate(c) for c in cards],
    )
