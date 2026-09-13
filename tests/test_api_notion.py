"""Track B 담당: POST /api/notion/sync 테스트.

실제 Notion API/LLM 호출 없이 fetch_notion_entries()와 parse_note()(run_pipeline_batch가
내부적으로 호출)를 모킹해서 오케스트레이션(가져오기 -> 파싱 -> 저장 -> 응답 변환)만 검증한다.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.agent.notion_client import NotionEntry
from src.api.main import app
from src.parsing.parser import ParsedEntry
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


def test_sync_notion_imports_entries_as_cards(client):
    entries = [
        NotionEntry(page_id="p1", title="9/13", content="결제 버그 고침", created_time="2026-09-13"),
        NotionEntry(page_id="p2", title="9/14", content="레디스 캐시 붙임", created_time="2026-09-14"),
    ]
    parsed_1 = ParsedEntry(raw_text="결제 버그 고침", refined_sentence="결제 모듈의 결함을 수정함",
                            skill_tags=["버그수정"], confidence=0.8)
    parsed_2 = ParsedEntry(raw_text="레디스 캐시 붙임", refined_sentence="Redis 캐싱 레이어를 도입함",
                            skill_tags=["Redis"], confidence=0.9)

    with patch("src.api.routers.notion.fetch_notion_entries", return_value=entries) as mock_fetch:
        with patch("src.api.routers.notion.run_pipeline_batch") as mock_batch:
            # run_pipeline_batch가 실제로 저장까지 하므로, 모킹 안에서 직접 save_card를 호출해
            # 실제 파이프라인과 동일한 부작용(카드 저장)을 흉내낸다.
            def _fake_batch(raw_texts):
                results = []
                for text, parsed in zip(raw_texts, [parsed_1, parsed_2]):
                    card_id = db.save_card(None, parsed, "2026-09-13")
                    results.append({"parsed": parsed, "card_id": card_id})
                return results

            mock_batch.side_effect = _fake_batch

            response = client.post(
                "/api/notion/sync",
                json={"user_token": "secret_abc123", "page_id": "some-page"},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["imported"] == 2
    assert len(body["cards"]) == 2
    assert {c["refined_sentence"] for c in body["cards"]} == {
        "결제 모듈의 결함을 수정함",
        "Redis 캐싱 레이어를 도입함",
    }
    mock_fetch.assert_called_once_with(user_token="secret_abc123")


def test_sync_notion_skips_empty_pages(client):
    entries = [
        NotionEntry(page_id="p1", title="빈 페이지", content="   ", created_time="2026-09-13"),
    ]
    with patch("src.api.routers.notion.fetch_notion_entries", return_value=entries):
        with patch("src.api.routers.notion.run_pipeline_batch", return_value=[]) as mock_batch:
            response = client.post("/api/notion/sync", json={"user_token": "secret_abc123"})

    assert response.status_code == 200
    assert response.json() == {"imported": 0, "cards": []}
    mock_batch.assert_called_once_with([])


def test_sync_notion_rejects_missing_user_token(client):
    response = client.post("/api/notion/sync", json={"user_token": "   "})
    assert response.status_code == 422


def test_sync_notion_does_not_fall_back_to_server_env_token(client):
    """빈 문자열이 settings.notion_token(로컬 개발용 폴백)으로 암묵 전환되면 안 된다
    (docs/03-risk-fallback.md 리스크 6 — 다른 사용자가 개발자 본인 노션 데이터를 끌어오는 사고)."""
    with patch("src.api.routers.notion.fetch_notion_entries") as mock_fetch:
        client.post("/api/notion/sync", json={"user_token": ""})
    mock_fetch.assert_not_called()


def test_sync_notion_returns_401_for_invalid_token(client):
    with patch("src.api.routers.notion.fetch_notion_entries", side_effect=ValueError("토큰이 유효하지 않습니다")):
        response = client.post("/api/notion/sync", json={"user_token": "bad-token"})
    assert response.status_code == 401
