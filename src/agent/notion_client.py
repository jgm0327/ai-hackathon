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
from urllib.parse import urlencode

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


# 블록 하나에 하위 블록이 있으면 그 하위를 또 요청해야 한다 — 페이지가 깊거나 넓으면
# 요청 수가 곱셈으로 는다. 상한을 둬서 "가져오기"가 몇십 초 걸리는 일을 막는다(넘으면
# 그 지점까지만 가져오고 `_TRUNCATED_MARK`를 붙여서 잘렸다는 걸 사용자가 보게 한다).
_MAX_BLOCK_REQUESTS = 40
# 들여쓰기 3단이면 사람이 읽기에 충분하고, 그보다 깊은 건 대개 부록이다.
_MAX_DEPTH = 3
# 입력창 상한(schemas.MAX_RAW_TEXT = 2,000)보다 넉넉히 둔다 — 실제로 자르는 판단은
# 프론트가 한다. 서버가 미리 2,000으로 자르면 "뒤가 잘렸다"는 걸 알릴 방법이 없다.
_MAX_CONTENT_CHARS = 8_000
_TRUNCATED_MARK = "…(이하 생략)"

# 하위 블록을 따라 들어가지 않는 타입.
#   child_page / child_database: **다른 페이지**다. "사용자가 고른 페이지 하나만
#     가져온다"는 이 모듈의 전제(맨 위 docstring)가 깨지므로 본문을 읽지 않는다.
#   table: 행(table_row)은 표 모양으로 묶어야 해서 `_render_table()`이 따로 다룬다.
_NO_RECURSE = frozenset({"child_page", "child_database", "table"})

# 자체 텍스트 없이 다른 블록을 담기만 하는 타입 — 하위만 펼치고 자기 줄은 만들지 않는다.
_CONTAINER_ONLY = frozenset({"column_list", "column", "synced_block"})

# 사용자가 쓴 글이 아니라 노션이 자동으로 그려주는 것들 — 텍스트로 옮기면 잡음만 된다.
_SKIP = frozenset({"breadcrumb", "table_of_contents", "unsupported"})

_MEDIA_LABELS = {
    "image": "(이미지)",
    "video": "(영상)",
    "audio": "(오디오)",
    "file": "(파일)",
    "pdf": "(PDF)",
    "bookmark": "(링크)",
    "embed": "(임베드)",
    "link_preview": "(링크)",
}


class _Budget:
    """블록 조회 요청 수를 세는 카운터 — 재귀 전체가 하나를 공유한다."""

    def __init__(self, limit: int) -> None:
        self.left = limit
        self.exhausted = False

    def take(self) -> bool:
        if self.left <= 0:
            self.exhausted = True
            return False
        self.left -= 1
        return True


def _extract_page_content(page_id: str, headers: dict) -> str:
    """페이지 본문 블록을 **서식을 살려** 텍스트로 펼친다.

    **9/18 개정 — 왜 서식을 살리나**: 그 전까지 이 함수는 블록마다 `rich_text`의
    plain_text만 뽑아 전부 `\\n`으로 이었다. 제목·불릿·체크박스·인용·코드가 모두
    구분 없는 평문 줄이 돼서 입력창에 들어간 본문이 "우다닥 붙은" 덩어리로 보였다
    (9/18 사용자 신고). 이제 마크다운에 가까운 형태로 옮긴다 — 사람이 읽기 좋고,
    이 텍스트를 이어 읽는 `parse_note()`에도 구조가 그대로 전달된다.

    같이 고친 것:
      - **하위 블록을 따라 들어간다.** 예전엔 통째로 누락됐다 — 토글이나 불릿 안에
        적은 내용이 조용히 사라졌다. 깊이(`_MAX_DEPTH`)와 요청 수(`_MAX_BLOCK_REQUESTS`)
        상한이 있다.
      - **표**를 `| a | b |` 행으로 옮긴다.
      - 사진/파일은 `(이미지)` 같은 한 마디와 캡션만 남긴다 — 본문에 뭔가 있었다는
        사실은 알려주되 URL은 옮기지 않는다(만료되는 서명 URL이라 옮겨도 쓸모없다).

    **하위 페이지(child_page)는 읽지 않는다.** 그건 사용자가 고른 그 페이지가 아니다 —
    맨 위 docstring의 전제이자 유출 신고의 원인이었던 지점이다.
    """
    budget = _Budget(_MAX_BLOCK_REQUESTS)
    text = _clean_lines(_render_blocks(page_id, headers, depth=0, budget=budget))

    if len(text) > _MAX_CONTENT_CHARS:
        return text[:_MAX_CONTENT_CHARS].rstrip() + f"\n{_TRUNCATED_MARK}"
    if budget.exhausted and text:
        return f"{text}\n{_TRUNCATED_MARK}"
    return text


