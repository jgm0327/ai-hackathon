"""POST /api/resume ★ 핵심 — CLAUDE.md 6장 P0 2순위, 이직 준비 경로(무겁게).

build_career_doc()가 list_cards() + build_resume()을 오케스트레이션한다.
result가 빈 문자열일 수 있는 것은 의도된 동작이다(CLAUDE.md 2.2, 환각 금지) —
여기서 되메우지 않는다.

**구현 노트 (9/14, 카카오 로그인 Phase B)**: `project_id`가 로그인 유저 소유가 아니면
`list_cards()`가 빈 목록을 반환하므로(다른 유저 카드가 안 보임) 자연히 빈 STAR
목록이 나온다 — 별도로 소유권을 검증하지 않아도 데이터가 새지 않는다.

**구현 노트 (9/14, 경력기술서 초안 저장)**: 아래 GET/PUT /resume/draft는 위
POST /resume(AI 생성)과 별개다 — AI가 만든 STAR 구조 자체는 여전히 저장하지
않고(CLAUDE.md 3장), 유저가 그 결과를 가져다 직접 고친 자유 텍스트만 저장한다
(src/storage/db.py의 ResumeDraft 참고).
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from src.agent.pipeline import build_career_doc, enhance_existing_resume, get_jd_requirements
from src.api.schemas import (
    EnhancedItemResponse,
    JdRequirementResponse,
    JdRequirementsRequest,
    JdRequirementsResponse,
    ResumeDraftResponse,
    ResumeDraftSaveRequest,
    ResumeEnhanceRequest,
    ResumeEnhanceResponse,
    ResumeRequest,
    ResumeResponse,
    StarApplyAnswersRequest,
    StarApplyAnswersResponse,
    StarItemResponse,
    StarQuestionsRequest,
    StarQuestionsResponse,
)
from src.auth.deps import get_current_user
from src.parsing.resume import StarItem, apply_star_answers, generate_star_questions
from src.storage import db

router = APIRouter(tags=["resume"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/resume", response_model=ResumeResponse)
def create_resume(
    payload: ResumeRequest, current_user: db.User = Depends(get_current_user)
) -> ResumeResponse:
    items = build_career_doc(current_user.id, payload.project_id, jd_text=payload.jd_text)
    return ResumeResponse(items=[StarItemResponse.model_validate(item) for item in items])


@router.post("/resume/enhance", response_model=ResumeEnhanceResponse)
def enhance_resume_endpoint(
    payload: ResumeEnhanceRequest, current_user: db.User = Depends(get_current_user)
) -> ResumeEnhanceResponse:
    items = enhance_existing_resume(current_user.id, payload.project_id, payload.existing_items)
    return ResumeEnhanceResponse(items=[EnhancedItemResponse.model_validate(item) for item in items])


@router.post("/resume/jd-requirements", response_model=JdRequirementsResponse)
def jd_requirements_endpoint(
    payload: JdRequirementsRequest, current_user: db.User = Depends(get_current_user)
) -> JdRequirementsResponse:
    result = get_jd_requirements(current_user.id, payload.project_id, payload.jd_text)
    return JdRequirementsResponse(
        job_title=result.job_title,
        company=result.company,
        years_label=result.years_label,
        requirements=[JdRequirementResponse.model_validate(r) for r in result.requirements],
    )


@router.post("/resume/star-questions", response_model=StarQuestionsResponse)
def star_questions_endpoint(
    payload: StarQuestionsRequest, current_user: db.User = Depends(get_current_user)
) -> StarQuestionsResponse:
    item = StarItem(**payload.item.model_dump())
    return StarQuestionsResponse(questions=generate_star_questions(item))


@router.post("/resume/star-apply-answers", response_model=StarApplyAnswersResponse)
def star_apply_answers_endpoint(
    payload: StarApplyAnswersRequest, current_user: db.User = Depends(get_current_user)
) -> StarApplyAnswersResponse:
    item = StarItem(**payload.item.model_dump())
    qa_pairs = [(a.question, a.answer) for a in payload.answers]
    result = apply_star_answers(item, qa_pairs)
    return StarApplyAnswersResponse(
        updated_item=StarItemResponse.model_validate(result.updated_item),
        changed_field=result.changed_field,
    )


@router.get("/resume/draft", response_model=ResumeDraftResponse)
def get_resume_draft_endpoint(
    project_id: int, current_user: db.User = Depends(get_current_user)
) -> ResumeDraftResponse:
    draft = db.get_resume_draft(current_user.id, project_id)
    if draft is None:
        return ResumeDraftResponse(project_id=project_id, content=None, updated_at=None)
    return ResumeDraftResponse.model_validate(draft, from_attributes=True)


@router.put("/resume/draft", response_model=ResumeDraftResponse)
def save_resume_draft_endpoint(
    payload: ResumeDraftSaveRequest, current_user: db.User = Depends(get_current_user)
) -> ResumeDraftResponse:
    draft = db.save_resume_draft(current_user.id, payload.project_id, payload.content, _now_iso())
    if draft is None:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
    return ResumeDraftResponse.model_validate(draft, from_attributes=True)
