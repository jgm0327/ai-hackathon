"""GET /api/jds/match — 카드의 스킬 태그로 유사 JD를 찾는다 (P1, docs/05-api-contract.md 4장).

이직 준비 시점에만 필요한 무거운 경로다. 9/13 파이프라인 개편으로 일상 경로
(`run_pipeline`)는 더 이상 벡터 인덱스에 의존하지 않으므로, 그 원칙을 여기서도
지킨다: 인덱스는 이 라우터가 최초로 호출될 때 지연 구축하고, 그 뒤로는 프로세스가
살아있는 동안 재사용한다(build_jd_index()는 upsert라 다시 불러도 안전하지만
매번 임베딩을 다시 계산하는 건 낭비라 플래그로 한 번만 하게 한다).
"""
from fastapi import APIRouter, HTTPException

from src.agent import vectorstore
from src.api.schemas import JDMatchResponse
from src.storage import db

router = APIRouter(tags=["jds"])

_index_ready = False


def _ensure_index() -> None:
    global _index_ready
    if not _index_ready:
        vectorstore.build_jd_index()
        _index_ready = True


@router.get("/jds/match", response_model=JDMatchResponse)
def match_jds(card_id: int, top_k: int = 5) -> JDMatchResponse:
    card = db.get_card(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="카드를 찾을 수 없습니다.")
    if not card.skill_tags:
        # 역량 태그가 없으면(모호한 입력 등) 매칭할 근거가 없다 — 빈 목록을 반환한다.
        return JDMatchResponse(matches=[])

    _ensure_index()
    matches = vectorstore.match_jds(card.skill_tags, top_k=top_k)
    return JDMatchResponse(matches=matches)
