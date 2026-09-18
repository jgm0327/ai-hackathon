"""Track B 담당: GET /api/backup, POST /api/backup/import 테스트 (9/18 신규).

Figma "5.0 설정"의 백업 내보내기/불러오기(41:333 / 41:338). 이 경로의 핵심 성질 두 개를
집중적으로 본다:

1. **불러오기가 LLM을 타지 않는다** — 백업에 저장된 정리 문장/태그가 그대로 되살아나야
   한다. 여기서 parse_note()가 불리면 문장이 바뀌고 비용도 든다.
2. **불러오기가 기존 데이터를 지우지 않는다** — 덧붙이기만 한다(src/api/routers/backup.py).
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.parsing.parser import ParsedEntry
from src.storage import db


@pytest.fixture
def client():
    return TestClient(app)


def _seed(user_id: int) -> int:
    project_id = db.create_project(user_id, "A은행 차세대", "2023-02-01")
    db.save_card(
        user_id,
        project_id,
        ParsedEntry(
            raw_text="레디스 캐시 붙임",
            refined_sentence="결제 API 응답 지연을 해소하기 위해 Redis 캐싱 레이어를 도입함",
            skill_tags=["Redis", "성능최적화"],
            confidence=0.9,
        ),
        "2023-02-14",
        "18:45",
    )
    db.save_card(
        user_id,
        None,  # 미분류
        ParsedEntry(
            raw_text="회고 정리",
            refined_sentence="스프린트 회고를 정리함",
            skill_tags=[],
            confidence=0.5,
        ),
        "2023-02-20",
    )
    return project_id


def test_export_returns_projects_and_cards(client, current_user_id):
    _seed(current_user_id)

    response = client.get("/api/backup")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 1
    assert [p["name"] for p in body["projects"]] == ["A은행 차세대"]
    assert len(body["cards"]) == 2
    card = next(c for c in body["cards"] if c["raw_text"] == "레디스 캐시 붙임")
    assert card["skill_tags"] == ["Redis", "성능최적화"]
    assert card["created_time"] == "18:45"


def test_export_does_not_leak_other_users_data(client, current_user_id):
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    _seed(other_user_id)

    body = client.get("/api/backup").json()

    assert body["projects"] == []
    assert body["cards"] == []


def test_import_restores_verbatim_without_calling_the_llm(client, current_user_id):
    """복원은 저장된 문장을 그대로 되살린다 — parse_note()가 불리면 안 된다."""
    _seed(current_user_id)
    exported = client.get("/api/backup").json()

    # 내보낸 걸 지운 뒤 다시 불러오는 상황을 흉내 내기 위해 새 유저로 복원한다.
    restore_user_id = db.upsert_user("restore-kakao-id", "복원", None, "2026-01-01T00:00:00")
    from src.auth.deps import get_current_user

    app.dependency_overrides[get_current_user] = lambda: db.get_user(restore_user_id)
    try:
        with patch("src.agent.pipeline.parse_note") as mock_parse:
            response = client.post(
                "/api/backup/import",
                json={"projects": exported["projects"], "cards": exported["cards"]},
            )
        assert mock_parse.call_count == 0
    finally:
        app.dependency_overrides[get_current_user] = lambda: db.get_user(current_user_id)

    assert response.status_code == 200
    assert response.json() == {"imported_projects": 1, "imported_cards": 2}

    restored = db.list_cards(restore_user_id)
    assert len(restored) == 2
    redis_card = next(c for c in restored if c.raw_text == "레디스 캐시 붙임")
    assert redis_card.refined_sentence == (
        "결제 API 응답 지연을 해소하기 위해 Redis 캐싱 레이어를 도입함"
    )
    assert redis_card.skill_tags == ["Redis", "성능최적화"]
    assert redis_card.created_at == "2023-02-14"
    # 프로젝트 소속도 따라와야 한다 — 백업의 옛 project_id가 새 id로 옮겨 붙는다.
    restored_project = db.list_projects(restore_user_id)[0]
    assert redis_card.project_id == restored_project.id
    # 미분류 카드는 미분류인 채로 들어온다(버리지 않는다).
    assert any(c.project_id is None for c in restored)


def test_import_is_additive_and_keeps_existing_records(client, current_user_id):
    """"복원"이 기존 기록을 지우면 되돌릴 방법이 없다 — 덧붙이기만 해야 한다."""
    _seed(current_user_id)
    before = len(db.list_cards(current_user_id))

    response = client.post(
        "/api/backup/import",
        json={
            "projects": [{"id": 99, "name": "B카드 정산", "started_at": "2024-01-01"}],
            "cards": [
                {
                    "id": 1,
                    "project_id": 99,
                    "raw_text": "정산 배치 개선",
                    "refined_sentence": "정산 배치 실행 시간을 단축함",
                    "skill_tags": ["배치"],
                    "confidence": 0.8,
                    "created_at": "2024-01-05",
                }
            ],
        },
    )

    assert response.status_code == 200
    assert len(db.list_cards(current_user_id)) == before + 1
    assert {p.name for p in db.list_projects(current_user_id)} == {"A은행 차세대", "B카드 정산"}


def test_import_does_not_change_the_current_project(client, current_user_id):
    """백업을 불러왔다고 지금 일하는 프로젝트가 바뀌면 안 된다 (CLAUDE.md 2.1)."""
    project_id = _seed(current_user_id)
    db.set_current_project(current_user_id, project_id)

    client.post(
        "/api/backup/import",
        json={"projects": [{"id": 99, "name": "B카드 정산", "started_at": "2024-01-01"}], "cards": []},
    )

    current = db.get_current_project(current_user_id)
    assert current is not None and current.id == project_id


def test_import_keeps_cards_whose_project_is_missing_from_the_file(client, current_user_id):
    """대응표에 없는 project_id를 가진 카드는 버리지 않고 미분류로 넣는다."""
    response = client.post(
        "/api/backup/import",
        json={
            "projects": [],
            "cards": [
                {
                    "id": 1,
                    "project_id": 12345,
                    "raw_text": "고아 카드",
                    "refined_sentence": "고아 카드",
                    "skill_tags": [],
                    "confidence": 0.0,
                    "created_at": "2024-01-05",
                }
            ],
        },
    )

    assert response.status_code == 200
    cards = db.list_cards(current_user_id)
    assert len(cards) == 1
    assert cards[0].project_id is None


def test_backup_requires_login(client):
    assert client.get("/api/backup").status_code == 401
    assert client.post("/api/backup/import", json={"projects": [], "cards": []}).status_code == 401
