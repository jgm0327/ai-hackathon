"""Track B 담당: fetch_notion_entries()에 대한 테스트.

실제 Notion API를 호출하지 않도록 requests.post/get을 모킹한다.
"""
from unittest.mock import MagicMock, patch

import pytest

from src.agent.notion_client import NotionEntry, fetch_notion_entries


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status.return_value = None
    return resp


def test_fetch_notion_entries_raises_without_token():
    with pytest.raises(ValueError):
        fetch_notion_entries(user_token=None)


def test_fetch_notion_entries_raises_clear_error_on_invalid_token():
    search_resp = _mock_response(status_code=401, json_data={})
    with patch("src.agent.notion_client.requests.post", return_value=search_resp):
        with pytest.raises(ValueError, match="유효하지 않습니다"):
            fetch_notion_entries(user_token="bad-token")


def test_fetch_notion_entries_parses_title_and_content():
    search_resp = _mock_response(
        json_data={
            "has_more": False,
            "next_cursor": None,
            "results": [
                {
                    "id": "page-1",
                    "created_time": "2026-09-11T00:00:00.000Z",
                    "properties": {
                        "title": {
                            "type": "title",
                            "title": [{"plain_text": "9/11 업무 일지"}],
                        }
                    },
                }
            ],
        }
    )
    blocks_resp = _mock_response(
        json_data={
            "has_more": False,
            "next_cursor": None,
            "results": [
                {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "결제 버그 고침"}]}},
                {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"plain_text": "코드리뷰함"}]}},
            ],
        }
    )

    with patch("src.agent.notion_client.requests.post", return_value=search_resp), patch(
        "src.agent.notion_client.requests.get", return_value=blocks_resp
    ):
        entries = fetch_notion_entries(user_token="valid-token")

    assert len(entries) == 1
    entry = entries[0]
    assert isinstance(entry, NotionEntry)
    assert entry.page_id == "page-1"
    assert entry.title == "9/11 업무 일지"
    assert entry.content == "결제 버그 고침\n코드리뷰함"
    assert entry.created_time == "2026-09-11T00:00:00.000Z"


def test_fetch_notion_entries_finds_title_property_by_type_not_name():
    """데이터베이스 행이면 title 속성 키 이름이 임의(예: '이름')일 수 있다."""
    search_resp = _mock_response(
        json_data={
            "has_more": False,
            "results": [
                {
                    "id": "page-2",
                    "created_time": "2026-09-11T00:00:00.000Z",
                    "properties": {
                        "이름": {"type": "title", "title": [{"plain_text": "DB 행 제목"}]},
                        "상태": {"type": "select", "select": {"name": "완료"}},
                    },
                }
            ],
        }
    )
    blocks_resp = _mock_response(json_data={"has_more": False, "results": []})

    with patch("src.agent.notion_client.requests.post", return_value=search_resp), patch(
        "src.agent.notion_client.requests.get", return_value=blocks_resp
    ):
        entries = fetch_notion_entries(user_token="valid-token")

    assert entries[0].title == "DB 행 제목"
    assert entries[0].content == ""


def test_fetch_notion_entries_paginates_search_results():
    page1 = _mock_response(
        json_data={
            "has_more": True,
            "next_cursor": "cursor-1",
            "results": [
                {"id": "a", "created_time": "t", "properties": {"title": {"type": "title", "title": []}}}
            ],
        }
    )
    page2 = _mock_response(
        json_data={
            "has_more": False,
            "results": [
                {"id": "b", "created_time": "t", "properties": {"title": {"type": "title", "title": []}}}
            ],
        }
    )
    blocks_resp = _mock_response(json_data={"has_more": False, "results": []})

    with patch(
        "src.agent.notion_client.requests.post", side_effect=[page1, page2]
    ) as mock_post, patch("src.agent.notion_client.requests.get", return_value=blocks_resp):
        entries = fetch_notion_entries(user_token="valid-token")

    assert [e.page_id for e in entries] == ["a", "b"]
    assert mock_post.call_count == 2
    # 두 번째 호출엔 커서가 실려야 한다.
    second_call_body = mock_post.call_args_list[1].kwargs["json"]
    assert second_call_body["start_cursor"] == "cursor-1"
