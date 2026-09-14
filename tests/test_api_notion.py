"""Track B 담당: POST /api/notion/sync 테스트.

실제 Notion API/LLM 호출 없이 fetch_notion_entries()와 parse_note()(run_pipeline_batch가
내부적으로 호출)를 모킹해서 오케스트레이션(가져오기 -> 파싱 -> 저장 -> 응답 변환)만 검증한다.

DB 격리와 로그인 유저 오버라이드는 tests/conftest.py가 담당한다(9/14 카카오 로그인 Phase B —
노션으로 가져온 카드도 로그인 유저 소유가 된다).
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.agent.notion_client import NotionEntry
from src.api.main import app
from src.parsing.parser import ParsedEntry
from src.storage import db


@pytest.fixture
def client():
    return TestClient(app)


def test_sync_notion_requires_login(client):
    response = client.post("/api/notion/sync", json={"user_token": "secret_abc123"})
    assert response.status_code == 401


def test_sync_notion_imports_entries_as_cards(client, current_user_id):
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
            def _fake_batch(user_id, raw_texts):
                results = []
                for text, parsed in zip(raw_texts, [parsed_1, parsed_2]):
                    card_id = db.save_card(user_id, None, parsed, "2026-09-13")
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


def test_sync_notion_skips_empty_pages(client, current_user_id):
    entries = [
        NotionEntry(page_id="p1", title="빈 페이지", content="   ", created_time="2026-09-13"),
    ]
    with patch("src.api.routers.notion.fetch_notion_entries", return_value=entries):
        with patch("src.api.routers.notion.run_pipeline_batch", return_value=[]) as mock_batch:
            response = client.post("/api/notion/sync", json={"user_token": "secret_abc123"})

    assert response.status_code == 200
    assert response.json() == {"imported": 0, "cards": []}
    mock_batch.assert_called_once_with(current_user_id, [])


def test_sync_notion_rejects_missing_user_token(client, current_user_id):
    response = client.post("/api/notion/sync", json={"user_token": "   "})
    assert response.status_code == 422


def test_sync_notion_does_not_fall_back_to_server_env_token(client, current_user_id):
    """빈 문자열이 settings.notion_token(로컬 개발용 폴백)으로 암묵 전환되면 안 된다
    (docs/03-risk-fallback.md 리스크 6 — 다른 사용자가 개발자 본인 노션 데이터를 끌어오는 사고)."""
    with patch("src.api.routers.notion.fetch_notion_entries") as mock_fetch:
        client.post("/api/notion/sync", json={"user_token": ""})
    mock_fetch.assert_not_called()


def test_sync_notion_returns_401_for_invalid_token(client, current_user_id):
    with patch("src.api.routers.notion.fetch_notion_entries", side_effect=ValueError("토큰이 유효하지 않습니다")):
        response = client.post("/api/notion/sync", json={"user_token": "bad-token"})
    assert response.status_code == 401


class _FakeSettingsWithMcp:
    notion_mcp_server_url = "http://fake-mcp"


def test_sync_notion_prefers_mcp_when_configured(client, current_user_id):
    """NOTION_MCP_SERVER_URL이 설정돼 있으면 MCP 경로를 먼저 쓰고, REST는 호출하지 않는다."""
    entries = [NotionEntry(page_id="p1", title="t", content="결제 버그 고침", created_time="2026-09-14")]

    with patch("src.api.routers.notion.settings", _FakeSettingsWithMcp()):
        with patch("src.api.routers.notion.fetch_notion_entries_via_mcp", return_value=entries) as mock_mcp:
            with patch("src.api.routers.notion.fetch_notion_entries") as mock_rest:
                with patch("src.api.routers.notion.run_pipeline_batch", return_value=[]):
                    response = client.post("/api/notion/sync", json={"user_token": "secret_abc123"})

    assert response.status_code == 200
    mock_mcp.assert_called_once_with(user_token="secret_abc123")
    mock_rest.assert_not_called()


def test_sync_notion_falls_back_to_rest_when_mcp_fails(client, current_user_id):
    """MCP 서버가 설정돼 있어도 실패하면(다운/도구 이름 불일치 등) REST로 조용히 폴백한다."""
    entries = [NotionEntry(page_id="p1", title="t", content="결제 버그 고침", created_time="2026-09-14")]

    with patch("src.api.routers.notion.settings", _FakeSettingsWithMcp()):
        with patch("src.api.routers.notion.fetch_notion_entries_via_mcp", side_effect=RuntimeError("연결 실패")):
            with patch("src.api.routers.notion.fetch_notion_entries", return_value=entries) as mock_rest:
                with patch("src.api.routers.notion.run_pipeline_batch", return_value=[]):
                    response = client.post("/api/notion/sync", json={"user_token": "secret_abc123"})

    assert response.status_code == 200
    mock_rest.assert_called_once_with(user_token="secret_abc123")
