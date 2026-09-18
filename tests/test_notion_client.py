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


# ---------------------------------------------------------------------------
# 본문 서식 (9/18 — "우다닥 붙어서 보기 힘들다" 신고)
# ---------------------------------------------------------------------------
#
# 개정 전엔 블록 종류를 구분하지 않고 plain_text만 "\n"으로 이어 붙였다. 제목·불릿·
# 체크박스·인용·코드가 전부 같은 평문 줄이 돼서 입력창에 덩어리로 들어갔고, 하위
# 블록(토글 안의 내용 등)은 통째로 누락됐다.


def _page_with_blocks(tree: dict):
    """블록 id → children 응답 맵을 받아 `requests.get` 대역을 만든다.

    `tree`의 키는 블록 id이고 값은 노션의 children 응답 모양이다. 페이지 자체의
    자식은 "page-1" 키에 둔다.
    """
    page_payload = {
        "id": "page-1",
        "created_time": "",
        "properties": {"title": {"type": "title", "title": [{"plain_text": "업무 일지"}]}},
    }

    def fake_get(url, **kwargs):
        if "/blocks/" in url:
            block_id = url.split("/blocks/")[1].split("/")[0]
            return _response(tree.get(block_id, {"results": [], "has_more": False}))
        return _response(page_payload)

    return fake_get


def _rich(text: str) -> list:
    return [{"plain_text": text}]


def _content(tree: dict) -> str:
    with patch("src.agent.notion_client.requests.get", side_effect=_page_with_blocks(tree)):
        return fetch_notion_page_content("page-1", user_token="tok").content


def test_content_keeps_block_structure():
    """제목/불릿/체크박스/인용/코드/구분선이 서로 구분돼 나와야 한다."""
    tree = {
        "page-1": {
            "results": [
                {"id": "b1", "type": "heading_2", "heading_2": {"rich_text": _rich("2월 작업")}},
                {"id": "b2", "type": "paragraph", "paragraph": {"rich_text": _rich("결제가 느렸다")}},
                {
                    "id": "b3",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": _rich("레디스 캐시 붙임")},
                },
                {
                    "id": "b4",
                    "type": "numbered_list_item",
                    "numbered_list_item": {"rich_text": _rich("첫째")},
                },
                {
                    "id": "b5",
                    "type": "numbered_list_item",
                    "numbered_list_item": {"rich_text": _rich("둘째")},
                },
                {"id": "b6", "type": "to_do", "to_do": {"rich_text": _rich("배포"), "checked": True}},
                {"id": "b7", "type": "to_do", "to_do": {"rich_text": _rich("회고"), "checked": False}},
                {"id": "b8", "type": "quote", "quote": {"rich_text": _rich("오류율 0.8%")}},
                {"id": "b9", "type": "divider", "divider": {}},
                {
                    "id": "b10",
                    "type": "code",
                    "code": {"rich_text": _rich("SET key v"), "language": "bash"},
                },
            ],
            "has_more": False,
        }
    }

    content = _content(tree)

    assert "## 2월 작업" in content
    assert "- 레디스 캐시 붙임" in content
    assert "1. 첫째" in content and "2. 둘째" in content
    assert "- [x] 배포" in content and "- [ ] 회고" in content
    assert "> 오류율 0.8%" in content
    assert "---" in content
    assert "```bash" in content and "SET key v" in content
    # 목록 항목끼리는 붙어 있어야 목록으로 보인다.
    assert "1. 첫째\n2. 둘째" in content
    # 문단 앞에는 빈 줄이 생긴다 — 이게 "우다닥 붙는" 걸 푸는 부분이다.
    assert content.startswith("## 2월 작업\n\n결제가 느렸다")


