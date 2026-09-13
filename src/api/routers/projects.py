"""GET/POST/PATCH /api/projects — CLAUDE.md 3장: 프로젝트는 사람이 만든다.

폴더 이동/병합/중첩 같은 CRUD 고도화는 하지 않는다(CLAUDE.md 2.4). PATCH는
계약 문서(docs/05-api-contract.md 2장)가 보여주는 name/ended_at/is_current
3개 필드만 받는다.
"""
from fastapi import APIRouter, HTTPException

from src.api.schemas import (
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectPatchRequest,
    ProjectResponse,
)
from src.storage import db

router = APIRouter(tags=["projects"])


def _find_project(project_id: int) -> db.Project | None:
    for project in db.list_projects():
        if project.id == project_id:
            return project
    return None


@router.get("/projects", response_model=ProjectListResponse)
def list_projects_endpoint() -> ProjectListResponse:
    return ProjectListResponse(
        projects=[ProjectResponse.model_validate(p) for p in db.list_projects()]
    )


@router.post("/projects", response_model=ProjectResponse, status_code=201)
def create_project_endpoint(payload: ProjectCreateRequest) -> ProjectResponse:
    project_id = db.create_project(payload.name, payload.started_at)
    return ProjectResponse.model_validate(_find_project(project_id))


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
def patch_project_endpoint(project_id: int, payload: ProjectPatchRequest) -> ProjectResponse:
    if _find_project(project_id) is None:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    fields = payload.model_dump(exclude_unset=True)
    if fields:
        db.update_project(project_id, **fields)

    return ProjectResponse.model_validate(_find_project(project_id))
