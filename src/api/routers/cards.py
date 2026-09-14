"""POST/GET/PATCH/DELETE /api/cards — CLAUDE.md 2.1: 매일 쓰는 경로, 가볍게 유지.

JD 매칭을 여기서 하지 않는다(run_pipeline이 이미 그렇게 되어 있음). 응답은
3~10초 걸릴 수 있으니 프론트는 스켈레톤을 띄운다(docs/05-api-contract.md 1장).

**구현 노트 (9/14, 카카오 로그인 Phase B)**: 전 엔드포인트가 `Depends(get_current_user)`로
로그인 유저를 받아 그 id로 storage를 스코핑한다 — 다른 유저의 카드는 존재 자체가
안 보인다(db.get_card/delete_card가 user_id로 필터링).

**구현 노트 (9/14, 카테고리 직접 수정)**: PATCH는 `skill_tags`만 받는다 — 매일 쓰는
저장 경로(POST)는 여전히 LLM+캐노니컬라이제이션이 자동으로 태그를 뽑고, 사람이 손대는
건 저장 후 가끔(`/stack`에서)뿐이다. 2.1(매일 경로에 선택지 금지)을 지키는 설계.
"""
from fastapi import APIRouter, Depends, HTTPException

from src.agent.pipeline import run_pipeline
from src.api.schemas import CardCreateRequest, CardListResponse, CardResponse, CardTagsUpdateRequest
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


@router.patch("/cards/{card_id}", response_model=CardResponse)
def update_card_tags_endpoint(
    card_id: int,
    payload: CardTagsUpdateRequest,
    current_user: db.User = Depends(get_current_user),
) -> CardResponse:
    card = db.update_card_tags(current_user.id, card_id, payload.skill_tags)
    if card is None:
        raise HTTPException(status_code=404, detail="카드를 찾을 수 없습니다")
    return CardResponse.model_validate(card)
