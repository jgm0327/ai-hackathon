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
    # 매일 쓰는 "메모 한 줄 정리"(parser.py의 parse_note())는 문장 다듬기 + 태그 추출
    # 뿐인 단순 구조화 작업이라 build_resume()/enhance_resume_items()만큼 무거운
    # 추론이 필요 없다(9/15, 발표 데모 체감 속도 개선). Sonnet보다 훨씬 빠른 Haiku로
    # 이 경로만 분리했다 — 인과관계 병합처럼 실제 추론이 필요한 경력기술서 생성 경로는
    # 여전히 llm_model(Sonnet)을 쓴다.
    llm_model_fast: str = os.getenv("LLM_MODEL_FAST", "claude-haiku-4-5-20251001")
    # "127.0.0.1"을 쓴다 — "localhost"로 두면 Windows에서 requests가 IPv6(::1)를 먼저
    # 시도하다 타임아웃 후 IPv4로 폴백하면서 호출마다 2~3초가 그냥 날아간다(9/15 실측,
    # 발표 데모 체감 지연의 실제 원인 중 하나였다). 두 값 다 같은 로컬 Ollama 서버를
    # 가리키지만 127.0.0.1은 DNS/주소체계 결정 자체가 필요 없어 이 문제가 없다.
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "exaone3.5:2.4b")
    # "chroma_default"(기본, **배포용 — 확정**. 별도 서버 불필요, 대신 한국어 임베딩
    #   품질이 낮음. 실측: 4개 한국어 스킬 태그 쿼리 중 2개가 무관한 공고를 1순위로
    #   반환 — tasks/track-b-agent-pipeline.md 참고)
    # "ollama"(로컬 개발용 전용 — bge-m3로 한국어 품질 우수, 로컬 Ollama 서버 필요.
    #   OCI 배포엔 못 쓴다: Ollama 서버까지 그 VM에 띄워야 하고 bge-m3 모델만 로드해도
    #   ~600MB+라 AMD Micro 1GB RAM에서 FastAPI 프로세스와 같이 못 돈다.)
    # "local_multilingual"(서버는 불필요하지만 **배포 후보에서 제외 확정, 9/14** —
    #   sentence-transformers 자체가 torch를 끌고 와서, 실측해보니 FastAPI+Chroma+Anthropic
    #   클라이언트까지 다 합쳐도 chroma_default는 ~152MB인데 반해 이건 모델 로드 시점에
    #   벌써 ~1,232MB를 찍는다 — OCI 배포 대상인 AMD Micro(1GB RAM 고정, tasks/
    #   track-d-deploy.md 2장)를 그 자체로 넘어서서 사실상 OOM 확정. 로컬 개발에서
    #   Ollama보다 빠르면서 한국어 품질을 유지하고 싶을 때만 로컬 전용으로 쓸 것.)
    embedding_provider: str = os.getenv("EMBEDDING_PROVIDER", "chroma_default")
    ollama_embedding_model: str = os.getenv("OLLAMA_EMBEDDING_MODEL", "bge-m3")
    local_multilingual_model: str = os.getenv(
        "LOCAL_MULTILINGUAL_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
    )
    # 로컬 단독 테스트용 폴백 토큰. **서비스 경로에서 이 값에 의존하면 안 된다** —
    # 사용자가 토큰을 안 넣었을 때 여기로 폴백하면 개발자 본인의 노션이 열린다
    # (docs/03-risk-fallback.md 리스크 6). 라우터가 빈 토큰을 422로 막는 이유다.
    notion_token: str = os.getenv("NOTION_TOKEN", "")

    # --- 노션 OAuth (9/18 신규) ---
    # 카카오와 구조가 같다: 콘솔에서 받은 client_id/secret + 바이트 단위로 일치하는
    # redirect_uri. notion.so/my-integrations에서 **Public** 타입으로 만들어야 나온다
    # (Internal은 토큰만 주고 OAuth를 안 쓴다).
    #
    # **비어 있으면 OAuth 경로 전체가 비활성**이고, 사용자가 통합 토큰을 직접 넣는
    # 기존 경로로 동작한다 — 발급 전에도 앱이 그대로 굴러가게 하려는 설계다.
    notion_oauth_client_id: str = os.getenv("NOTION_OAUTH_CLIENT_ID", "")
    notion_oauth_client_secret: str = os.getenv("NOTION_OAUTH_CLIENT_SECRET", "")
    # 노션 콘솔에 등록한 값과 **바이트 단위로 정확히 일치**해야 한다(트레일링 슬래시 포함).
    # 카카오에서 똑같이 데였던 지점이다(DEPLOY-OCI.local.md).
    notion_oauth_redirect_uri: str = os.getenv(
        "NOTION_OAUTH_REDIRECT_URI", "http://localhost:8000/api/notion/oauth/callback"
    )
    # 사람인 오픈API(oapi.saramin.co.kr). 키 승인 대기 중 — 승인되면 .env에 채워 넣으면 됨.
    saramin_api_key: str = os.getenv("SARAMIN_API_KEY", "")
    chroma_persist_dir: str = os.getenv("CHROMA_PERSIST_DIR", "./.chroma")
    mock_jd_dir: str = os.getenv("MOCK_JD_DIR", "data/mock_jds")
    # 태그 캐노니컬라이제이션(신규) — "성능최적화"/"시스템최적화"처럼 LLM이 매번 다르게
    # 뽑아내는 동의어 태그를 임베딩 유사도로 통일한다(CLAUDE.md 2.3: 분류는 임베딩).
    # 코사인 거리 기준값 — 낮을수록 "확실히 같은 개념"일 때만 합친다. 시드 데이터로
    # 수동 검증한 값이라 데이터가 늘어나면 재튜닝 필요(tasks/track-b-agent-pipeline.md 참고).
    tag_canonicalize_threshold: float = float(os.getenv("TAG_CANONICALIZE_THRESHOLD", "0.15"))
    # 미분류 카드 유사도 클러스터링(9/14 신규, "4.1.1 AI 프로젝트 자동 제안") —
    # project_id가 없는 카드끼리만 비교해서 "비슷해 보이는 것들"을 묶어 제안한다
    # (CLAUDE.md 3장: 이미 프로젝트가 배정된 카드는 절대 건드리지 않음). 태그보다
    # 문장 단위라 표현이 더 다양하므로 태그 임계값(0.15)보다 느슨하게 잡았다 —
    # 실측 튜닝 전 초기값, tag_canonicalize_threshold와 같은 "코사인 거리, 낮을수록
    # 유사" 기준이다.
    card_cluster_threshold: float = float(os.getenv("CARD_CLUSTER_THRESHOLD", "0.25"))
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
    # 기록에 첨부한 사진 (9/18 신규, Figma "03 · 커리어 스택" 4.1-b "첨부한 사진").
    # DB에 BLOB으로 넣지 않고 디스크 파일로 둔다 — SQLite 파일이 사진만큼 불어나면
    # 백업 내보내기(GET /api/backup)가 통째로 무거워지고, OCI AMD Micro(RAM 1GB)에서
    # 큰 BLOB을 메모리로 읽어 내보내는 게 부담이다. DB에는 경로와 메타만 남긴다.
    photo_dir: str = os.getenv("PHOTO_DIR", "data/photos")
    # 사진 1장 최대 크기(바이트)와 기록 1건당 최대 장수. 폰 카메라 원본이 보통 2~5MB라
    # 8MB면 넉넉하고, 장수는 목업(3장)보다 여유 있게 잡았다.
    photo_max_bytes: int = int(os.getenv("PHOTO_MAX_BYTES", str(8 * 1024 * 1024)))
    photo_max_per_card: int = int(os.getenv("PHOTO_MAX_PER_CARD", "10"))
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

    # --- 앱 기준 시간대 (9/17 신규) ---
    # 유저가 입력하는 퇴근 시각("18:00")과 카드의 "오늘"은 전부 이 시간대 기준이다.
    # 서버 로컬 시간(datetime.now())에 의존하면 배포 환경에 따라 결과가 달라진다 —
    # 실제로 GitHub Actions 러너(UTC)에서 푸시가 9시간 어긋나 발송되고 있었다(9/17 발견).
    # 코드가 어디서 돌든 같은 결과를 내도록 시간대를 명시적으로 고정한다.
    app_timezone: str = os.getenv("APP_TIMEZONE", "Asia/Seoul")


settings = Settings()
