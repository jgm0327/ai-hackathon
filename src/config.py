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
    # 해커톤 단일 유저 데모 기본값은 "*"(전체 허용) — 인증이 없으므로(docs/05-api-contract.md)
    # 배포 시엔 반드시 실제 프론트 origin으로 좁힐 것 (CLAUDE.md 9장: 하드코딩 금지).
    cors_allowed_origins: str = os.getenv("CORS_ALLOWED_ORIGINS", "*")


settings = Settings()
