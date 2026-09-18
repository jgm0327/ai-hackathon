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

from fastapi import APIRouter, Depends, HTTPException, Response

from src.agent.pipeline import build_career_doc, enhance_existing_resume, get_jd_requirements
from src.api.schemas import (
    EnhancedItemResponse,
    JdRequirementResponse,
    JdRequirementsRequest,
    JdRequirementsResponse,
    ResumeDraftCountResponse,
    ResumeDraftResponse,
    SavedResumeCreateRequest,
    SavedResumeDetailResponse,
    SavedResumeListResponse,
    SavedResumeResponse,
    ResumeDraftSaveRequest,
    ResumeEnhanceRequest,
    ResumeEnhanceResponse,
    ResumeExportRequest,
    ResumeRequest,
    ResumeResponse,
    StarApplyAnswersRequest,
    StarApplyAnswersResponse,
    StarItemResponse,
    StarQuestionsRequest,
    StarQuestionsResponse,
)
from src.api.rate_limit import limit_heavy
from src.auth.deps import get_current_user
from src.export.docx_export import markdown_to_docx_bytes
from src.parsing.resume import StarItem, apply_star_answers, generate_star_questions
from src.storage import db

router = APIRouter(tags=["resume"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/resume", response_model=ResumeResponse, dependencies=[Depends(limit_heavy)])
def create_resume(
    payload: ResumeRequest, current_user: db.User = Depends(get_current_user)
) -> ResumeResponse:
    items = build_career_doc(
        current_user.id,
        payload.project_id,
        jd_text=payload.jd_text,
        project_ids=payload.project_ids,
        include_unassigned=payload.include_unassigned,
        skill_tag=payload.skill_tag,
    )
    return ResumeResponse(items=[StarItemResponse.model_validate(item) for item in items])


@router.get("/resume/draft-count", response_model=ResumeDraftCountResponse)
def resume_draft_count(current_user: db.User = Depends(get_current_user)) -> ResumeDraftCountResponse:
    """저장본 개수 (9/18 신규, Figma 4.1-h "내 경력기술서  3개").

    화면에 띄울 숫자를 짐작하지 않기 위해 있는 엔드포인트다(CLAUDE.md 2.2).
    4.3 목록이 세는 것과 같은 값이어야 해서 `saved_resumes`를 센다.
    """
    return ResumeDraftCountResponse(count=len(db.list_saved_resumes(current_user.id)))


@router.get("/resume/saved", response_model=SavedResumeListResponse)
def list_saved_resumes_endpoint(
    current_user: db.User = Depends(get_current_user),
) -> SavedResumeListResponse:
    """"4.3 내 경력기술서 (저장본)" 목록 (9/18 신규).

    본문(`content`)은 싣지 않는다 — 저장본이 여럿이면 목록 응답이 통째로 무거워진다.
    본문이 필요하면 `GET /api/resume/saved/{id}`로 하나만 받는다.
    """
    saved = db.list_saved_resumes(current_user.id)
    return SavedResumeListResponse(resumes=[SavedResumeResponse.model_validate(r) for r in saved])


@router.post("/resume/saved", response_model=SavedResumeDetailResponse, status_code=201)
def create_saved_resume_endpoint(
    payload: SavedResumeCreateRequest, current_user: db.User = Depends(get_current_user)
) -> SavedResumeDetailResponse:
    """빌더에서 만든 경력기술서를 이름 붙여 보관한다 (9/18 신규).

    `resume_drafts`(작업 중 초안, 프로젝트당 1개 덮어쓰기)와 **별개**다 — 저장본은
    여러 개 남길 수 있고 지우기 전엔 안 사라진다.
    """
    saved = db.create_saved_resume(
        current_user.id,
        payload.title.strip(),
        payload.content,
        payload.item_count,
        payload.card_count,
        payload.jd_based,
        _now_iso(),
    )
    return SavedResumeDetailResponse.model_validate(saved)


@router.get("/resume/saved/{saved_id}", response_model=SavedResumeDetailResponse)
def get_saved_resume_endpoint(
    saved_id: int, current_user: db.User = Depends(get_current_user)
) -> SavedResumeDetailResponse:
    saved = db.get_saved_resume(current_user.id, saved_id)
    if saved is None:
        raise HTTPException(status_code=404, detail="저장본을 찾을 수 없습니다")
    return SavedResumeDetailResponse.model_validate(saved)


@router.delete("/resume/saved/{saved_id}", status_code=204)
def delete_saved_resume_endpoint(
    saved_id: int, current_user: db.User = Depends(get_current_user)
) -> None:
    # 없거나 남의 것이어도 204 — 다른 삭제 엔드포인트와 같은 멱등 규칙이다.
    db.delete_saved_resume(current_user.id, saved_id)


@router.post("/resume/enhance", response_model=ResumeEnhanceResponse, dependencies=[Depends(limit_heavy)])
def enhance_resume_endpoint(
    payload: ResumeEnhanceRequest, current_user: db.User = Depends(get_current_user)
) -> ResumeEnhanceResponse:
    items = enhance_existing_resume(
        current_user.id,
        payload.project_id,
        payload.existing_items,
        project_ids=payload.project_ids,
        include_unassigned=payload.include_unassigned,
    )
    return ResumeEnhanceResponse(items=[EnhancedItemResponse.model_validate(item) for item in items])


@router.post("/resume/jd-requirements", response_model=JdRequirementsResponse, dependencies=[Depends(limit_heavy)])
def jd_requirements_endpoint(
    payload: JdRequirementsRequest, current_user: db.User = Depends(get_current_user)
) -> JdRequirementsResponse:
    result = get_jd_requirements(
        current_user.id,
        payload.project_id,
        payload.jd_text,
        project_ids=payload.project_ids,
        include_unassigned=payload.include_unassigned,
    )
    return JdRequirementsResponse(
        job_title=result.job_title,
        company=result.company,
        years_label=result.years_label,
        requirements=[JdRequirementResponse.model_validate(r) for r in result.requirements],
    )


@router.post("/resume/star-questions", response_model=StarQuestionsResponse, dependencies=[Depends(limit_heavy)])
def star_questions_endpoint(
    payload: StarQuestionsRequest, current_user: db.User = Depends(get_current_user)
) -> StarQuestionsResponse:
    item = StarItem(**payload.item.model_dump())
    return StarQuestionsResponse(questions=generate_star_questions(item))


@router.post("/resume/star-apply-answers", response_model=StarApplyAnswersResponse, dependencies=[Depends(limit_heavy)])
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


@router.post("/resume/export/docx")
def export_resume_docx(
    payload: ResumeExportRequest, current_user: db.User = Depends(get_current_user)
) -> Response:
    """경력기술서를 Word(.docx)로 내보낸다 (9/16 신규 — 그동안 프론트에서 "준비 중"으로
    막혀 있던 스텁을 구현). `content`는 프론트가 이미 "마크다운 복사"에 쓰는 텍스트와
    동일하다 — 여기서 STAR 구조를 다시 조합하지 않는다."""
    docx_bytes = markdown_to_docx_bytes(payload.content)
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="resume.docx"'},
    )


@router.get("/resume/draft", response_model=ResumeDraftResponse)
def get_resume_draft_endpoint(
    project_id: int | None = None, current_user: db.User = Depends(get_current_user)
) -> ResumeDraftResponse:
    """`project_id`를 생략하면 마스터 초안(여러 프로젝트를 한 문서로)을 조회한다 (9/18)."""
    if project_id is None:
        master = db.get_master_resume_draft(current_user.id)
        if master is None:
            return ResumeDraftResponse(project_id=None, content=None, updated_at=None)
        return ResumeDraftResponse(
            project_id=None, content=master.content, updated_at=master.updated_at
        )
    draft = db.get_resume_draft(current_user.id, project_id)
    if draft is None:
        return ResumeDraftResponse(project_id=project_id, content=None, updated_at=None)
    return ResumeDraftResponse.model_validate(draft, from_attributes=True)


@router.put("/resume/draft", response_model=ResumeDraftResponse)
def save_resume_draft_endpoint(
    payload: ResumeDraftSaveRequest, current_user: db.User = Depends(get_current_user)
) -> ResumeDraftResponse:
    if payload.project_id is None:
        master = db.save_master_resume_draft(current_user.id, payload.content, _now_iso())
        return ResumeDraftResponse(
            project_id=None, content=master.content, updated_at=master.updated_at
        )
    draft = db.save_resume_draft(current_user.id, payload.project_id, payload.content, _now_iso())
    if draft is None:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
    return ResumeDraftResponse.model_validate(draft, from_attributes=True)
