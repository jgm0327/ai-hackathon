"""Track B 담당: GET/POST/PATCH /api/projects 테스트."""
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.storage import db


@pytest.fixture(autouse=True)
def _isolated_db(monkeypatch, tmp_path):
    class _FakeSettings:
        db_path = str(tmp_path / "test.db")

    monkeypatch.setattr(db, "settings", _FakeSettings())
    yield


@pytest.fixture
def client():
    return TestClient(app)


def test_list_projects_empty(client):
    response = client.get("/api/projects")
    assert response.status_code == 200
    assert response.json() == {"projects": []}


def test_create_project_sets_current_true(client):
    response = client.post(
        "/api/projects", json={"name": "A은행 차세대", "started_at": "2023-02-01"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "A은행 차세대"
    assert body["started_at"] == "2023-02-01"
    assert body["ended_at"] is None
    assert body["is_current"] is True


def test_list_projects_returns_all(client):
    client.post("/api/projects", json={"name": "B카드 시스템", "started_at": "2022-05-01"})
    client.post("/api/projects", json={"name": "A은행 차세대", "started_at": "2023-02-01"})

    response = client.get("/api/projects")
    names = {p["name"] for p in response.json()["projects"]}
    assert names == {"B카드 시스템", "A은행 차세대"}


def test_patch_project_renames(client):
    project_id = db.create_project("A은행 차세대", "2023-02-01")

    response = client.patch(f"/api/projects/{project_id}", json={"name": "A은행 차세대 2차"})

    assert response.status_code == 200
    assert response.json()["name"] == "A은행 차세대 2차"


def test_patch_project_sets_ended_at(client):
    project_id = db.create_project("A은행 차세대", "2023-02-01")

    response = client.patch(f"/api/projects/{project_id}", json={"ended_at": "2023-11-30"})

    assert response.json()["ended_at"] == "2023-11-30"


def test_patch_project_is_current_switches_current(client):
    first = db.create_project("B카드 시스템", "2022-05-01")
    second = db.create_project("A은행 차세대", "2023-02-01")

    response = client.patch(f"/api/projects/{first}", json={"is_current": True})

    assert response.json()["is_current"] is True
    projects = {p["id"]: p for p in client.get("/api/projects").json()["projects"]}
    assert projects[second]["is_current"] is False


def test_patch_missing_project_returns_404(client):
    response = client.patch("/api/projects/9999", json={"name": "x"})
    assert response.status_code == 404
    assert "detail" in response.json()
