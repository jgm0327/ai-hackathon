"""Track B 담당: GET/POST/PATCH /api/projects 테스트.

DB 격리와 로그인 유저 오버라이드는 tests/conftest.py가 담당한다(9/14 카카오 로그인 Phase B).
"""
from fastapi.testclient import TestClient
import pytest

from src.api.main import app
from src.storage import db


@pytest.fixture
def client():
    return TestClient(app)


def test_list_projects_requires_login(client):
    response = client.get("/api/projects")
    assert response.status_code == 401


def test_list_projects_empty(client, current_user_id):
    response = client.get("/api/projects")
    assert response.status_code == 200
    assert response.json() == {"projects": []}


def test_create_project_sets_current_true(client, current_user_id):
    response = client.post(
        "/api/projects", json={"name": "A은행 차세대", "started_at": "2023-02-01"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "A은행 차세대"
    assert body["started_at"] == "2023-02-01"
    assert body["ended_at"] is None
    assert body["is_current"] is True


def test_list_projects_returns_all(client, current_user_id):
    client.post("/api/projects", json={"name": "B카드 시스템", "started_at": "2022-05-01"})
    client.post("/api/projects", json={"name": "A은행 차세대", "started_at": "2023-02-01"})

    response = client.get("/api/projects")
    names = {p["name"] for p in response.json()["projects"]}
    assert names == {"B카드 시스템", "A은행 차세대"}


def test_list_projects_never_returns_another_users_projects(client, current_user_id):
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    db.create_project(other_user_id, "다른 유저 프로젝트", "2023-01-01")

    response = client.get("/api/projects")
    assert response.json() == {"projects": []}


def test_patch_project_renames(client, current_user_id):
    project_id = db.create_project(current_user_id, "A은행 차세대", "2023-02-01")

    response = client.patch(f"/api/projects/{project_id}", json={"name": "A은행 차세대 2차"})

    assert response.status_code == 200
    assert response.json()["name"] == "A은행 차세대 2차"


def test_patch_project_sets_ended_at(client, current_user_id):
    project_id = db.create_project(current_user_id, "A은행 차세대", "2023-02-01")

    response = client.patch(f"/api/projects/{project_id}", json={"ended_at": "2023-11-30"})

    assert response.json()["ended_at"] == "2023-11-30"


def test_patch_project_is_current_switches_current(client, current_user_id):
    first = db.create_project(current_user_id, "B카드 시스템", "2022-05-01")
    second = db.create_project(current_user_id, "A은행 차세대", "2023-02-01")

    response = client.patch(f"/api/projects/{first}", json={"is_current": True})

    assert response.json()["is_current"] is True
    projects = {p["id"]: p for p in client.get("/api/projects").json()["projects"]}
    assert projects[second]["is_current"] is False


def test_patch_missing_project_returns_404(client, current_user_id):
    response = client.patch("/api/projects/9999", json={"name": "x"})
    assert response.status_code == 404
    assert "detail" in response.json()


def test_patch_another_users_project_returns_404(client, current_user_id):
    """소유권 강제 — 다른 유저 프로젝트의 id를 알아도 수정할 수 없어야 한다."""
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    other_project_id = db.create_project(other_user_id, "다른 유저 프로젝트", "2023-01-01")

    response = client.patch(f"/api/projects/{other_project_id}", json={"name": "가로채기"})

    assert response.status_code == 404