def _iter_children(block_id: str, headers: dict, budget: _Budget):
    """블록 하위를 페이지네이션까지 따라가며 순서대로 내놓는다."""
    cursor = None
    while True:
        if not budget.take():
            return
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor

        response = requests.get(
            f"{_NOTION_API_BASE}/blocks/{block_id}/children",
            headers=headers,
            params=params,
            timeout=15,
        )
        _raise_for_notion_error(response)
        data = response.json()

        yield from data.get("results", [])

        if not data.get("has_more"):
            return
        cursor = data.get("next_cursor")


def _render_blocks(block_id: str, headers: dict, depth: int, budget: _Budget) -> list[str]:
    out: list[str] = []
    indent = "  " * depth
    number = 0  # 번호 목록 연번 — 형제 사이에서만 이어지고 다른 블록이 끼면 끊긴다

    for block in _iter_children(block_id, headers, budget):
        block_type = block.get("type", "")

        number = number + 1 if block_type == "numbered_list_item" else 0

        if block_type in _SKIP:
            continue

        if block_type in _CONTAINER_ONLY:
            # 단(column)은 화면 배치일 뿐이라 들여쓰기를 더하지 않는다.
            out.extend(_render_blocks(block["id"], headers, depth, budget))
            continue

        if block_type == "table":
            _append(out, True, _render_table(block, headers, depth, budget, indent))
            continue

        blank_before, lines = _render_block(block, block_type, number, indent)
        _append(out, blank_before, lines)

        if block.get("has_children") and block_type not in _NO_RECURSE and depth < _MAX_DEPTH:
            out.extend(_render_blocks(block["id"], headers, depth + 1, budget))

    return out


def _append(out: list[str], blank_before: bool, lines: list[str]) -> None:
    if not lines:
        return
    if blank_before and out and out[-1] != "":
        out.append("")
    out.extend(lines)


def _render_block(
    block: dict, block_type: str, number: int, indent: str
) -> tuple[bool, list[str]]:
    """블록 하나 → (앞에 빈 줄이 필요한가, 줄 목록).

    빈 줄은 덩어리를 나누는 블록(제목·문단·인용·코드·구분선) 앞에만 넣는다. 목록
    항목끼리는 붙어 있어야 목록으로 보인다.
    """
    text = _extract_block_text(block)
    payload = block.get(block_type) or {}

    if block_type in ("heading_1", "heading_2", "heading_3"):
        if not text:
            return False, []
        hashes = "#" * int(block_type[-1])
        return True, [f"{indent}{hashes} {text}"]

    if block_type == "paragraph":
        # 빈 문단은 노션에서 여백을 주려고 넣은 것 — 빈 줄 하나로 옮긴다.
        return (True, [f"{indent}{text}"]) if text else (False, [""])

    if block_type == "bulleted_list_item":
        return False, [f"{indent}- {text}"]
    if block_type == "numbered_list_item":
        return False, [f"{indent}{number}. {text}"]
    if block_type == "to_do":
        box = "[x]" if payload.get("checked") else "[ ]"
        return False, [f"{indent}- {box} {text}"]
    if block_type == "toggle":
        # 토글은 접힌 제목 + 하위 블록이다 — 하위는 호출부가 한 단 들여쓰며 붙인다.
        return False, [f"{indent}- {text}"]

    if block_type == "quote":
        return True, [f"{indent}> {text}"]
    if block_type == "callout":
        icon = (payload.get("icon") or {}).get("emoji", "")
        return True, [f"{indent}> {f'{icon} ' if icon else ''}{text}"]

    if block_type == "code":
        language = payload.get("language") or ""
        body = [f"{indent}{line}" for line in text.split("\n")]
        return True, [f"{indent}```{language}", *body, f"{indent}```"]

    if block_type == "divider":
        return True, [f"{indent}---"]

    if block_type == "equation":
        expression = payload.get("expression", "")
        return (True, [f"{indent}{expression}"]) if expression else (False, [])

    if block_type in _MEDIA_LABELS:
        # 캡션이 있으면 그게 그 블록에서 사용자가 쓴 유일한 글이다 — 그것만 살린다.
        caption = "".join(t.get("plain_text", "") for t in payload.get("caption", []))
        return False, [f"{indent}{_MEDIA_LABELS[block_type]} {caption}".rstrip()]

    if block_type in ("child_page", "child_database"):
        # 제목조차 옮기지 않는다 — 사용자가 고른 페이지가 아니다(맨 위 docstring).
        return False, [f"{indent}(하위 페이지는 가져오지 않았어요)"]

    # 모르는 타입이라도 rich_text가 있으면 글은 살린다(개정 전 동작).
    return (False, [f"{indent}{text}"]) if text else (False, [])


