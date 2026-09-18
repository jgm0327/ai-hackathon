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


# ---------------------------------------------------------------------------
# OAuth (Figma 3.0-a) — 9/18 신규
# ---------------------------------------------------------------------------
#
# 통합 토큰과의 차이는 **페이지를 누가 어디서 고르느냐**다. OAuth는 노션의 인가 화면에
# 페이지 선택기가 있어서 사용자가 고른 것만 통합이 보게 된다. 여기서 검증할 건
# 그 플로우의 배관(state 대조, 토큰 보관, 응답에 토큰이 안 새는지)이다.

from dataclasses import replace as _dc_replace  # noqa: E402

from src.agent.notion_client import NotionOAuthError, NotionOAuthResult  # noqa: E402
from src.config import settings  # noqa: E402


@pytest.fixture
def oauth_configured(monkeypatch):
    """client_id/secret이 있는 상태로 만든다 (settings는 frozen이라 인스턴스를 갈아끼운다)."""
    patched = _dc_replace(
        settings,
        notion_oauth_client_id="cid",
        notion_oauth_client_secret="csecret",
        notion_oauth_redirect_uri="http://localhost:8000/api/notion/oauth/callback",
    )
    monkeypatch.setattr("src.agent.notion_client.settings", patched)
    monkeypatch.setattr("src.api.routers.notion.settings", patched)
    yield patched


def test_connection_reports_disconnected_by_default(client, current_user_id):
    body = client.get("/api/notion/connection").json()
    assert body["connected"] is False
    assert body["workspace_name"] is None


def test_connection_hides_oauth_when_client_id_missing(client, current_user_id):
    """client_id 발급 전 — 프론트가 OAuth 버튼 대신 토큰 입력을 띄우게 한다."""
    assert client.get("/api/notion/connection").json()["oauth_available"] is False


def test_oauth_start_is_unavailable_without_client_id(client, current_user_id):
    assert client.get("/api/notion/oauth/start", follow_redirects=False).status_code == 503


def test_oauth_start_redirects_to_notion_with_state(client, current_user_id, oauth_configured):
    response = client.get("/api/notion/oauth/start", follow_redirects=False)

    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith("https://api.notion.com/v1/oauth/authorize")
    assert "client_id=cid" in location
    # owner=user가 있어야 인가 화면에 페이지 선택기가 뜬다 — 이 기능의 핵심이다.
    assert "owner=user" in location
    assert "notion_oauth_state" in response.headers.get("set-cookie", "")


def test_oauth_callback_rejects_state_mismatch(client, current_user_id, oauth_configured):
    client.cookies.set("notion_oauth_state", "expected")
    with patch("src.api.routers.notion.exchange_code_for_token") as mock_exchange:
        response = client.get(
            "/api/notion/oauth/callback?code=abc&state=forged", follow_redirects=False
        )

    assert response.status_code == 400
    # state가 안 맞으면 코드 교환 자체를 시도하지 않아야 한다.
    mock_exchange.assert_not_called()


def test_oauth_callback_stores_token_and_redirects(client, current_user_id, oauth_configured):
    client.cookies.set("notion_oauth_state", "st")
    with patch(
        "src.api.routers.notion.exchange_code_for_token",
        return_value=NotionOAuthResult(access_token="ntn_secret", workspace_name="내 워크스페이스"),
    ):
        response = client.get(
            "/api/notion/oauth/callback?code=abc&state=st", follow_redirects=False
        )

    assert response.status_code == 307
    assert "/record?notion=connected" in response.headers["location"]
    stored = db.get_notion_connection(current_user_id)
    assert stored.access_token == "ntn_secret"
    assert stored.workspace_name == "내 워크스페이스"


def test_connection_never_exposes_the_access_token(client, current_user_id):
    """토큰은 서버 밖으로 나갈 이유가 없다 — 화면엔 워크스페이스 이름만 있으면 된다."""
    db.save_notion_connection(current_user_id, "ntn_secret", "내 워크스페이스", "2026-09-18T00:00:00Z")

    body = client.get("/api/notion/connection").json()
    assert body["connected"] is True
    assert body["workspace_name"] == "내 워크스페이스"
    assert "ntn_secret" not in client.get("/api/notion/connection").text


def test_oauth_callback_maps_exchange_failure_to_502(client, current_user_id, oauth_configured):
    client.cookies.set("notion_oauth_state", "st")
    with patch(
        "src.api.routers.notion.exchange_code_for_token",
        side_effect=NotionOAuthError("토큰 교환 실패 (400)"),
    ):
        response = client.get(
            "/api/notion/oauth/callback?code=abc&state=st", follow_redirects=False
        )

    assert response.status_code == 502


def test_disconnect_deletes_the_stored_token(client, current_user_id):
    db.save_notion_connection(current_user_id, "ntn_secret", "내 워크스페이스", "2026-09-18T00:00:00Z")

    assert client.delete("/api/notion/connection").status_code == 204
    assert db.get_notion_connection(current_user_id) is None


def test_stored_connection_is_used_instead_of_request_token(client, current_user_id):
    """OAuth 연결이 있으면 그 토큰을 쓴다 — 요청이 다른 토큰을 실어 보내도 무시한다."""
    db.save_notion_connection(current_user_id, "ntn_from_oauth", "내 워크스페이스", "2026-09-18T00:00:00Z")

    with patch("src.api.routers.notion.list_notion_pages", return_value=[]) as mock_list:
        client.post("/api/notion/pages", json={"user_token": "ignored_integration_token"})

    assert mock_list.call_args.kwargs["user_token"] == "ntn_from_oauth"


def test_pages_work_without_request_token_once_connected(client, current_user_id):
    """연결된 뒤에는 프론트가 토큰을 안 보내도 된다 — "처음 한 번만 연결하면 돼요"."""
    db.save_notion_connection(current_user_id, "ntn_from_oauth", "내 워크스페이스", "2026-09-18T00:00:00Z")

    with patch("src.api.routers.notion.list_notion_pages", return_value=[]):
        response = client.post("/api/notion/pages", json={"user_token": ""})

    assert response.status_code == 200
