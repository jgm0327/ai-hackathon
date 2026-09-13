"""POST /api/resume ★ 핵심 — CLAUDE.md 6장 P0 2순위, 이직 준비 경로(무겁게).

build_career_doc()가 list_cards() + build_resume()을 오케스트레이션한다.
result가 빈 문자열일 수 있는 것은 의도된 동작이다(CLAUDE.md 2.2, 환각 금지) —
여기서 되메우지 않는다.
"""
from fastapi import APIRouter

from src.agent.pipeline import build_career_doc
from src.api.schemas import ResumeRequest, ResumeResponse, StarItemResponse

router = APIRouter(tags=["resume"])


@router.post("/resume", response_model=ResumeResponse)
def create_resume(payload: ResumeRequest) -> ResumeResponse:
    items = build_career_doc(payload.project_id, jd_text=payload.jd_text)
    return ResumeResponse(items=[StarItemResponse.model_validate(item) for item in items])
