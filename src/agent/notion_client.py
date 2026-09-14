"""노션 업무 일지 연동 — Track B 담당.

투트랙 전략 (docs/03-risk-fallback.md 리스크 1 참고):
  1차(필수): fetch_notion_entries() — 공식 REST API
  2차(선택, 타임박스 하루): fetch_notion_entries_via_mcp() — 오픈소스 MCP 서버
두 함수는 반드시 동일한 반환 타입(list[NotionEntry])을 지켜서
프론트엔드(Track C)가 어느 쪽을 쓰든 영향받지 않게 한다.

멀티유저 설계(tasks/track-b-agent-pipeline.md 9/10 결정 참고): user_token은
호출자(app.py)가 항상 명시적으로 넘긴다. settings.notion_token 폴백은 로컬
단독 테스트용일 뿐이니, 이 모듈 내부에서 토큰별 클라이언트를 전역 캐싱하지 않는다.

구현 노트 (9/14, MCP 경로): "오픈소스 Notion MCP 서버"가 정확히 어떤 도구
이름/스키마를 노출하는지는 CLAUDE.md/tasks 어디에도 명시돼 있지 않고, 이 세션엔
실제로 띄워서 검증해볼 MCP 서버가 없다 — 그래서 특정 서버 하나에 맞춰 도구 이름을
하드코딩하지 않고, `list_tools()` 결과에서 이름에 "search"가 들어간 도구와
"fetch"/"retrieve"/"get_page"가 들어간 도구를 각각 찾아 쓰는 **적응형** 방식으로
구현했다. 표준적인 MCP Notion 서버라면 대부분 이 명명 규칙을 따르지만, 100%
보장은 못 한다 — 못 찾으면 `NotionMcpUnsupportedError`로 명확히 실패하고
`fetch_notion_entries()`(REST)로 폴백하도록 설계했다(호출부, `src/api/routers/notion.py`
참고). **실제 MCP 서버로 end-to-end 검증은 안 됐다** — 유닛 테스트는 `ClientSession`을
모킹해서 이 적응형 로직 자체만 검증한다.
"""
import asyncio
import json
from dataclasses import dataclass

import requests

from src.config import settings

_NOTION_API_BASE = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"


class NotionMcpUnsupportedError(Exception):
    """연결한 MCP 서버에서 검색/조회용 도구를 찾지 못했을 때."""


@dataclass
class NotionEntry:
    page_id: str
    title: str
    content: str
    created_time: str


def fetch_notion_entries(user_token: str = None) -> list[NotionEntry]:
    """[필수/기본] Notion 공식 REST API로 개인 업무 일지 페이지를 긁어온다.

    /v1/search로 이 토큰(통합)과 공유된 페이지 전체를 찾고, 각 페이지의 블록
    내용을 텍스트로 펼쳐서 NotionEntry 리스트로 반환한다.
    """
    token = user_token or settings.notion_token
    if not token:
        raise ValueError("NOTION_TOKEN이 설정되어 있지 않습니다 (.env 확인)")

    headers = _build_headers(token)
    pages = _search_pages(headers)
    return [_page_to_entry(page, headers) for page in pages]


def fetch_notion_entries_via_mcp(user_token: str = None) -> list[NotionEntry]:
    """[선택] 오픈소스 Notion MCP 서버 연동.

    `NOTION_MCP_SERVER_URL`에 접속해 검색 도구로 페이지를 찾고, 조회 도구로 각
    페이지 내용을 가져온다 (모듈 docstring의 "적응형" 설명 참고). 동기 함수라서
    내부적으로 asyncio 이벤트 루프를 새로 만들어 돌린다 — 호출부(FastAPI 라우터
    등)가 이미 async 이벤트 루프 안에 있다면 이 함수를 직접 쓰지 말고
    `_fetch_notion_entries_via_mcp_async()`를 await할 것.

    주의: 타임박스 하루(24시간) 초과 시 즉시 중단하고 fetch_notion_entries()로
    폴백할 것. 중단 시 docs/03-risk-fallback.md에 진행 상황을 기록한다.
    """
    server_url = settings.notion_mcp_server_url
    if not server_url:
        raise ValueError("NOTION_MCP_SERVER_URL이 설정되어 있지 않습니다")
    token = user_token or settings.notion_token
    if not token:
        raise ValueError("Notion 토큰이 없습니다 (user_token 또는 .env의 NOTION_TOKEN)")

    return asyncio.run(_fetch_notion_entries_via_mcp_async(server_url, token))


async def _fetch_notion_entries_via_mcp_async(server_url: str, token: str) -> list[NotionEntry]:
    # 지연 import — mcp 패키지는 이 경로(선택 기능)를 안 쓰면 불필요한 무게라
    # 모듈 최상단에서 항상 import하지 않는다.
    from mcp import ClientSession
    from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

    http_client = create_mcp_http_client(headers={"Authorization": f"Bearer {token}"})
    async with streamable_http_client(server_url, http_client=http_client) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools

            search_tool = _find_tool(tools, "search")
            fetch_tool = _find_tool(tools, "fetch", "retrieve", "get_page", "read_page")
            if not search_tool or not fetch_tool:
                names = [t.name for t in tools]
                raise NotionMcpUnsupportedError(
                    f"이 MCP 서버에서 검색/조회용 도구를 찾지 못했습니다 (사용 가능한 도구: {names})"
                )

            search_args = _build_search_args(search_tool)
            search_result = await session.call_tool(search_tool.name, search_args)
            pages = _extract_pages(search_result)

            entries = []
            for page in pages:
                page_id = page.get("id") or page.get("page_id") or page.get("url")
                if not page_id:
                    continue
                fetch_args = _build_fetch_args(fetch_tool, str(page_id))
                fetch_result = await session.call_tool(fetch_tool.name, fetch_args)
                entries.append(
                    NotionEntry(
                        page_id=str(page_id),
                        title=page.get("title") or "(제목 없음)",
                        content=_extract_text(fetch_result),
                        created_time=page.get("created_time", ""),
                    )
                )
            return entries


