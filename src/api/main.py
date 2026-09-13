"""FastAPI 앱 진입점 — Track B 담당 (CLAUDE.md 4장 아키텍처).

배포 시엔 이 프로세스를 `uvicorn src.api.main:app --host 127.0.0.1 --port 8000`으로
띄우고 nginx가 `/api/`를 여기로 프록시한다(tasks/track-d-deploy.md 3.2/3.4).
인증 없음 — 해커톤 단일 유저 데모 전제(docs/05-api-contract.md).

여기서 구현하는 라우터는 계약 문서 1~3, 8절(P0)이다. 4~7절(JD 매칭/노션/STT/푸시,
P1)은 시간이 남으면 각 라우터 모듈에 TODO로 남겨둔다.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routers import cards, health, projects, resume
from src.config import settings

app = FastAPI(title="커리어 로그 API")

# CORS 허용 origin은 하드코딩하지 않고 환경변수로 관리한다(CLAUDE.md 9장).
# 해커톤 데모 기본값은 "*"(전체 허용) — 인증이 없으므로 자격증명(쿠키 등)은 함께 허용하지 않는다.
_raw_origins = settings.cors_allowed_origins.strip()
_origins = ["*"] if _raw_origins == "*" else [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cards.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(resume.router, prefix="/api")
app.include_router(health.router, prefix="/api")

# --- P1, 시간이 남으면 구현 (docs/05-api-contract.md 4~7절) ---
# TODO(P1, 4장 JD 매칭): GET /api/jds/match?card_id=&top_k= — src.agent.vectorstore.match_jds() 연결
# TODO(P1, 5장 노션): POST /api/notion/sync — src.agent.notion_client.fetch_notion_entries() +
#                     run_pipeline_batch() 연결. user_token 필수(옵셔널 취급 금지, 리스크 6 참고)
# TODO(P1, 6장 STT): POST /api/stt — 9/13 실기기 음성 검증 결과에 따라 구현 여부 결정
# TODO(P1, 7장 웹푸시): POST/DELETE /api/push/subscribe — src.push.subscription_store 연결