def _render_table(
    block: dict, headers: dict, depth: int, budget: _Budget, indent: str
) -> list[str]:
    """`table` 블록을 마크다운 표로 옮긴다.

    셀 텍스트는 `table_row.cells`(셀마다 rich_text 배열)에 있어서 다른 블록과 구조가
    달라 `_render_block()`이 아니라 여기서 따로 다룬다.
    """
    if depth >= _MAX_DEPTH:
        return []

    rows: list[list[str]] = []
    for child in _iter_children(block["id"], headers, budget):
        if child.get("type") != "table_row":
            continue
        cells = child.get("table_row", {}).get("cells") or []
        rows.append(
            [
                "".join(t.get("plain_text", "") for t in cell).replace("|", "\\|").strip()
                for cell in cells
            ]
        )

    if not rows:
        return []

    lines = [f"{indent}| " + " | ".join(row) + " |" for row in rows]
    if (block.get("table") or {}).get("has_column_header") and len(rows) > 1:
        lines.insert(1, f"{indent}| " + " | ".join("---" for _ in rows[0]) + " |")
    return lines


def _clean_lines(lines: list[str]) -> str:
    """빈 줄 중복, 바로 이어지는 같은 줄, 앞뒤 여백을 정리한다.

    같은 줄 중복 제거는 `(이미지)`나 `(하위 페이지는 가져오지 않았어요)`가 수십 개
    이어지는 페이지에서 본문이 그 한 마디로 도배되는 걸 막는다(괄호로 시작하는 줄,
    즉 우리가 붙인 표시에만 적용한다 — 사용자가 쓴 글은 같아도 지우지 않는다).
    """
    cleaned: list[str] = []
    for raw in lines:
        line = raw.rstrip()
        if line == "" and (not cleaned or cleaned[-1] == ""):
            continue
        if cleaned and line == cleaned[-1] and line.lstrip().startswith("("):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def _extract_block_text(block: dict) -> str:
    block_type = block.get("type", "")
    rich_text = (block.get(block_type) or {}).get("rich_text", [])
    return "".join(t.get("plain_text", "") for t in rich_text)


def _raise_for_notion_error(response: requests.Response) -> None:
    if response.status_code == 401:
        raise ValueError("Notion 토큰이 유효하지 않습니다. 토큰을 다시 확인해주세요.")
    response.raise_for_status()


