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
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

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


class _CORSSafeErrorMiddleware:
    """처리 안 된 예외를 잡아 계약대로 `{"detail": "..."}`로 바꾸면서, CORS 헤더도
    직접 붙여서 내려보낸다 (9/14 신규).

    **왜 필요한가 (한 번 잘못 고쳐본 기록)**: 처음엔 `@app.exception_handler(Exception)`로
    고치면 될 줄 알았는데, 실측해보니 안 통했다 — Starlette는 `Exception`(또는 500)에
    등록된 핸들러를 `ServerErrorMiddleware`에 연결하는데, 이 미들웨어는 Starlette가
    항상 스택의 **가장 바깥**(우리가 추가하는 `CORSMiddleware`보다도 바깥)에 자동으로
    끼워 넣는다. 그래서 그 핸들러가 만든 응답도 여전히 CORSMiddleware를 거치지 않고
    나가서 CORS 헤더가 안 붙는다(9/14 실측: curl로 재현 — `access-control-allow-origin`
    헤더 없이 500만 내려옴). `app.add_middleware()`로 추가한 미들웨어는 나중에 추가할수록
    더 바깥쪽(ServerErrorMiddleware에 더 가까운 쪽)에 놓이므로, `CORSMiddleware` **다음에**
    이 미들웨어를 추가하면 이 미들웨어가 CORSMiddleware보다 바깥에서 예외를 가로챌 수
    있다 — 대신 CORSMiddleware가 해주던 origin 헤더 부착을 여기서 직접 해야 한다.

    (9/14 애초 증상: `_call_llm_anthropic()`의 `AttributeError`가 이 경로로 CORS 에러처럼
    보였음 — src/parsing/parser.py 참고. 그 자체 버그는 따로 고쳤지만, 앞으로 어떤
    예외가 나든 CORS 에러 뒤에 숨지 않게 이 미들웨어를 남겨둔다.)
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        except Exception:
            method = scope.get("method", "?")
            path = scope.get("path", "?")
            logger.exception("처리되지 않은 예외: %s %s", method, path)

            response = JSONResponse(status_code=500, content={"detail": "서버 오류가 발생했습니다."})
            origin = next(
                (v.decode("latin-1") for k, v in scope.get("headers", []) if k == b"origin"),
                None,
            )
            if origin and (_origins == ["*"] or origin in _origins):
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
                response.headers["Vary"] = "Origin"
            await response(scope, receive, send)


app.add_middleware(_CORSSafeErrorMiddleware)

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
