"""GET/POST/PATCH /api/projects — CLAUDE.md 3장: 프로젝트는 사람이 만든다.

폴더 이동/병합/중첩 같은 CRUD 고도화는 하지 않는다(CLAUDE.md 2.4). PATCH는
계약 문서(docs/05-api-contract.md 2장)가 보여주는 name/ended_at/is_current
3개 필드만 받는다.

**구현 노트 (9/14, 카카오 로그인 Phase B)**: 전 엔드포인트가 로그인 유저로 스코핑된다.
"""
from fastapi import APIRouter, Depends, HTTPException

from src.api.schemas import (
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectPatchRequest,
    ProjectResponse,
)
from src.auth.deps import get_current_user
from src.storage import db

router = APIRouter(tags=["projects"])


def _find_project(user_id: int, project_id: int) -> db.Project | None:
    for project in db.list_projects(user_id):
        if project.id == project_id:
            return project
    return None


@router.get("/projects", response_model=ProjectListResponse)
def list_projects_endpoint(current_user: db.User = Depends(get_current_user)) -> ProjectListResponse:
    return ProjectListResponse(
        projects=[ProjectResponse.model_validate(p) for p in db.list_projects(current_user.id)]
    )


@router.post("/projects", response_model=ProjectResponse, status_code=201)
def create_project_endpoint(
    payload: ProjectCreateRequest, current_user: db.User = Depends(get_current_user)
) -> ProjectResponse:
    project_id = db.create_project(current_user.id, payload.name, payload.started_at)
    return ProjectResponse.model_validate(_find_project(current_user.id, project_id))


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
def patch_project_endpoint(
    project_id: int,
    payload: ProjectPatchRequest,
    current_user: db.User = Depends(get_current_user),
) -> ProjectResponse:
    if _find_project(current_user.id, project_id) is None:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    fields = payload.model_dump(exclude_unset=True)
    if fields:
        db.update_project(current_user.id, project_id, **fields)

    return ProjectResponse.model_validate(_find_project(current_user.id, project_id))
