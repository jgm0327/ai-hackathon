"""`notion_client` 단위 테스트 — 9/18 재작성.

옛 `fetch_notion_entries()`(무필터 전체 검색 + 전 페이지 본문 수집)는 제거됐다.
그 함수가 통합에 공유된 **모든** 페이지를 끝까지 긁어서, 사용자가 의도하지 않은
노션 문서까지 LLM으로 나갔다(사용자 신고, 9/18). 지금은 목록과 본문이 분리되고
본문은 사용자가 고른 하나만 가져온다.

여기서 못 박는 것:
  - 목록 조회가 **최근 수정 순으로 정렬**을 서버(노션)에 맡기고 **limit으로 자른다**
    — 페이지네이션으로 전부 긁지 않는다.
  - 목록 조회가 **본문 블록 API를 부르지 않는다**.
  - 본문 조회가 **지정한 페이지 하나만** 부른다.
"""
from unittest.mock import MagicMock, patch

import pytest

from src.agent.notion_client import (
    NotionPageSummary,
    fetch_notion_page_content,
    list_notion_pages,
)


def _response(payload: dict, status: int = 200) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status
    mock.json.return_value = payload
    return mock


def _search_payload(count: int) -> dict:
    return {
        "results": [
            {
                "id": f"page-{i}",
                "last_edited_time": f"2026-09-{18 - i:02d}T10:00:00Z",
                "properties": {"title": {"type": "title", "title": [{"plain_text": f"페이지 {i}"}]}},
            }
            for i in range(count)
        ],
        "has_more": False,
    }


# ---------------------------------------------------------------------------
# list_notion_pages
# ---------------------------------------------------------------------------


def test_list_pages_raises_without_token():
    with patch("src.agent.notion_client.settings") as mock_settings:
        mock_settings.notion_token = ""
        with pytest.raises(ValueError):
            list_notion_pages(user_token=None)


def test_list_pages_sorts_by_last_edited_and_caps_page_size():
    """정렬을 노션에 맡겨야 limit으로 잘라도 '최근 것'이 남는다."""
    with patch("src.agent.notion_client.requests.post", return_value=_response(_search_payload(3))) as mock_post:
        list_notion_pages(user_token="tok", limit=5)

    body = mock_post.call_args.kwargs["json"]
    assert body["sort"] == {"direction": "descending", "timestamp": "last_edited_time"}
    assert body["page_size"] == 5
    assert body["filter"] == {"value": "page", "property": "object"}


def test_list_pages_does_not_paginate():
    """옛 코드는 has_more를 따라가며 전부 긁었다 — 한 번만 부르는지 확인한다."""
    payload = _search_payload(3)
    payload["has_more"] = True
    payload["next_cursor"] = "cursor-1"

    with patch("src.agent.notion_client.requests.post", return_value=_response(payload)) as mock_post:
        pages = list_notion_pages(user_token="tok")

    assert mock_post.call_count == 1
    assert len(pages) == 3


def test_list_pages_does_not_fetch_block_content():
    """목록은 제목과 시각만 — 본문 블록 API(GET)를 부르면 안 된다."""
    with patch("src.agent.notion_client.requests.post", return_value=_response(_search_payload(2))):
        with patch("src.agent.notion_client.requests.get") as mock_get:
            pages = list_notion_pages(user_token="tok")

    mock_get.assert_not_called()
    assert all(isinstance(p, NotionPageSummary) for p in pages)


def test_list_pages_truncates_to_limit():
    with patch("src.agent.notion_client.requests.post", return_value=_response(_search_payload(10))):
        pages = list_notion_pages(user_token="tok", limit=3)

    assert len(pages) == 3


def test_list_pages_raises_clear_error_on_invalid_token():
    with patch("src.agent.notion_client.requests.post", return_value=_response({}, status=401)):
        with pytest.raises(ValueError):
            list_notion_pages(user_token="bad-token")


# ---------------------------------------------------------------------------
# fetch_notion_page_content
# ---------------------------------------------------------------------------


def test_fetch_page_content_reads_only_the_given_page():
    page_payload = {
        "id": "page-1",
        "created_time": "2026-09-18T00:00:00Z",
        "properties": {"title": {"type": "title", "title": [{"plain_text": "업무 일지"}]}},
    }
    blocks_payload = {
        "results": [
            {
                "type": "paragraph",
                "paragraph": {"rich_text": [{"plain_text": "결제 API 느려서 레디스 캐시 붙임"}]},
            }
        ],
        "has_more": False,
    }

    def fake_get(url, **kwargs):
        if "/blocks/" in url:
            return _response(blocks_payload)
        return _response(page_payload)

    with patch("src.agent.notion_client.requests.get", side_effect=fake_get) as mock_get:
        entry = fetch_notion_page_content("page-1", user_token="tok")

    assert entry.title == "업무 일지"
    assert "레디스 캐시" in entry.content
    # 페이지 조회 + 그 페이지의 블록 조회, 딱 두 번. 다른 페이지를 건드리면 안 된다.
    urls = [call.args[0] for call in mock_get.call_args_list]
    assert all("page-1" in url for url in urls)


def test_fetch_page_content_raises_without_token():
    with patch("src.agent.notion_client.settings") as mock_settings:
        mock_settings.notion_token = ""
        with pytest.raises(ValueError):
            fetch_notion_page_content("page-1", user_token=None)


def test_fetch_page_content_finds_title_property_by_type_not_name():
    """데이터베이스 행이면 title 프로퍼티 키 이름이 "이름"/"Name" 등 임의일 수 있다."""
    page_payload = {
        "id": "page-1",
        "created_time": "",
        "properties": {"이름": {"type": "title", "title": [{"plain_text": "행 제목"}]}},
    }

    def fake_get(url, **kwargs):
        if "/blocks/" in url:
            return _response({"results": [], "has_more": False})
        return _response(page_payload)

    with patch("src.agent.notion_client.requests.get", side_effect=fake_get):
        entry = fetch_notion_page_content("page-1", user_token="tok")

    assert entry.title == "행 제목"
