"""노션 업무 일지 연동 — Track B 담당.

투트랙 전략 (docs/03-risk-fallback.md 리스크 1 참고):
  1차(필수): fetch_notion_entries() — 공식 REST API
  2차(선택, 타임박스 하루): fetch_notion_entries_via_mcp() — 오픈소스 MCP 서버
두 함수는 반드시 동일한 반환 타입(list[NotionEntry])을 지켜서
프론트엔드(Track C)가 어느 쪽을 쓰든 영향받지 않게 한다.

멀티유저 설계(tasks/track-b-agent-pipeline.md 9/10 결정 참고): user_token은
호출자(app.py)가 항상 명시적으로 넘긴다. settings.notion_token 폴백은 로컬
단독 테스트용일 뿐이니, 이 모듈 내부에서 토큰별 클라이언트를 전역 캐싱하지 않는다.
"""
from dataclasses import dataclass

import requests

from src.config import settings

_NOTION_API_BASE = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"


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

    주의: 타임박스 하루(24시간) 초과 시 즉시 중단하고 fetch_notion_entries()로
    폴백할 것. 중단 시 docs/03-risk-fallback.md에 진행 상황을 기록한다.
    """
    server_url = settings.notion_mcp_server_url
    if not server_url:
        raise ValueError("NOTION_MCP_SERVER_URL이 설정되어 있지 않습니다")
    raise NotImplementedError("Track B(선택): MCP 연동 구현 필요, 실패 시 REST로 폴백")


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
