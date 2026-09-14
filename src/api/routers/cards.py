"""POST/GET/DELETE /api/cards — CLAUDE.md 2.1: 매일 쓰는 경로, 가볍게 유지.

JD 매칭을 여기서 하지 않는다(run_pipeline이 이미 그렇게 되어 있음). 응답은
3~10초 걸릴 수 있으니 프론트는 스켈레톤을 띄운다(docs/05-api-contract.md 1장).

**구현 노트 (9/14, 카카오 로그인 Phase B)**: 전 엔드포인트가 `Depends(get_current_user)`로
로그인 유저를 받아 그 id로 storage를 스코핑한다 — 다른 유저의 카드는 존재 자체가
안 보인다(db.get_card/delete_card가 user_id로 필터링).
"""
from fastapi import APIRouter, Depends

from src.agent.pipeline import run_pipeline
from src.api.schemas import CardCreateRequest, CardListResponse, CardResponse
from src.auth.deps import get_current_user
from src.storage import db

router = APIRouter(tags=["cards"])


@router.post("/cards", response_model=CardResponse, status_code=201)
def create_card(
    payload: CardCreateRequest, current_user: db.User = Depends(get_current_user)
) -> CardResponse:
    result = run_pipeline(current_user.id, payload.raw_text)
    card = db.get_card(current_user.id, result["card_id"])
    return CardResponse.model_validate(card)


@router.get("/cards", response_model=CardListResponse)
def list_cards_endpoint(
    project_id: int | None = None, current_user: db.User = Depends(get_current_user)
) -> CardListResponse:
    # list_cards()는 내부 계약상 오래된 순(build_resume에 넘길 때 시간순이 필요)이라
    # API 계약(최신순)에 맞추기 위해 여기서만 뒤집는다.
    cards = list(reversed(db.list_cards(current_user.id, project_id)))
    return CardListResponse(cards=[CardResponse.model_validate(c) for c in cards])


@router.delete("/cards/{card_id}", status_code=204)
def delete_card_endpoint(card_id: int, current_user: db.User = Depends(get_current_user)) -> None:
    db.delete_card(current_user.id, card_id)  # 다른 유저 소유이거나 없어도 멱등하게 무시됨
