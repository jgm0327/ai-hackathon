"""노션 연동 API — 페이지 목록 + 고른 페이지 하나의 본문 (9/18 재작성).

옛 `POST /api/notion/sync`(대량 가져오기)를 대체한다. 그 엔드포인트는 통합이 접근
가능한 **모든** 페이지를 긁어 전부 LLM에 태웠고, 사용자가 의도하지 않은 노션 문서가
외부로 나갔다(사용자 신고, 9/18).

여기서 지켜야 할 핵심은 **"이 경로는 LLM을 부르지도, 카드를 만들지도 않는다"**는
것이다 — 그게 이 재작성의 이유이므로 테스트로 못 박는다.

실제 Notion API는 호출하지 않는다(`notion_client` 쪽을 모킹).
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.agent.notion_client import NotionEntry, NotionPageSummary
from src.api.main import app
from src.storage import db


@pytest.fixture
def client():
    return TestClient(app)


PAGES = [
    NotionPageSummary(page_id="p1", title="2월 3주차 업무 일지", last_edited_time="2026-09-18T17:20:00Z"),
    NotionPageSummary(page_id="p2", title="가입 퍼널 회고", last_edited_time="2026-09-14T09:00:00Z"),
]


# ---------------------------------------------------------------------------
# 목록
# ---------------------------------------------------------------------------


def test_list_pages_requires_login(client):
    assert client.post("/api/notion/pages", json={"user_token": "secret"}).status_code == 401


def test_list_pages_returns_titles_and_times(client, current_user_id):
    with patch("src.api.routers.notion.list_notion_pages", return_value=PAGES):
        body = client.post("/api/notion/pages", json={"user_token": "secret"}).json()

    assert [p["page_id"] for p in body["pages"]] == ["p1", "p2"]
    assert body["pages"][0]["title"] == "2월 3주차 업무 일지"
    # 본문은 목록에 실리지 않는다 — 목록을 그리는 데 필요 없고, 받으려면 페이지마다
    # 블록 API를 또 불러야 한다.
    assert "content" not in body["pages"][0]


def test_list_pages_does_not_call_llm_or_create_cards(client, current_user_id):
    """이 재작성의 핵심 — 목록을 여는 것만으로는 아무것도 밖으로 나가지 않는다."""
    with patch("src.api.routers.notion.list_notion_pages", return_value=PAGES):
        with patch("src.parsing.parser._call_llm") as mock_llm:
            client.post("/api/notion/pages", json={"user_token": "secret"})

    mock_llm.assert_not_called()
    assert client.get("/api/cards").json()["cards"] == []


def test_list_pages_rejects_blank_token(client, current_user_id):
    """빈 토큰을 통과시키면 개발자 본인의 .env 토큰으로 폴백한다 — 남의 노션이 열린다."""
    with patch("src.api.routers.notion.list_notion_pages") as mock_list:
        response = client.post("/api/notion/pages", json={"user_token": "   "})

    assert response.status_code == 422
    mock_list.assert_not_called()


def test_list_pages_maps_token_error_to_401(client, current_user_id):
    with patch(
        "src.api.routers.notion.list_notion_pages",
        side_effect=ValueError("토큰이 유효하지 않습니다"),
    ):
        response = client.post("/api/notion/pages", json={"user_token": "bad"})

    assert response.status_code == 401


def test_list_pages_passes_user_token_through(client, current_user_id):
    """요청이 준 토큰이 그대로 쓰여야 한다(서버 폴백 토큰이 끼어들면 안 된다)."""
    with patch("src.api.routers.notion.list_notion_pages", return_value=[]) as mock_list:
        client.post("/api/notion/pages", json={"user_token": "secret_abc"})

    assert mock_list.call_args.kwargs["user_token"] == "secret_abc"


# ---------------------------------------------------------------------------
# 본문
# ---------------------------------------------------------------------------


ENTRY = NotionEntry(
    page_id="p1",
    title="2월 3주차 업무 일지",
    content="결제 API 느려서 레디스 캐시 붙임",
    created_time="2026-09-18T00:00:00Z",
)


def test_page_content_returns_body_without_saving(client, current_user_id):
    """본문은 돌려주기만 한다 — 저장도, 변환도 사용자가 [문장으로 바꾸기]를 눌러야 한다."""
    with patch("src.api.routers.notion.fetch_notion_page_content", return_value=ENTRY):
        with patch("src.parsing.parser._call_llm") as mock_llm:
            body = client.post(
                "/api/notion/pages/p1/content", json={"user_token": "secret"}
            ).json()

    assert body["content"] == "결제 API 느려서 레디스 캐시 붙임"
    assert body["title"] == "2월 3주차 업무 일지"
    mock_llm.assert_not_called()
    assert client.get("/api/cards").json()["cards"] == []


def test_page_content_only_fetches_the_chosen_page(client, current_user_id):
    """고른 페이지 하나만 — 여기서 여러 페이지를 긁으면 재작성의 의미가 없다."""
    with patch("src.api.routers.notion.fetch_notion_page_content", return_value=ENTRY) as mock_fetch:
        client.post("/api/notion/pages/p1/content", json={"user_token": "secret"})

    assert mock_fetch.call_count == 1
    assert mock_fetch.call_args.args[0] == "p1"


def test_page_content_rejects_blank_token(client, current_user_id):
    with patch("src.api.routers.notion.fetch_notion_page_content") as mock_fetch:
        response = client.post("/api/notion/pages/p1/content", json={"user_token": ""})

    assert response.status_code == 422
    mock_fetch.assert_not_called()


def test_page_content_requires_login(client):
    response = client.post("/api/notion/pages/p1/content", json={"user_token": "secret"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# 대량 가져오기가 정말로 사라졌는지
# ---------------------------------------------------------------------------


def test_bulk_sync_endpoint_is_gone(client, current_user_id):
    """다시 만들지 말 것 — 이 엔드포인트가 의도하지 않은 노션 문서를 외부로 보냈다."""
    response = client.post("/api/notion/sync", json={"user_token": "secret"})
    assert response.status_code == 404


def test_unfiltered_search_helpers_are_gone():
    """무필터 전체 검색 경로가 코드에서 사라졌는지 — 되살아나면 같은 유출이 재발한다."""
    from src.agent import notion_client

    assert not hasattr(notion_client, "fetch_notion_entries")
    assert not hasattr(notion_client, "_search_pages")
