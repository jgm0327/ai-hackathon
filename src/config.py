"""공용 환경변수 로더. 모든 트랙은 이 모듈을 통해서만 설정값에 접근한다."""
import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass(frozen=True)
class Settings:
    # "anthropic"(기본, 배포용) 또는 "ollama"(로컬 무료 검증용 폴백).
    llm_provider: str = os.getenv("LLM_PROVIDER", "anthropic")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "claude-sonnet-5")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "exaone3.5:2.4b")
    # "chroma_default"(기본, 배포용 — 별도 서버 불필요, 대신 한국어 임베딩 품질이 낮음.
    #   실측: 4개 한국어 스킬 태그 쿼리 중 2개가 무관한 공고를 1순위로 반환 —
    #   tasks/track-b-agent-pipeline.md 참고)
    # "ollama"(로컬 개발용 — bge-m3로 한국어 품질 우수, 로컬 Ollama 서버 필요)
    # "local_multilingual"(서버 불필요 — sentence-transformers 다국어 모델을 in-process로
    #   로드. chroma_default보다 한국어 품질 우수하나 의존성이 무거움(torch 포함),
    #   `pip install sentence-transformers` 별도 필요. 배포 기본값 전환은 Track D 판단.)
    embedding_provider: str = os.getenv("EMBEDDING_PROVIDER", "chroma_default")
    ollama_embedding_model: str = os.getenv("OLLAMA_EMBEDDING_MODEL", "bge-m3")
    local_multilingual_model: str = os.getenv(
        "LOCAL_MULTILINGUAL_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
    )
    notion_token: str = os.getenv("NOTION_TOKEN", "")
    notion_mcp_server_url: str = os.getenv("NOTION_MCP_SERVER_URL", "")
    # 사람인 오픈API(oapi.saramin.co.kr). 키 승인 대기 중 — 승인되면 .env에 채워 넣으면 됨.
    saramin_api_key: str = os.getenv("SARAMIN_API_KEY", "")
    chroma_persist_dir: str = os.getenv("CHROMA_PERSIST_DIR", "./.chroma")
    mock_jd_dir: str = os.getenv("MOCK_JD_DIR", "data/mock_jds")
    # 태그 캐노니컬라이제이션(신규) — "성능최적화"/"시스템최적화"처럼 LLM이 매번 다르게
    # 뽑아내는 동의어 태그를 임베딩 유사도로 통일한다(CLAUDE.md 2.3: 분류는 임베딩).
    # 코사인 거리 기준값 — 낮을수록 "확실히 같은 개념"일 때만 합친다. 시드 데이터로
    # 수동 검증한 값이라 데이터가 늘어나면 재튜닝 필요(tasks/track-b-agent-pipeline.md 참고).
    tag_canonicalize_threshold: float = float(os.getenv("TAG_CANONICALIZE_THRESHOLD", "0.15"))
    # Tier 2 푸시 알림(Track E). PRIVATE는 서버(push_sender.py)만, PUBLIC은 프론트 JS의
    # pushManager.subscribe(applicationServerKey=...)에 그대로 노출해도 안전(공개키라서 그렇다).
    vapid_private_key: str = os.getenv("VAPID_PRIVATE_KEY", "")
    vapid_public_key: str = os.getenv("VAPID_PUBLIC_KEY", "")
    vapid_contact_email: str = os.getenv("VAPID_CONTACT_EMAIL", "mailto:example@example.com")
    # 구독 데이터 저장소. 배포된 Streamlit 앱(쓰기)과 GitHub Actions(읽기)가 서로 다른
    # 프로세스라 파일시스템을 공유 못 하므로 Upstash Redis(REST API, 무료)를 공용
    # 저장소로 쓴다. 비어있으면 로컬 JSON 파일로 자동 폴백(로컬 개발용).
    upstash_redis_rest_url: str = os.getenv("UPSTASH_REDIS_REST_URL", "")
    upstash_redis_rest_token: str = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
    # 카드/프로젝트 영속 저장(SQLite). OCI VM 로컬 디스크는 재시작해도 유지되므로
    # 별도 클라우드 DB 불필요 (CLAUDE.md P0 1순위, 9/13 피벗).
    db_path: str = os.getenv("DB_PATH", "data/app.db")
    # FastAPI CORS 허용 origin. 콤마로 구분(예: "https://app.example.com,http://localhost:3000").
    # 9/14 카카오 로그인 도입으로 쿠키 기반 세션을 쓰게 되면서 기본값을 "*"로 둘 수 없게
    # 됐다(자격증명 포함 요청엔 브라우저가 와일드카드 origin을 거부함) — 로컬 개발 기본값을
    # 프론트 dev 서버 origin으로 좁혔다. 배포 시엔 반드시 실제 프론트 origin으로 바꿀 것
    # (CLAUDE.md 9장: 하드코딩 금지 — 여전히 환경변수로 관리하니 원칙은 지켜짐).
    cors_allowed_origins: str = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3001")

    # --- 카카오 소셜 로그인 (9/14 신규) ---
    # REST API 키/Redirect URI는 developers.kakao.com 앱 설정에서 그대로 복사해 넣는다.
    # Client Secret은 콘솔에서 "사용함"으로 켰을 때만 필요(안 켰으면 빈 문자열로 둬도 됨).
    kakao_rest_api_key: str = os.getenv("KAKAO_REST_API_KEY", "")
    kakao_client_secret: str = os.getenv("KAKAO_CLIENT_SECRET", "")
    # Kakao 콘솔에 등록한 값과 바이트 단위로 정확히 일치해야 한다(트레일링 슬래시 등 포함).
    kakao_redirect_uri: str = os.getenv("KAKAO_REDIRECT_URI", "http://localhost:8000/api/auth/kakao/callback")
    # 카카오 콜백 처리가 끝난 뒤 브라우저를 돌려보낼 프론트엔드 주소.
    frontend_base_url: str = os.getenv("FRONTEND_BASE_URL", "http://localhost:3001")
    # 세션 쿠키의 Secure 속성. 배포(HTTPS)는 true, 로컬 개발(http)은 false로 둘 것 —
    # true인데 http로 서빙하면 브라우저가 쿠키 자체를 저장하지 않는다.
    cookie_secure: bool = os.getenv("COOKIE_SECURE", "true").strip().lower() not in ("false", "0", "")
    session_ttl_days: int = int(os.getenv("SESSION_TTL_DAYS", "30"))


settings = Settings()
