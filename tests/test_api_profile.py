"""Track B 담당: GET/PUT /api/profile 테스트 (온보딩 프로필, P2).

DB 격리와 로그인 유저 오버라이드는 tests/conftest.py가 담당한다(9/14 카카오 로그인 Phase B —
profile은 싱글턴에서 유저당 1행으로 바뀌었다).
"""
from fastapi.testclient import TestClient
import pytest

from src.storage import db
from src.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_get_profile_requires_login(client):
    response = client.get("/api/profile")
    assert response.status_code == 401


def test_get_profile_before_onboarding_returns_all_none(client, current_user_id):
    response = client.get("/api/profile")
    assert response.status_code == 200
    assert response.json() == {"job_field": None, "job_detail": None, "years_segment": None}


def test_put_profile_saves_and_returns_it(client, current_user_id):
    response = client.put(
        "/api/profile",
        json={"job_field": "개발", "job_detail": "백엔드", "years_segment": "4-6"},
    )
    assert response.status_code == 200
    assert response.json() == {"job_field": "개발", "job_detail": "백엔드", "years_segment": "4-6"}

    # 재조회해도 저장된 값이 그대로 나와야 한다.
    response = client.get("/api/profile")
    assert response.json() == {"job_field": "개발", "job_detail": "백엔드", "years_segment": "4-6"}


def test_put_profile_without_job_detail_is_optional(client, current_user_id):
    response = client.put(
        "/api/profile", json={"job_field": "디자인", "years_segment": "1-3"}
    )
    assert response.status_code == 200
    assert response.json()["job_detail"] is None


def test_put_profile_rejects_invalid_job_field(client, current_user_id):
    """직군은 자유 입력이 아니라 고정 칩 세트다 — CLAUDE.md 2.4."""
    response = client.put(
        "/api/profile", json={"job_field": "우주비행사", "years_segment": "1-3"}
    )
    assert response.status_code == 422


def test_put_profile_rejects_invalid_years_segment(client, current_user_id):
    """연차는 자유 입력이 아니라 4개 세그먼트만 허용한다 — CLAUDE.md 2.4."""
    response = client.put(
        "/api/profile", json={"job_field": "개발", "years_segment": "20년"}
    )
    assert response.status_code == 422


def test_put_profile_overwrites_previous_value(client, current_user_id):
    client.put("/api/profile", json={"job_field": "개발", "years_segment": "1-3"})
    client.put("/api/profile", json={"job_field": "마케팅", "years_segment": "10+"})

    response = client.get("/api/profile")
    assert response.json() == {"job_field": "마케팅", "job_detail": None, "years_segment": "10+"}


def test_profile_is_isolated_per_user(client, current_user_id):
    """소유권 강제 — 다른 유저가 저장한 프로필이 이 유저에게 보이면 안 된다."""
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    db.save_profile(other_user_id, job_field="디자인", job_detail=None, years_segment="10+")

    response = client.get("/api/profile")
    assert response.json() == {"job_field": None, "job_detail": None, "years_segment": None}