# ---------------------------------------------------------------------------
# OAuth (9/18 신규) — Figma 3.0-a "노션 인증"
# ---------------------------------------------------------------------------
#
# 통합 토큰 방식과 무엇이 다른가: **페이지를 누가 어디서 고르느냐**가 다르다.
#   - 통합 토큰: 사용자가 노션에 들어가 페이지마다 수동으로 공유해야 하고, 앱은
#     "그동안 공유된 것 전부"를 본다. 범위를 좁힐 방법이 앱에 없다.
#   - OAuth: 노션의 인가 화면에 **페이지 선택기가 내장**돼 있어, 사용자가 그 자리에서
#     고른 것만 통합이 볼 수 있다. 우리가 신고받은 "허용하지 않은 페이지" 문제의
#     근본 해법이다(다만 권한 상속은 그대로라 부모를 고르면 하위는 딸려온다).
#
# 구조는 카카오 로그인(`src/auth/kakao_client.py`)과 같은 authorization code 플로우다.
# 다른 점은 토큰 교환 때 client_id/secret을 **HTTP Basic**으로 보낸다는 것뿐.

_NOTION_OAUTH_AUTHORIZE_URL = "https://api.notion.com/v1/oauth/authorize"
_NOTION_OAUTH_TOKEN_URL = "https://api.notion.com/v1/oauth/token"


class NotionOAuthError(Exception):
    """인가 코드 교환 실패 — 라우터가 502로 바꿔 사용자에게 알린다."""


@dataclass
class NotionOAuthResult:
    access_token: str
    workspace_name: str


def oauth_enabled() -> bool:
    """OAuth를 쓸 수 있는 상태인지.

    client_id가 없으면(발급 전) OAuth 경로 전체를 감추고, 사용자가 통합 토큰을 직접
    넣는 기존 경로로 동작한다 — 발급 전에도 앱이 그대로 굴러가게 하려는 설계다.
    """
    return bool(settings.notion_oauth_client_id and settings.notion_oauth_client_secret)


def build_authorize_url(state: str) -> str:
    """노션 인가 화면 URL. `state`는 호출부가 CSRF 방지용으로 쿠키에 저장해뒀다가
    콜백에서 되돌아온 값과 대조한다(카카오와 동일한 패턴).

    `owner=user`는 노션 OAuth에서 필수다 — 이 값이 있어야 사용자 계정 단위로 인가하고
    인가 화면에 페이지 선택기가 뜬다.
    """
    params = {
        "client_id": settings.notion_oauth_client_id,
        "redirect_uri": settings.notion_oauth_redirect_uri,
        "response_type": "code",
        "owner": "user",
        "state": state,
    }
    return f"{_NOTION_OAUTH_AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code_for_token(code: str) -> NotionOAuthResult:
    """인가 코드를 액세스 토큰으로 교환한다(서버-서버 호출).

    노션은 카카오와 달리 client_id/secret을 본문이 아니라 **HTTP Basic**으로 받는다.
    `redirect_uri`는 인가 요청 때와 **바이트 단위로 같아야** 한다 — 다르면 노션이
    거부한다(카카오에서 똑같이 데였던 지점).
    """
    if not oauth_enabled():
        raise NotionOAuthError("노션 OAuth가 설정되어 있지 않습니다 (NOTION_OAUTH_CLIENT_ID 확인)")

    response = requests.post(
        _NOTION_OAUTH_TOKEN_URL,
        auth=(settings.notion_oauth_client_id, settings.notion_oauth_client_secret),
        headers={"Notion-Version": _NOTION_VERSION},
        json={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.notion_oauth_redirect_uri,
        },
        timeout=15,
    )
    if response.status_code >= 400:
        # 노션이 주는 본문에 client_secret이 섞여 올 이유는 없지만, 그래도 전문을
        # 그대로 올리지 않고 상태 코드와 error 필드만 남긴다(로그 유출 방지).
        detail = ""
        try:
            detail = str(response.json().get("error", ""))
        except ValueError:
            pass
        raise NotionOAuthError(f"토큰 교환 실패 ({response.status_code}) {detail}".strip())

    data = response.json()
    token = data.get("access_token")
    if not token:
        raise NotionOAuthError("응답에 access_token이 없습니다")

    return NotionOAuthResult(
        access_token=token,
        # 워크스페이스 이름은 "어디에 연결됐는지"를 사용자에게 보여주는 용도다.
        # 없을 수도 있어서(개인 페이지만 인가한 경우 등) 기본값을 둔다.
        workspace_name=data.get("workspace_name") or "노션 워크스페이스",
    )
