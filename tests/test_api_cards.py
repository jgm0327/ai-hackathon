"""Track B 담당: POST/GET/DELETE /api/cards 테스트.

DB 격리와 로그인 유저 오버라이드는 tests/conftest.py의 `_isolated_db`(autouse)/
`current_user_id` 픽스처가 담당한다(9/14 카카오 로그인 Phase B).
"""
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.parsing.parser import ParsedEntry
from src.storage import db

MOCK_LLM_RESPONSE = json.dumps(
    {
        "refined_sentence": "결제 API 응답 지연을 해소하기 위해 Redis 캐싱 레이어를 도입했습니다.",
        "skill_tags": ["Redis", "성능최적화", "결제시스템"],
        "confidence": 0.91,
    },
    ensure_ascii=False,
)


@pytest.fixture(autouse=True)
def _no_op_canonicalize(monkeypatch):
    """태그 캐노니컬라이제이션(임베딩/Chroma)은 test_tag_canonicalizer.py가 검증한다.

    여기서는 API 레이어만 격리해서 보고 싶으므로 항등 함수로 대체한다 — 안 그러면
    이 테스트들이 실제 임베딩 provider(로컬 Ollama 등)에 의존하게 된다.
    """
    monkeypatch.setattr("src.agent.pipeline.canonicalize_tags", lambda tags: tags)
    yield


@pytest.fixture
def client():
    return TestClient(app)


def test_create_card_requires_login(client):
    """로그인 없이(세션 쿠키 없이) 호출하면 401 — current_user_id 픽스처를 안 썼을 때."""
    response = client.post("/api/cards", json={"raw_text": "결제 API 느려서 레디스 캐시 붙임"})
    assert response.status_code == 401


def test_create_card_returns_201_with_parsed_fields(client, current_user_id):
    with patch("src.parsing.parser._call_llm", return_value=MOCK_LLM_RESPONSE):
        response = client.post("/api/cards", json={"raw_text": "결제 API 느려서 레디스 캐시 붙임"})

    assert response.status_code == 201
    body = response.json()
    assert body["raw_text"] == "결제 API 느려서 레디스 캐시 붙임"
    assert body["refined_sentence"] == "결제 API 응답 지연을 해소하기 위해 Redis 캐싱 레이어를 도입했습니다."
    assert body["skill_tags"] == ["Redis", "성능최적화", "결제시스템"]
    assert body["confidence"] == 0.91
    assert body["project_id"] is None
    assert "id" in body
    assert "created_at" in body


def test_create_card_auto_assigns_current_project(client, current_user_id):
    project_id = db.create_project(current_user_id, "A은행 차세대", "2023-02-01")

    with patch("src.parsing.parser._call_llm", return_value=MOCK_LLM_RESPONSE):
        response = client.post("/api/cards", json={"raw_text": "레디스 캐시 붙임"})

    assert response.json()["project_id"] == project_id


def test_list_cards_empty(client, current_user_id):
    response = client.get("/api/cards")
    assert response.status_code == 200
    assert response.json() == {"cards": []}


def test_list_cards_returns_newest_first(client, current_user_id):
    with patch("src.parsing.parser._call_llm", return_value=MOCK_LLM_RESPONSE):
        client.post("/api/cards", json={"raw_text": "첫 번째"})
        client.post("/api/cards", json={"raw_text": "두 번째"})

    response = client.get("/api/cards")
    cards = response.json()["cards"]
    assert [c["raw_text"] for c in cards] == ["두 번째", "첫 번째"]


def test_list_cards_filters_by_project_id(client, current_user_id):
    project_a = db.create_project(current_user_id, "A은행 차세대", "2023-02-01")
    project_b = db.create_project(current_user_id, "B카드 시스템", "2022-05-01")

    with patch("src.parsing.parser._call_llm", return_value=MOCK_LLM_RESPONSE):
        db.set_current_project(current_user_id, project_a)
        client.post("/api/cards", json={"raw_text": "A 카드"})
        db.set_current_project(current_user_id, project_b)
        client.post("/api/cards", json={"raw_text": "B 카드"})

    response = client.get(f"/api/cards?project_id={project_a}")
    cards = response.json()["cards"]
    assert len(cards) == 1
    assert cards[0]["raw_text"] == "A 카드"


def test_list_cards_never_returns_another_users_cards(client, current_user_id):
    """소유권 강제 — 다른 유저 카드가 이 유저의 목록에 섞이면 안 된다."""
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    db.save_card(
        other_user_id,
        None,
        ParsedEntry(raw_text="다른 유저 카드", refined_sentence="다른 유저 카드", skill_tags=[], confidence=0.5),
        "2023-02-14",
    )

    response = client.get("/api/cards")
    assert response.json() == {"cards": []}


def test_delete_card_returns_204_and_removes_it(client, current_user_id):
    with patch("src.parsing.parser._call_llm", return_value=MOCK_LLM_RESPONSE):
        created = client.post("/api/cards", json={"raw_text": "삭제될 카드"}).json()

    response = client.delete(f"/api/cards/{created['id']}")
    assert response.status_code == 204
    assert client.get("/api/cards").json()["cards"] == []


def test_delete_missing_card_still_returns_204(client, current_user_id):
    response = client.delete("/api/cards/9999")
    assert response.status_code == 204


def test_patch_card_tags_updates_skill_tags(client, current_user_id):
    """9/14 신규 — 카테고리(스킬 태그) 직접 수정. /stack에서 가끔 손으로 고치는 경로."""
    with patch("src.parsing.parser._call_llm", return_value=MOCK_LLM_RESPONSE):
        created = client.post("/api/cards", json={"raw_text": "결제 API 느려서 레디스 캐시 붙임"}).json()

    response = client.patch(f"/api/cards/{created['id']}", json={"skill_tags": ["결제/정산"]})

    assert response.status_code == 200
    assert response.json()["skill_tags"] == ["결제/정산"]
    # 재조회해도 반영돼야 한다.
    cards = client.get("/api/cards").json()["cards"]
    assert cards[0]["skill_tags"] == ["결제/정산"]


def test_patch_missing_card_tags_returns_404(client, current_user_id):
    response = client.patch("/api/cards/9999", json={"skill_tags": ["x"]})
    assert response.status_code == 404


def test_patch_another_users_card_tags_returns_404(client, current_user_id):
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    other_card_id = db.save_card(
        other_user_id, None,
        ParsedEntry(raw_text="다른 유저 카드", refined_sentence="다른 유저 카드",
                    skill_tags=["Redis"], confidence=0.5),
        "2023-02-14",
    )

    response = client.patch(f"/api/cards/{other_card_id}", json={"skill_tags": ["가로채기"]})

    assert response.status_code == 404
    assert db.get_card(other_user_id, other_card_id).skill_tags == ["Redis"]
