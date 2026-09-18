"""노션 연동 — 페이지 목록 조회 + 고른 페이지 하나의 본문 조회 (Track B).

**9/18 전면 재작성.** 그 전까지 이 모듈은 `/v1/search`를 필터 없이 불러 **이 통합이
접근 가능한 모든 페이지**를 끝까지 긁고, 그 본문을 전부 LLM에 태워 카드로 저장했다
(`fetch_notion_entries()` + `POST /api/notion/sync`). 노션은 부모 페이지를 통합에
공유하면 **하위 트리 전체**에 권한을 주기 때문에, 사용자가 의도하지 않은 문서까지
외부(우리 서버 → Anthropic)로 나갔다. 실제로 그 신고를 받아 걷어냈다.

지금 구조는 Figma "01 · 기록 · Tab A"의 3.0-b "노션 페이지 선택" 그대로다:
  1. `list_notion_pages()` — 최근 수정 순 **제목과 시각만**. 본문도, LLM도 없다.
  2. 사용자가 목록에서 **하나를 고른다**.
  3. `fetch_notion_page_content()` — 그 페이지 하나의 본문만 가져와 **입력창에 채운다**.
  4. 사용자가 읽고 고친 뒤 [문장으로 바꾸기]를 눌러야 비로소 변환된다.

무엇이 외부로 나가는지를 사용자가 매번 눈으로 보고 정한다는 게 이 설계의 핵심이다.
대량 가져오기 경로는 다시 만들지 말 것.

**같이 지운 것**: MCP 경로(`fetch_notion_entries_via_mcp()` 등)도 제거했다. 같은
무필터 검색을 쓰면서 오직 위 sync 엔드포인트만 호출하던 코드라, sync가 사라지면
어디서도 안 불리는 데다 같은 유출 형태를 그대로 갖고 있었다. 실제 MCP 서버로
end-to-end 검증도 된 적이 없다(9/14 노트). 필요하면 git 히스토리에서 되살릴 것.

멀티유저 설계: `user_token`은 호출자가 항상 명시적으로 넘긴다. `settings.notion_token`
폴백은 로컬 단독 테스트용일 뿐이라 토큰별 클라이언트를 전역 캐싱하지 않는다.
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


@dataclass
class NotionPageSummary:
    """페이지 선택 화면(Figma 3.0-b)에 뿌릴 **메타데이터만**.

    본문(`content`)이 없는 게 핵심이다 — 목록을 그리는 데 본문이 필요 없고, 본문을
    받아오려면 페이지마다 블록 API를 또 불러야 한다. 고른 페이지 하나만 나중에
    `fetch_notion_page_content()`로 가져온다.
    """

    page_id: str
    title: str
    last_edited_time: str


# 페이지 선택 화면에 한 번에 보여줄 최대 개수 (Figma 3.0-b는 "최근 수정한 페이지 3건").
# 목록이 길어봐야 고르기만 어려워지고, 최근 것부터 정렬돼 있으면 대부분 앞쪽에서 끝난다.
MAX_PAGE_CANDIDATES = 20


def list_notion_pages(user_token: str = None, limit: int = MAX_PAGE_CANDIDATES) -> list[NotionPageSummary]:
    """[9/18 신규] 고를 수 있는 페이지 **목록만** 가져온다 (Figma 3.0-b).

    **이 함수는 본문을 읽지 않고, 카드를 만들지 않고, LLM을 부르지 않는다.**
    노션 워크스페이스의 내용이 우리 서버나 Anthropic으로 나가는 지점이 아니다 —
    제목과 수정 시각만 받아서 화면에 뿌린다.

    **왜 이렇게 바꿨나 (9/18)**: 예전 `fetch_notion_entries()`는 `/v1/search`를 필터
    없이 불러서 **이 통합이 접근 가능한 모든 페이지**를 끝까지 긁고, 그 본문을 전부
    LLM에 태워 카드로 저장했다. 노션은 부모 페이지를 공유하면 하위 트리 전체에 권한을
    주기 때문에, 사용자가 의도하지 않은 문서까지 외부로 나갔다(사용자 신고, 9/18).
    이제 **무엇을 보낼지는 사용자가 목록에서 하나 골라야** 정해진다.

    최근 수정 순으로 정렬해서 `limit`개까지만 받는다 — 페이지네이션으로 전부 긁지
    않는다. 워크스페이스가 큰 계정에서 목록 한 번 여는 데 수십 번 왕복할 이유가 없다.
    """
    token = user_token or settings.notion_token
    if not token:
        raise ValueError("NOTION_TOKEN이 설정되어 있지 않습니다 (.env 확인)")

    headers = _build_headers(token)
    body = {
        "filter": {"value": "page", "property": "object"},
        # Figma 3.0-b가 "최근 수정한 페이지"라고 명시한다. 정렬을 서버(노션)에 맡겨야
        # limit으로 잘라도 "최근 것"이 남는다 — 안 그러면 어떤 N개가 올지 알 수 없다.
        "sort": {"direction": "descending", "timestamp": "last_edited_time"},
        "page_size": min(limit, 100),
    }
    response = requests.post(f"{_NOTION_API_BASE}/search", headers=headers, json=body, timeout=15)
    _raise_for_notion_error(response)

    return [
        NotionPageSummary(
            page_id=page["id"],
            title=_extract_title(page),
            last_edited_time=page.get("last_edited_time", ""),
        )
        for page in response.json().get("results", [])
    ][:limit]


def fetch_notion_page_content(page_id: str, user_token: str = None) -> NotionEntry:
    """[9/18 신규] **사용자가 고른 페이지 하나**의 본문을 가져온다 (Figma 3.0-b).

    가져온 본문은 입력창에 채워질 뿐, 이 함수는 카드를 만들지도 LLM을 부르지도
    않는다 — 사용자가 화면에서 읽고 고친 뒤 [문장으로 바꾸기]를 눌러야 변환된다.
    "무엇이 외부로 나가는지"를 사용자가 눈으로 보고 정하게 하는 게 이 설계의 핵심이다.
    """
    token = user_token or settings.notion_token
    if not token:
        raise ValueError("NOTION_TOKEN이 설정되어 있지 않습니다 (.env 확인)")

    headers = _build_headers(token)
    response = requests.get(f"{_NOTION_API_BASE}/pages/{page_id}", headers=headers, timeout=15)
    _raise_for_notion_error(response)
    page = response.json()

    return NotionEntry(
        page_id=page_id,
        title=_extract_title(page),
        content=_extract_page_content(page_id, headers),
        created_time=page.get("created_time", ""),
    )


def _build_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": _NOTION_VERSION,
        "Content-Type": "application/json",
    }


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
