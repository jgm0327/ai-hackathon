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


# ---------------------------------------------------------------------------
# fetch_notion_entries_via_mcp() — 9/14 신규 (선택 기능, P2).
#
# "오픈소스 Notion MCP 서버"의 정확한 도구 이름/스키마가 스펙에 명시돼 있지 않고
# 이 세션엔 실제로 띄워볼 서버가 없어서(notion_client.py 모듈 docstring 참고),
# mcp.ClientSession/streamable_http_client를 모킹해서 "적응형" 도구 탐색·호출
# 로직 자체만 검증한다. 실제 서버로의 end-to-end 검증은 안 됐다.
# ---------------------------------------------------------------------------
import pytest

from src.agent.notion_client import NotionMcpUnsupportedError, fetch_notion_entries_via_mcp


def _fake_settings(**overrides):
    """settings는 frozen dataclass라 속성별로 monkeypatch할 수 없다 — 객체 통째로 바꿔치기한다
    (tests/test_db.py 등 다른 테스트 파일과 동일한 패턴)."""

    class _S:
        notion_mcp_server_url = "http://fake-mcp"
        notion_token = ""

    s = _S()
    for key, value in overrides.items():
        setattr(s, key, value)
    return s


class _FakeTool:
    def __init__(self, name, input_schema=None):
        self.name = name
        self.input_schema = input_schema or {}


class _FakeToolsResult:
    def __init__(self, tools):
        self.tools = tools


class _FakeTextBlock:
    def __init__(self, text):
        self.text = text


class _FakeCallResult:
    def __init__(self, structured_content=None, content=None):
        self.structured_content = structured_content
        self.content = content or []


class _FakeSession:
    """mcp.ClientSession 대역. async with로 쓰이고, initialize/list_tools/call_tool만 흉내낸다."""

    def __init__(self, *_args, **_kwargs):
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def initialize(self):
        return None

    async def list_tools(self):
        return _FakeToolsResult(_FakeSession.tools_to_return)

    async def call_tool(self, name, args):
        self.calls.append((name, args))
        return _FakeSession.call_results[name]


class _FakeStreamCtx:
    async def __aenter__(self):
        return ("read-stream", "write-stream")

    async def __aexit__(self, *_exc):
        return False


@pytest.fixture(autouse=True)
def _patch_mcp(monkeypatch):
    """mcp.ClientSession과 streamable_http_client를 가짜로 교체한다.

    notion_client.py는 함수 안에서 지연 import(`from mcp import ClientSession`)하므로,
    소스 모듈(mcp, mcp.client.streamable_http)의 이름을 바꿔치기하면 그대로 먹힌다.
    """
    import mcp
    import mcp.client.streamable_http as streamable_http_module

    monkeypatch.setattr(mcp, "ClientSession", _FakeSession)
    monkeypatch.setattr(streamable_http_module, "streamable_http_client", lambda *a, **k: _FakeStreamCtx())
    monkeypatch.setattr(streamable_http_module, "create_mcp_http_client", lambda **k: object())
    yield


def test_fetch_via_mcp_raises_without_server_url(monkeypatch):
    import src.agent.notion_client as notion_client

    monkeypatch.setattr(notion_client, "settings", _fake_settings(notion_mcp_server_url=""))
    with pytest.raises(ValueError, match="NOTION_MCP_SERVER_URL"):
        fetch_notion_entries_via_mcp(user_token="tok")


def test_fetch_via_mcp_raises_without_token(monkeypatch):
    import src.agent.notion_client as notion_client

    monkeypatch.setattr(notion_client, "settings", _fake_settings(notion_token=""))
    with pytest.raises(ValueError, match="토큰"):
        fetch_notion_entries_via_mcp(user_token=None)


def test_fetch_via_mcp_raises_clear_error_when_no_matching_tools(monkeypatch):
    import src.agent.notion_client as notion_client

    monkeypatch.setattr(notion_client, "settings", _fake_settings())
    _FakeSession.tools_to_return = [_FakeTool("unrelated_tool")]
    _FakeSession.call_results = {}

    with pytest.raises(NotionMcpUnsupportedError):
        fetch_notion_entries_via_mcp(user_token="tok")


def test_fetch_via_mcp_finds_tools_by_name_and_maps_entries(monkeypatch):
    import src.agent.notion_client as notion_client

    monkeypatch.setattr(notion_client, "settings", _fake_settings())
    _FakeSession.tools_to_return = [
        _FakeTool("notion-search", input_schema={"properties": {"query": {"type": "string"}}}),
        _FakeTool("notion-fetch", input_schema={"properties": {"id": {"type": "string"}}}),
    ]
    _FakeSession.call_results = {
        "notion-search": _FakeCallResult(
            structured_content={
                "results": [
                    {"id": "page-1", "title": "9/14 업무 일지", "created_time": "2026-09-14"}
                ]
            }
        ),
        "notion-fetch": _FakeCallResult(content=[_FakeTextBlock("결제 버그 고침")]),
    }

    entries = fetch_notion_entries_via_mcp(user_token="tok")

    assert len(entries) == 1
    assert entries[0].page_id == "page-1"
    assert entries[0].title == "9/14 업무 일지"
    assert entries[0].content == "결제 버그 고침"
    assert entries[0].created_time == "2026-09-14"


def test_fetch_via_mcp_search_uses_schema_query_param_name(monkeypatch):
    import src.agent.notion_client as notion_client

    monkeypatch.setattr(notion_client, "settings", _fake_settings())
    _FakeSession.tools_to_return = [
        _FakeTool("search_pages", input_schema={"properties": {"q": {"type": "string"}}}),
        _FakeTool("fetch_page", input_schema={"properties": {"page_id": {"type": "string"}}}),
    ]
    _FakeSession.call_results = {
        "search_pages": _FakeCallResult(structured_content={"results": []}),
        "fetch_page": _FakeCallResult(content=[]),
    }

    fetch_notion_entries_via_mcp(user_token="tok")


def test_fetch_via_mcp_parses_text_content_json_fallback(monkeypatch):
    """structured_content가 없는 서버 대비: 텍스트 블록이 JSON 문자열인 경우도 파싱한다."""
    import src.agent.notion_client as notion_client

    monkeypatch.setattr(notion_client, "settings", _fake_settings())
    _FakeSession.tools_to_return = [
        _FakeTool("search"),
        _FakeTool("fetch"),
    ]
    _FakeSession.call_results = {
        "search": _FakeCallResult(
            content=[_FakeTextBlock('{"results": [{"id": "p1", "title": "제목"}]}')]
        ),
        "fetch": _FakeCallResult(content=[_FakeTextBlock("본문 내용")]),
    }

    entries = fetch_notion_entries_via_mcp(user_token="tok")

    assert len(entries) == 1
    assert entries[0].page_id == "p1"
    assert entries[0].content == "본문 내용"
