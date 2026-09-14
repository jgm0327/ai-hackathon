"""GET /api/health — 배포 검증과 발표 직전 확인용(docs/05-api-contract.md 8장).

각 체크는 best-effort다: 실패해도 500을 던지지 않고 false로 표기한다. 배포 직전
빠르게 확인할 용도라 무거운 호출(실제 LLM 호출 등)은 하지 않는다.
"""
import requests
from fastapi import APIRouter

from src.api.schemas import HealthResponse
from src.config import settings
from src.storage import db

router = APIRouter(tags=["health"])


def _check_db() -> bool:
    try:
        # 9/14 카카오 로그인 Phase B: list_projects()는 이제 user_id가 필요해서 이
        # 로그인 없는 헬스체크에는 안 맞는다. init_db()는 유저 무관하게 연결/스키마
        # 자체만 확인하므로(멱등) 순수 "DB가 살아있는가" 체크로는 이게 더 맞다.
        db.init_db()
        return True
    except Exception:
        return False


def _check_chroma() -> bool:
    try:
        import chromadb

        client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        client.heartbeat()
        return True
    except Exception:
        return False


def _check_llm() -> bool:
    try:
        if settings.llm_provider == "ollama":
            response = requests.get(f"{settings.ollama_base_url}/api/tags", timeout=2)
            return response.ok
        # anthropic 경로: 실제 API 호출은 비용/지연이 있어 여기서는 하지 않는다.
        # 키가 설정돼 있는지만 확인한다(best-effort).
        return bool(settings.llm_api_key)
    except Exception:
        return False


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    db_ok = _check_db()
    chroma_ok = _check_chroma()
    llm_ok = _check_llm()
    return HealthResponse(
        status="ok" if (db_ok and chroma_ok and llm_ok) else "degraded",
        db=db_ok,
        chroma=chroma_ok,
        llm=llm_ok,
    )
