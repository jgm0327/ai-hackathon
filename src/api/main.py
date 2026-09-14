"""FastAPI 앱 진입점 — Track B 담당 (CLAUDE.md 4장 아키텍처).

배포 시엔 이 프로세스를 `uvicorn src.api.main:app --host 127.0.0.1 --port 8000`으로
띄우고 nginx가 `/api/`를 여기로 프록시한다(tasks/track-d-deploy.md 3.2/3.4).

**구현 노트 (9/14, 카카오 로그인 도입)**: 위 "인증 없음" 전제는 이번 개정으로 끝났다.
`auth.router`가 카카오 로그인/세션을 담당하고, 그 외 라우터들은 Phase B에서 순차적으로
`Depends(get_current_user)`를 받도록 바뀐다(계획서 참고). 쿠키 기반 세션을 쓰게 되면서
CORS도 `allow_credentials=True`로 바뀌었다 — 이 상태에서 origin을 `"*"`로 두면 브라우저가
자격증명 포함 요청 자체를 거부하므로, 아래 가드가 그 조합을 막는다.

여기서 구현하는 라우터는 계약 문서 1~5, 7~9절(P0 + P1/P2 대부분)이다. 6절(STT)만 보류
중이다 — 9/13 실기기 음성 검증 없이 Web Speech API로 이식하기로 했으므로
(docs/06-migration.md 2장, iOS Safari가 14.5부터 지원한다는 사전 조사 근거) 서버측
STT 엔드포인트 자체가 당장은 불필요하다. 실기기에서 실패가 확인되면 그때 추가한다.
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routers import auth, cards, health, jds, notion, profile, projects, push, resume
from src.config import settings

logger = logging.getLogger(__name__)

app = FastAPI(title="커리어 로그 API")

# CORS 허용 origin은 하드코딩하지 않고 환경변수로 관리한다(CLAUDE.md 9장).
# 카카오 로그인 도입(9/14)으로 쿠키 기반 세션을 쓰므로 allow_credentials=True가 필요하고,
# 그 순간부터 "*"는 브라우저가 거부한다(자격증명 포함 요청엔 와일드카드 origin 불가) —
# 배포 시 실제 프론트 origin으로 반드시 좁혀야 한다.
_raw_origins = settings.cors_allowed_origins.strip()
_origins = ["*"] if _raw_origins == "*" else [o.strip() for o in _raw_origins.split(",") if o.strip()]

if _origins == ["*"]:
    logger.warning(
        "CORS_ALLOWED_ORIGINS='*'와 쿠키 기반 세션(allow_credentials=True)은 함께 동작하지 "
        "않습니다 — 브라우저가 자격증명 포함 요청을 거부합니다. .env의 CORS_ALLOWED_ORIGINS를 "
        "실제 프론트 origin(예: http://localhost:3001)으로 설정하세요."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(cards.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(resume.router, prefix="/api")
app.include_router(health.router, prefix="/api")
app.include_router(jds.router, prefix="/api")
app.include_router(notion.router, prefix="/api")
app.include_router(push.router, prefix="/api")
app.include_router(profile.router, prefix="/api")

# --- 남은 P1 (docs/05-api-contract.md 6장) ---
# TODO(6장 STT): POST /api/stt — 9/13 실기기 음성 검증에서 iOS Safari 실패가 실제로
# 확인되면 그때 구현(현재는 Web Speech API 이식으로 진행, docs/06-migration.md 2장)
