"""Track B 담당: GET/PUT /api/profile 테스트 (온보딩 프로필, P2).

DB 격리와 로그인 유저 오버라이드는 tests/conftest.py가 담당한다(9/14 카카오 로그인 Phase B —
profile은 싱글턴에서 유저당 1행으로 바뀌었다).

9/18 — Figma "00 · 온보딩"(268:5731) 재설계로 계약이 넓어졌다: 목표 직무(다중),
회사·기간, 그리고 **연차는 받지 않고 회사 기간에서 계산한다.**
"""
from fastapi.testclient import TestClient
import pytest

from src.storage import db
from src.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


EMPTY_PROFILE = {
    "job_field": None,
    "job_detail": None,
    "years_segment": None,
    "target_jobs": [],
    "companies": [],
    "total_months": 0,
}


def test_get_profile_requires_login(client):
    response = client.get("/api/profile")
    assert response.status_code == 401


def test_get_profile_before_onboarding_returns_all_none(client, current_user_id):
    response = client.get("/api/profile")
    assert response.status_code == 200
    assert response.json() == EMPTY_PROFILE


def test_put_profile_saves_and_returns_it(client, current_user_id):
    response = client.put(
        "/api/profile",
        json={"job_field": "개발", "job_detail": "서버 개발자", "years_segment": "4-6"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["job_field"] == "개발"
    assert body["job_detail"] == "서버 개발자"
    assert body["years_segment"] == "4-6"

    # 재조회해도 저장된 값이 그대로 나와야 한다.
    assert client.get("/api/profile").json() == body


def test_put_profile_without_job_detail_is_optional(client, current_user_id):
    response = client.put("/api/profile", json={"job_field": "디자인", "years_segment": "1-3"})
    assert response.status_code == 200
    assert response.json()["job_detail"] is None


def test_put_profile_rejects_invalid_job_field(client, current_user_id):
    """직군은 자유 입력이 아니라 고정 칩 세트다 — CLAUDE.md 2.4."""
    response = client.put("/api/profile", json={"job_field": "우주비행사"})
    assert response.status_code == 422


def test_put_profile_rejects_invalid_years_segment(client, current_user_id):
    response = client.put("/api/profile", json={"job_field": "개발", "years_segment": "20년"})
    assert response.status_code == 422


def test_put_profile_overwrites_previous_value(client, current_user_id):
    client.put("/api/profile", json={"job_field": "개발", "years_segment": "1-3"})
    client.put("/api/profile", json={"job_field": "마케팅·광고", "years_segment": "10+"})

    body = client.get("/api/profile").json()
    assert body["job_field"] == "마케팅·광고"
    assert body["job_detail"] is None
    assert body["years_segment"] == "10+"


def test_profile_is_isolated_per_user(client, current_user_id):
    """소유권 강제 — 다른 유저가 저장한 프로필이 이 유저에게 보이면 안 된다."""
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    db.save_profile(other_user_id, job_field="디자인", job_detail=None, years_segment="10+")

    assert client.get("/api/profile").json() == EMPTY_PROFILE


# --- 9/18 신규: 목표 직무(다중) ---


def test_target_jobs_round_trip(client, current_user_id):
    response = client.put(
        "/api/profile",
        json={
            "job_field": "마케팅·광고",
            "job_detail": "퍼포먼스 마케터",
            "target_jobs": ["프로덕트 마케터", "그로스 마케터"],
        },
    )
    assert response.status_code == 200
    assert response.json()["target_jobs"] == ["프로덕트 마케터", "그로스 마케터"]
    assert client.get("/api/profile").json()["target_jobs"] == ["프로덕트 마케터", "그로스 마케터"]


def test_target_jobs_default_to_empty(client, current_user_id):
    client.put("/api/profile", json={"job_field": "개발"})
    assert client.get("/api/profile").json()["target_jobs"] == []


# --- 9/18 신규: 회사·기간 → 연차 자동 계산 ---


def test_companies_round_trip_and_derive_years(client, current_user_id):
    """연차를 직접 받지 않고 회사 기간에서 계산한다 (Figma 3/4)."""
    response = client.put(
        "/api/profile",
        json={
            "job_field": "개발",
            "companies": [
                {"name": "A은행", "started_at": "2018-01", "ended_at": "2021-12"},  # 48개월
                {"name": "B카드", "started_at": "2022-01", "ended_at": "2023-12"},  # 24개월
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert [c["name"] for c in body["companies"]] == ["A은행", "B카드"]
    assert body["total_months"] == 72  # 6년
    assert body["years_segment"] == "4-6"


def test_years_segment_from_request_is_ignored_when_companies_given(client, current_user_id):
    """두 값이 어긋난 채로 저장되는 경우를 아예 만들지 않는다 — 회사 쪽이 이긴다."""
    response = client.put(
        "/api/profile",
        json={
            "job_field": "개발",
            "years_segment": "10+",  # 거짓말
            "companies": [{"name": "A은행", "started_at": "2024-01", "ended_at": "2024-12"}],
        },
    )
    assert response.json()["years_segment"] == "1-3"


def test_companies_omitted_leaves_existing_list_untouched(client, current_user_id):
    """직무만 고치러 다시 들어온 경우 회사 목록이 날아가면 안 된다."""
    client.put(
        "/api/profile",
        json={
            "job_field": "개발",
            "companies": [{"name": "A은행", "started_at": "2020-01", "ended_at": None}],
        },
    )
    client.put("/api/profile", json={"job_field": "디자인"})  # companies 생략

    body = client.get("/api/profile").json()
    assert [c["name"] for c in body["companies"]] == ["A은행"]
    assert body["job_field"] == "디자인"


def test_companies_empty_list_clears_them(client, current_user_id):
    """생략(None)과 빈 배열([])은 다르다 — 빈 배열은 "다 지워라"다."""
    client.put(
        "/api/profile",
        json={
            "job_field": "개발",
            "companies": [{"name": "A은행", "started_at": "2020-01", "ended_at": None}],
        },
    )
    client.put("/api/profile", json={"job_field": "개발", "companies": []})

    body = client.get("/api/profile").json()
    assert body["companies"] == []
    assert body["total_months"] == 0
    assert body["years_segment"] is None


def test_companies_are_isolated_per_user(client, current_user_id):
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    db.save_profile(
        other_user_id,
        job_field="개발",
        job_detail=None,
        years_segment=None,
        companies=[db.Company(name="남의 회사", started_at="2020-01", ended_at=None)],
    )

    assert client.get("/api/profile").json()["companies"] == []


def test_blank_company_names_are_dropped(client, current_user_id):
    """온보딩에서 "+ 회사 추가"만 누르고 안 채운 빈 칸이 그대로 저장되면 안 된다."""
    response = client.put(
        "/api/profile",
        json={
            "job_field": "개발",
            "companies": [
                {"name": "A은행", "started_at": "2020-01", "ended_at": None},
                {"name": "   ", "started_at": "2020-01", "ended_at": None},
            ],
        },
    )
    assert [c["name"] for c in response.json()["companies"]] == ["A은행"]


def test_legacy_job_field_still_readable(client, current_user_id):
    """9/18에 직군 세트가 바뀌었다. 그 전에 저장된 값("데이터")도 조회는 돼야 한다 —
    읽기까지 Literal로 막으면 기존 유저 프로필이 통째로 500난다."""
    db.save_profile(current_user_id, job_field="데이터", job_detail=None, years_segment="1-3")

    response = client.get("/api/profile")
    assert response.status_code == 200
    assert response.json()["job_field"] == "데이터"
