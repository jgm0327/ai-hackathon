"""Track B 담당: GET /api/jds/match 테스트.

Chroma/임베딩 호출을 실제로 하지 않기 위해 vectorstore.match_jds() 자체를 모킹한다
(test_vectorstore.py가 이미 임베딩 품질을 별도로 검증하므로, 여기서는 라우터의
카드 조회 + 에러 처리 + 스키마 변환만 확인하면 된다).

**구현 노트 (9/14, 카카오 로그인 Phase B — 계획서에 없던 정정)**: 이 라우터가
`db.get_card()`를 직접 호출한다는 걸 뒤늦게 확인해서, 이 파일도 다른 API 테스트처럼
로그인 유저 스코핑이 필요하다. DB 격리/로그인 오버라이드는 tests/conftest.py가 담당한다.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import src.api.routers.jds as jds_router
from src.api.main import app
from src.parsing.parser import ParsedEntry
from src.storage import db


@pytest.fixture(autouse=True)
def _reset_index_ready():
    """`_index_ready`는 모듈 전역이라 테스트 간에 새 프로세스처럼 매번 초기화한다."""
    jds_router._index_ready = False
    yield
    jds_router._index_ready = False


@pytest.fixture
def client():
    return TestClient(app)


_MOCK_MATCHES = [
    {
        "company": "가상핀테크",
        "title": "결제 백엔드 엔지니어",
        "required_skills": ["Redis", "결제시스템", "장애대응"],
        "description": "결제 장애 대응 경험자",
        "score": 0.87,
    }
]


def test_match_jds_requires_login(client):
    response = client.get("/api/jds/match?card_id=1")
    assert response.status_code == 401


def test_match_jds_returns_matches_for_existing_card(client, current_user_id):
    card_id = db.save_card(
        current_user_id,
        None,
        ParsedEntry(
            raw_text="레디스 캐시 붙임",
            refined_sentence="Redis 캐싱 레이어를 도입함",
            skill_tags=["Redis", "결제시스템"],
            confidence=0.9,
        ),
        "2023-02-14",
    )

    with patch("src.api.routers.jds.vectorstore.build_jd_index") as mock_build:
        with patch("src.api.routers.jds.vectorstore.match_jds", return_value=_MOCK_MATCHES) as mock_match:
            response = client.get(f"/api/jds/match?card_id={card_id}&top_k=3")

    assert response.status_code == 200
    body = response.json()
    assert body["matches"] == _MOCK_MATCHES
    mock_build.assert_called_once()
    mock_match.assert_called_once_with(["Redis", "결제시스템"], top_k=3)


def test_match_jds_404_for_missing_card(client, current_user_id):
    with patch("src.api.routers.jds.vectorstore.build_jd_index"):
        response = client.get("/api/jds/match?card_id=9999")
    assert response.status_code == 404


def test_match_jds_404_for_another_users_card(client, current_user_id):
    """소유권 강제 — 다른 유저의 card_id로는 매칭이 돌아가면 안 된다(태그가 새어나감)."""
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    other_card_id = db.save_card(
        other_user_id,
        None,
        ParsedEntry(raw_text="다른 유저 카드", refined_sentence="다른 유저 카드",
                    skill_tags=["Redis"], confidence=0.9),
        "2023-02-14",
    )

    with patch("src.api.routers.jds.vectorstore.build_jd_index"):
        with patch("src.api.routers.jds.vectorstore.match_jds") as mock_match:
            response = client.get(f"/api/jds/match?card_id={other_card_id}")

    assert response.status_code == 404
    mock_match.assert_not_called()


def test_match_jds_returns_empty_list_when_card_has_no_skill_tags(client, current_user_id):
    card_id = db.save_card(
        current_user_id,
        None,
        ParsedEntry(raw_text="오늘 좀 바빴음", refined_sentence="특정 업무 내용을 확인할 수 없음",
                    skill_tags=[], confidence=0.1),
        "2023-02-14",
    )

    with patch("src.api.routers.jds.vectorstore.build_jd_index") as mock_build:
        with patch("src.api.routers.jds.vectorstore.match_jds") as mock_match:
            response = client.get(f"/api/jds/match?card_id={card_id}")

    assert response.status_code == 200
    assert response.json() == {"matches": []}
    mock_build.assert_not_called()
    mock_match.assert_not_called()


def test_match_jds_builds_index_only_once_per_process(client, current_user_id):
    """인덱스는 프로세스당 한 번만 지연 구축한다(매 요청마다 재임베딩하는 낭비를 피함)."""
    card_id = db.save_card(
        current_user_id,
        None,
        ParsedEntry(raw_text="레디스 캐시 붙임", refined_sentence="Redis 캐싱 레이어를 도입함",
                    skill_tags=["Redis"], confidence=0.9),
        "2023-02-14",
    )

    with patch("src.api.routers.jds.vectorstore.build_jd_index") as mock_build:
        with patch("src.api.routers.jds.vectorstore.match_jds", return_value=[]):
            client.get(f"/api/jds/match?card_id={card_id}")
            client.get(f"/api/jds/match?card_id={card_id}")

    mock_build.assert_called_once()
