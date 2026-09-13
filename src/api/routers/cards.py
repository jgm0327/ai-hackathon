"""POST/GET/DELETE /api/cards — CLAUDE.md 2.1: 매일 쓰는 경로, 가볍게 유지.

JD 매칭을 여기서 하지 않는다(run_pipeline이 이미 그렇게 되어 있음). 응답은
3~10초 걸릴 수 있으니 프론트는 스켈레톤을 띄운다(docs/05-api-contract.md 1장).
"""
from fastapi import APIRouter

from src.agent.pipeline import run_pipeline
from src.api.schemas import CardCreateRequest, CardListResponse, CardResponse
from src.storage import db

router = APIRouter(tags=["cards"])


def _find_card(card_id: int) -> db.Card | None:
    """list_cards()에 단건 조회가 없어 전체를 훑어 찾는다. 카드 수가 수천 건
    규모(CLAUDE.md 4장)라 이 비용은 무시할 만하다."""
    for card in db.list_cards():
        if card.id == card_id:
            return card
    return None


@router.post("/cards", response_model=CardResponse, status_code=201)
def create_card(payload: CardCreateRequest) -> CardResponse:
    result = run_pipeline(payload.raw_text)
    card = _find_card(result["card_id"])
    return CardResponse.model_validate(card)


@router.get("/cards", response_model=CardListResponse)
def list_cards_endpoint(project_id: int | None = None) -> CardListResponse:
    # list_cards()는 내부 계약상 오래된 순(build_resume에 넘길 때 시간순이 필요)이라
    # API 계약(최신순)에 맞추기 위해 여기서만 뒤집는다.
    cards = list(reversed(db.list_cards(project_id)))
    return CardListResponse(cards=[CardResponse.model_validate(c) for c in cards])


@router.delete("/cards/{card_id}", status_code=204)
def delete_card_endpoint(card_id: int) -> None:
    db.delete_card(card_id)  # 존재하지 않아도 멱등하게 무시됨(db.delete_card 참고)