def test_content_follows_nested_blocks():
    """토글/불릿 안에 적은 내용은 개정 전에 통째로 사라졌다."""
    tree = {
        "page-1": {
            "results": [
                {
                    "id": "toggle-1",
                    "type": "toggle",
                    "toggle": {"rich_text": _rich("A은행 결제")},
                    "has_children": True,
                }
            ],
            "has_more": False,
        },
        "toggle-1": {
            "results": [
                {
                    "id": "b1",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": _rich("레디스 붙임")},
                }
            ],
            "has_more": False,
        },
    }

    assert _content(tree) == "- A은행 결제\n  - 레디스 붙임"


def test_content_renders_table_rows():
    tree = {
        "page-1": {
            "results": [
                {
                    "id": "table-1",
                    "type": "table",
                    "table": {"has_column_header": True},
                    "has_children": True,
                }
            ],
            "has_more": False,
        },
        "table-1": {
            "results": [
                {"type": "table_row", "table_row": {"cells": [_rich("지표"), _rich("값")]}},
                {"type": "table_row", "table_row": {"cells": [_rich("오류율"), _rich("0.3%")]}},
            ],
            "has_more": False,
        },
    }

    assert _content(tree) == "| 지표 | 값 |\n| --- | --- |\n| 오류율 | 0.3% |"


def test_content_does_not_read_child_pages():
    """하위 페이지는 사용자가 고른 페이지가 아니다 — 본문도 제목도 가져오지 않는다."""
    tree = {
        "page-1": {
            "results": [
                {
                    "id": "child-1",
                    "type": "child_page",
                    "child_page": {"title": "연봉 협상 메모"},
                    "has_children": True,
                }
            ],
            "has_more": False,
        },
        "child-1": {
            "results": [
                {"id": "x", "type": "paragraph", "paragraph": {"rich_text": _rich("비밀 내용")}}
            ],
            "has_more": False,
        },
    }

    fake_get = _page_with_blocks(tree)
    with patch("src.agent.notion_client.requests.get", side_effect=fake_get) as mock_get:
        content = fetch_notion_page_content("page-1", user_token="tok").content

    assert "비밀 내용" not in content
    assert "연봉 협상 메모" not in content
    assert "(하위 페이지는 가져오지 않았어요)" in content
    assert not any("child-1" in call.args[0] for call in mock_get.call_args_list)


def test_content_keeps_media_marker_and_caption_only():
    tree = {
        "page-1": {
            "results": [
                {
                    "id": "img-1",
                    "type": "image",
                    "image": {
                        "caption": _rich("대시보드 캡처"),
                        "file": {"url": "https://signed.example/secret.png"},
                    },
                }
            ],
            "has_more": False,
        }
    }

    content = _content(tree)

    assert content == "(이미지) 대시보드 캡처"
    assert "signed.example" not in content


def test_content_collapses_repeated_markers():
    """사진만 여러 장인 페이지가 "(이미지)"로 도배되지 않게."""
    tree = {
        "page-1": {
            "results": [
                {"id": f"img-{i}", "type": "image", "image": {"caption": []}} for i in range(5)
            ],
            "has_more": False,
        }
    }

    assert _content(tree) == "(이미지)"


def test_content_stops_at_request_budget():
    """하위 블록을 무한정 따라가지 않는다 — 넘으면 잘렸다고 표시한다."""
    tree = {
        "page-1": {
            "results": [
                {
                    "id": f"b{i}",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": _rich(f"항목 {i}")},
                    "has_children": True,
                }
                for i in range(60)
            ],
            "has_more": False,
        }
    }
    for i in range(60):
        tree[f"b{i}"] = {
            "results": [
                {
                    "id": f"c{i}",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": _rich(f"하위 {i}")},
                }
            ],
            "has_more": False,
        }

    fake_get = _page_with_blocks(tree)
    with patch("src.agent.notion_client.requests.get", side_effect=fake_get) as mock_get:
        content = fetch_notion_page_content("page-1", user_token="tok").content

    block_calls = [c for c in mock_get.call_args_list if "/blocks/" in c.args[0]]
    assert len(block_calls) <= 40
    assert content.endswith("…(이하 생략)")
