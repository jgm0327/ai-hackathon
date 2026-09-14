"""POST /api/resume ★ 핵심 — CLAUDE.md 6장 P0 2순위, 이직 준비 경로(무겁게).

build_career_doc()가 list_cards() + build_resume()을 오케스트레이션한다.
result가 빈 문자열일 수 있는 것은 의도된 동작이다(CLAUDE.md 2.2, 환각 금지) —
여기서 되메우지 않는다.

**구현 노트 (9/14, 카카오 로그인 Phase B)**: `project_id`가 로그인 유저 소유가 아니면
`list_cards()`가 빈 목록을 반환하므로(다른 유저 카드가 안 보임) 자연히 빈 STAR
목록이 나온다 — 별도로 소유권을 검증하지 않아도 데이터가 새지 않는다.
"""
from fastapi import APIRouter, Depends

from src.agent.pipeline import build_career_doc
from src.api.schemas import ResumeRequest, ResumeResponse, StarItemResponse
from src.auth.deps import get_current_user
from src.storage import db

router = APIRouter(tags=["resume"])


@router.post("/resume", response_model=ResumeResponse)
def create_resume(
    payload: ResumeRequest, current_user: db.User = Depends(get_current_user)
) -> ResumeResponse:
    items = build_career_doc(current_user.id, payload.project_id, jd_text=payload.jd_text)
    return ResumeResponse(items=[StarItemResponse.model_validate(item) for item in items])
