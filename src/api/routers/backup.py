"""GET /api/backup, POST /api/backup/import — Figma "5.0 설정"의 백업 내보내기/불러오기
(41:333 / 41:338, 9/18 신규).

**왜 서버에 두는가**: 내보내기는 프론트가 `GET /projects` + `GET /cards`로 조립할 수도
있지만, 불러오기는 그럴 수 없다. `POST /api/cards`는 원문을 LLM에 태워 새로 정리하는
경로라, 백업 복원에 쓰면 (1) 백업에 들어있던 정리 문장/태그가 다른 문장으로 바뀌고
(2) 카드 수만큼 LLM 비용이 발생한다. 복원은 **LLM을 전혀 타지 않고 저장된 값을 그대로
되살려야** 하므로 전용 엔드포인트가 필요하다.

**불러오기는 덧붙이기(additive)다 — 기존 데이터를 지우지 않는다.** "복원"이라는 말
때문에 기존 기록이 날아갈 거라 오해하기 쉬운데, 그런 파괴적 동작은 되돌릴 방법이
없어서 일부러 넣지 않았다. 같은 파일을 두 번 불러오면 카드가 두 벌 생긴다.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from src.api.schemas import (
    BackupCard,
    BackupImportRequest,
    BackupImportResponse,
    BackupProject,
    BackupResponse,
)
from src.auth.deps import get_current_user
from src.parsing.parser import ParsedEntry
from src.storage import db

router = APIRouter(tags=["backup"])

# 파일 포맷 버전. 나중에 모양이 바뀌면 여기를 올리고 불러오기에서 분기한다.
BACKUP_VERSION = 1


@router.get("/backup", response_model=BackupResponse)
def export_backup(current_user: db.User = Depends(get_current_user)) -> BackupResponse:
    """이 유저의 프로젝트와 카드 전부를 그대로 담은 JSON을 돌려준다."""
    projects = db.list_projects(current_user.id)
    cards = db.list_cards(current_user.id)
    return BackupResponse(
        version=BACKUP_VERSION,
        exported_at=datetime.now(timezone.utc).isoformat(),
        projects=[BackupProject.model_validate(p) for p in projects],
        cards=[BackupCard.model_validate(c) for c in cards],
    )


@router.post("/backup/import", response_model=BackupImportResponse)
def import_backup(
    payload: BackupImportRequest, current_user: db.User = Depends(get_current_user)
) -> BackupImportResponse:
    """백업 JSON의 프로젝트/카드를 **덧붙인다**. 기존 기록은 하나도 건드리지 않는다.

    백업 안의 `project_id`는 이 DB에서 그대로 쓸 수 없다(다른 기기에서 만든 id라
    이미 다른 프로젝트가 쓰고 있을 수 있다). 그래서 프로젝트를 먼저 새로 만들고
    옛 id → 새 id 대응표를 만든 뒤, 카드를 그 표로 옮겨 붙인다. 대응표에 없는
    project_id를 가진 카드는 미분류로 들어간다 — 버리지 않는다.
    """
    # db.create_project()는 만든 프로젝트를 자동으로 현재 프로젝트로 지정한다.
    # 백업을 불러왔다고 유저가 지금 일하는 프로젝트가 바뀌면 곤란하므로, 원래
    # 현재 프로젝트를 기억해뒀다가 끝에서 되돌린다.
    previous_current = db.get_current_project(current_user.id)

    id_map: dict[int, int] = {}
    for project in payload.projects:
        new_id = db.create_project(current_user.id, project.name, project.started_at)
        if project.ended_at is not None:
            db.update_project(current_user.id, new_id, ended_at=project.ended_at)
        id_map[project.id] = new_id

    imported_cards = 0
    for card in payload.cards:
        project_id = id_map.get(card.project_id) if card.project_id is not None else None
        parsed = ParsedEntry(
            raw_text=card.raw_text,
            refined_sentence=card.refined_sentence,
            skill_tags=list(card.skill_tags),
            confidence=card.confidence,
        )
        db.save_card(current_user.id, project_id, parsed, card.created_at, card.created_time)
        imported_cards += 1

    if previous_current is not None:
        db.set_current_project(current_user.id, previous_current.id)

    return BackupImportResponse(
        imported_projects=len(id_map),
        imported_cards=imported_cards,
    )