def _find_tool(tools: list, *keywords: str):
    """도구 이름에 keywords 중 하나라도 포함된 첫 도구를 반환한다 (대소문자 무시)."""
    for tool in tools:
        name_lower = tool.name.lower()
        if any(keyword in name_lower for keyword in keywords):
            return tool
    return None


def _schema_properties(tool) -> dict:
    schema = getattr(tool, "input_schema", None) or {}
    return schema.get("properties", {}) if isinstance(schema, dict) else {}


def _build_search_args(search_tool) -> dict:
    """검색 도구의 입력 스키마를 보고 질의어 파라미터 이름을 추정해 채운다.

    표준 이름을 못 찾으면 빈 dict로 호출한다 — 대부분의 검색 도구는 질의어 없이
    호출하면 최근/전체 문서를 반환하도록 만들어져 있다.
    """
    properties = _schema_properties(search_tool)
    for candidate in ("query", "q", "search", "text"):
        if candidate in properties:
            return {candidate: ""}
    return {}


def _build_fetch_args(fetch_tool, page_id: str) -> dict:
    properties = _schema_properties(fetch_tool)
    for candidate in ("id", "page_id", "pageId", "url"):
        if candidate in properties:
            return {candidate: page_id}
    return {"id": page_id}


def _extract_pages(call_result) -> list[dict]:
    """검색 결과에서 페이지 목록을 뽑아낸다. 서버마다 응답 모양이 달라 최대한 관대하게 파싱한다."""
    structured = getattr(call_result, "structured_content", None)
    if isinstance(structured, dict):
        for key in ("results", "pages", "items"):
            if isinstance(structured.get(key), list):
                return [p for p in structured[key] if isinstance(p, dict)]
        if isinstance(structured, list):
            return [p for p in structured if isinstance(p, dict)]

    # structured_content가 없으면 텍스트 콘텐츠 블록을 JSON으로 파싱 시도.
    for block in getattr(call_result, "content", []) or []:
        text = getattr(block, "text", None)
        if not text:
            continue
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            continue
        if isinstance(data, list):
            return [p for p in data if isinstance(p, dict)]
        if isinstance(data, dict):
            for key in ("results", "pages", "items"):
                if isinstance(data.get(key), list):
                    return [p for p in data[key] if isinstance(p, dict)]
    return []


def _extract_text(call_result) -> str:
    """조회 결과에서 본문 텍스트를 뽑아낸다."""
    structured = getattr(call_result, "structured_content", None)
    if isinstance(structured, dict):
        for key in ("content", "text", "body"):
            if isinstance(structured.get(key), str):
                return structured[key]

    lines = []
    for block in getattr(call_result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            lines.append(text)
    return "\n".join(lines)


def _build_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": _NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _search_pages(headers: dict) -> list[dict]:
    """이 통합과 공유된 페이지 전체를 (페이지네이션 처리하며) 조회한다."""
    pages = []
    cursor = None
    while True:
        body = {
            "filter": {"value": "page", "property": "object"},
            "page_size": 100,
        }
        if cursor:
            body["start_cursor"] = cursor

        response = requests.post(f"{_NOTION_API_BASE}/search", headers=headers, json=body, timeout=15)
        _raise_for_notion_error(response)
        data = response.json()

        pages.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")

    return pages


def _page_to_entry(page: dict, headers: dict) -> NotionEntry:
    return NotionEntry(
        page_id=page["id"],
        title=_extract_title(page),
        content=_extract_page_content(page["id"], headers),
        created_time=page.get("created_time", ""),
    )


def _extract_title(page: dict) -> str:
    """페이지 properties 중 type이 title인 걸 찾는다.

    일반 페이지는 보통 키 이름이 "title"이지만, 데이터베이스 행(row)이면
    "이름", "Name" 등 임의의 키일 수 있어 type으로 찾는다.
    """
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            return "".join(t.get("plain_text", "") for t in prop.get("title", []))
    return "(제목 없음)"


def _extract_page_content(page_id: str, headers: dict) -> str:
    """페이지 본문 블록을 순서대로 텍스트로 펼친다 (중첩 블록은 다루지 않음, MVP)."""
    lines = []
    cursor = None
    while True:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor

        response = requests.get(
            f"{_NOTION_API_BASE}/blocks/{page_id}/children",
            headers=headers,
            params=params,
            timeout=15,
        )
        _raise_for_notion_error(response)
        data = response.json()

        for block in data.get("results", []):
            text = _extract_block_text(block)
            if text:
                lines.append(text)

        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")

    return "\n".join(lines)


def _extract_block_text(block: dict) -> str:
    block_type = block.get("type", "")
    rich_text = block.get(block_type, {}).get("rich_text", [])
    return "".join(t.get("plain_text", "") for t in rich_text)


def _raise_for_notion_error(response: requests.Response) -> None:
    if response.status_code == 401:
        raise ValueError("Notion 토큰이 유효하지 않습니다. 토큰을 다시 확인해주세요.")
    response.raise_for_status()
