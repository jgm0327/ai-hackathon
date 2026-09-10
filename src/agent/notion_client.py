"""노션 업무 일지 연동 — Track B 담당.

투트랙 전략 (docs/03-risk-fallback.md 리스크 1 참고):
  1차(필수): fetch_notion_entries() — 공식 REST API
  2차(선택, 타임박스 하루): fetch_notion_entries_via_mcp() — 오픈소스 MCP 서버
두 함수는 반드시 동일한 반환 타입(list[NotionEntry])을 지켜서
프론트엔드(Track C)가 어느 쪽을 쓰든 영향받지 않게 한다.
"""
from dataclasses import dataclass

from src.config import settings


@dataclass
class NotionEntry:
    page_id: str
    title: str
    content: str
    created_time: str


def fetch_notion_entries(user_token: str = None) -> list[NotionEntry]:
    """[필수/기본] Notion 공식 REST API로 개인 업무 일지 페이지를 긁어온다.

    TODO(Track B):
    1. Notion REST API (/v1/search 또는 지정 데이터베이스 쿼리)로 페이지 목록 조회
    2. 각 페이지 블록에서 텍스트 콘텐츠 추출
    3. NotionEntry 리스트로 변환
    """
    token = user_token or settings.notion_token
    if not token:
        raise ValueError("NOTION_TOKEN이 설정되어 있지 않습니다 (.env 확인)")
    raise NotImplementedError("Track B: Notion REST API 연동 구현 필요")


def fetch_notion_entries_via_mcp(user_token: str = None) -> list[NotionEntry]:
    """[선택] 오픈소스 Notion MCP 서버 연동.

    주의: 타임박스 하루(24시간) 초과 시 즉시 중단하고 fetch_notion_entries()로
    폴백할 것. 중단 시 docs/03-risk-fallback.md에 진행 상황을 기록한다.
    """
    server_url = settings.notion_mcp_server_url
    if not server_url:
        raise ValueError("NOTION_MCP_SERVER_URL이 설정되어 있지 않습니다")
    raise NotImplementedError("Track B(선택): MCP 연동 구현 필요, 실패 시 REST로 폴백")
