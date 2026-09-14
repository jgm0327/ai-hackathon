"""Track B 담당: POST/GET/DELETE /api/cards 테스트.

DB는 test_db.py/test_pipeline.py와 동일하게 격리된 임시 SQLite 파일을 쓰고,
LLM 호출부(parser._call_llm)는 모킹한다. src.agent.pipeline이 src.storage.db를
`from ... import`로 가져오므로, 두 모듈의 `settings`를 모두 monkeypatch해야
같은 임시 DB를 바라본다(test_pipeline.py와 동일 패턴).
"""
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
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
def _isolated_db(monkeypatch, tmp_path):
    class _FakeSettings:
        db_path = str(tmp_path / "test.db")

    monkeypatch.setattr(db, "settings", _FakeSettings())
    yield


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


def test_create_card_returns_201_with_parsed_fields(client):
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


def test_create_card_auto_assigns_current_project(client):
    project_id = db.create_project("A은행 차세대", "2023-02-01")

    with patch("src.parsing.parser._call_llm", return_value=MOCK_LLM_RESPONSE):
        response = client.post("/api/cards", json={"raw_text": "레디스 캐시 붙임"})

    assert response.json()["project_id"] == project_id


def test_list_cards_empty(client):
    response = client.get("/api/cards")
    assert response.status_code == 200
    assert response.json() == {"cards": []}


def test_list_cards_returns_newest_first(client):
    with patch("src.parsing.parser._call_llm", return_value=MOCK_LLM_RESPONSE):
        client.post("/api/cards", json={"raw_text": "첫 번째"})
        client.post("/api/cards", json={"raw_text": "두 번째"})

    response = client.get("/api/cards")
    cards = response.json()["cards"]
    assert [c["raw_text"] for c in cards] == ["두 번째", "첫 번째"]


def test_list_cards_filters_by_project_id(client):
    project_a = db.create_project("A은행 차세대", "2023-02-01")
    project_b = db.create_project("B카드 시스템", "2022-05-01")

    with patch("src.parsing.parser._call_llm", return_value=MOCK_LLM_RESPONSE):
        db.set_current_project(project_a)
        client.post("/api/cards", json={"raw_text": "A 카드"})
        db.set_current_project(project_b)
        client.post("/api/cards", json={"raw_text": "B 카드"})

    response = client.get(f"/api/cards?project_id={project_a}")
    cards = response.json()["cards"]
    assert len(cards) == 1
    assert cards[0]["raw_text"] == "A 카드"


def test_delete_card_returns_204_and_removes_it(client):
    with patch("src.parsing.parser._call_llm", return_value=MOCK_LLM_RESPONSE):
        created = client.post("/api/cards", json={"raw_text": "삭제될 카드"}).json()

    response = client.delete(f"/api/cards/{created['id']}")
    assert response.status_code == 204
    assert client.get("/api/cards").json()["cards"] == []


def test_delete_missing_card_still_returns_204(client):
    response = client.delete("/api/cards/9999")
    assert response.status_code == 204
