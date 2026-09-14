"""Track B 담당: GET/PUT /api/profile 테스트 (온보딩 프로필, P2)."""
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


def test_get_profile_before_onboarding_returns_all_none(client):
    response = client.get("/api/profile")
    assert response.status_code == 200
    assert response.json() == {"job_field": None, "job_detail": None, "years_segment": None}


def test_put_profile_saves_and_returns_it(client):
    response = client.put(
        "/api/profile",
        json={"job_field": "개발", "job_detail": "백엔드", "years_segment": "4-6"},
    )
    assert response.status_code == 200
    assert response.json() == {"job_field": "개발", "job_detail": "백엔드", "years_segment": "4-6"}

    # 재조회해도 저장된 값이 그대로 나와야 한다.
    response = client.get("/api/profile")
    assert response.json() == {"job_field": "개발", "job_detail": "백엔드", "years_segment": "4-6"}


def test_put_profile_without_job_detail_is_optional(client):
    response = client.put(
        "/api/profile", json={"job_field": "디자인", "years_segment": "1-3"}
    )
    assert response.status_code == 200
    assert response.json()["job_detail"] is None


def test_put_profile_rejects_invalid_job_field(client):
    """직군은 자유 입력이 아니라 고정 칩 세트다 — CLAUDE.md 2.4."""
    response = client.put(
        "/api/profile", json={"job_field": "우주비행사", "years_segment": "1-3"}
    )
    assert response.status_code == 422


def test_put_profile_rejects_invalid_years_segment(client):
    """연차는 자유 입력이 아니라 4개 세그먼트만 허용한다 — CLAUDE.md 2.4."""
    response = client.put(
        "/api/profile", json={"job_field": "개발", "years_segment": "20년"}
    )
    assert response.status_code == 422


def test_put_profile_overwrites_previous_value(client):
    client.put("/api/profile", json={"job_field": "개발", "years_segment": "1-3"})
    client.put("/api/profile", json={"job_field": "마케팅", "years_segment": "10+"})

    response = client.get("/api/profile")
    assert response.json() == {"job_field": "마케팅", "job_detail": None, "years_segment": "10+"}
