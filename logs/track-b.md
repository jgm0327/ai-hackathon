# Track B — 에이전트/MCP/벡터DB/노션 연동

각 트랙(A~E)마다 하나의 누적 로그 파일을 둔다. **작업 세션이 끝날 때마다**
(하루 작업 끝, 또는 하나의 작업 항목을 완료했을 때) 해당 트랙 파일 맨 아래에
`TEMPLATE.md` 형식으로 새 항목을 추가한다.

---

## 2026-09-10 (세션 1, 9/13 CLAUDE.md 대개편 시 tasks/track-b-agent-pipeline.md에서 이관)

### 오늘 한 일
- 일정보다 3일 당겨서 벡터 매칭 조기 착수: `vectorstore.py`의 `build_jd_index()`/`match_jds()`
  실제 구현, `data/mock_jds/*.json` 20개 작성(고유 스킬 태그 66개)
- 임베딩 provider 이원화: `chroma_default`(배포 기본, 서버 불필요) / `ollama`(로컬 개발,
  bge-m3 다국어) — `EMBEDDING_PROVIDER` 설정으로 분기
- `pipeline.py` 모듈 임포트 시 `build_jd_index()` 자동 1회 호출 (upsert 기반이라 재실행 안전),
  임베딩 서버 연결 실패 시 앱 전체가 안 죽도록 try/except로 방어
- Notion 멀티유저 설계 결정: `user_token`을 절대 optional 취급하지 않음, 프로덕션 경로에서
  `settings.notion_token` 폴백에 암묵적으로 의존하지 않음, 모듈 전역 클라이언트 캐싱 금지

### 트러블슈팅
- **문제**: `requirements.txt`에 고정된 `chromadb==0.5.15`가 로컬 Python 3.14 환경에서
  설치 자체가 안 됨.
- **원인 추정**: 구버전 chromadb가 의존하는 numpy 버전이 Python 3.14용 사전 빌드 wheel을
  제공하지 않아 소스 빌드가 필요한데, 로컬 빌드 툴체인 미비로 실패.
- **해결/우회**: `chromadb`를 최신 버전(`1.5.9`)으로 상향 — 최신 버전은 Python 3.14 wheel을
  제공해 문제없이 설치됨. 단, 최신 chromadb의 커스텀 `EmbeddingFunction` API가 구버전과
  달라서(`EmbeddingFunction[Documents]`를 명시적으로 상속해야 `embed_query`가 자동 제공됨)
  다른 Python/chromadb 버전 조합에서는 재검증이 필요하다는 점을 남겨둠.

### 회고 / 생각
- "배포 환경에는 로컬 서버가 없다"는 제약을 처음부터 염두에 두고 provider 스위치 구조로
  설계해둔 덕분에, 나중에(9/13) `local_multilingual` provider를 추가할 때도 기존 구조를
  거의 그대로 재사용할 수 있었다. 처음부터 확장 가능한 인터페이스를 잡아두는 것의 가치.

---

## 2026-09-13 (세션 2)

### 오늘 한 일
- `chroma_default`(배포 기본 임베딩) 한국어 스킬 태그 매칭 품질을 처음으로 실측 검증함
  (그동안 로컬 개발은 계속 `ollama`(bge-m3)로만 확인했었고, 실제 배포 기본값은 검증한 적이 없었음).
- 서버 없이 쓸 수 있는 다국어 임베딩 대안(`sentence-transformers`)을 검증하고
  `local_multilingual` provider로 `vectorstore.py`에 추가함.
- 사람인(Saramin) 오픈API 클라이언트 스캐폴드(`saramin_client.py`) 작성 — 키 승인 대기 중이라
  실제 호출 없이 API 스펙 문서 기준 모킹 테스트로만 검증.

### 트러블슈팅
- **문제**: `chroma_default`로 4개 한국어 스킬 태그 쿼리를 실제 검색해보니, 2개
  (장애대응/결제시스템/트러블슈팅, DB최적화/인덱스관리/쿼리튜닝)에서 명백히 무관한 도메인의
  공고가 1순위로 나옴 (예: 결제 관련 쿼리에 인증 백엔드 공고가 1위, 결제 정답 공고는
  top-5에서 완전히 누락). 영어 로마자가 섞인 React 쿼리만 정확히 매칭됨.
- **원인 추정**: `chroma_default`(all-MiniLM-L6-v2)가 영어 위주 모델이라 한글 토큰 임베딩
  품질 자체가 낮음. 로컬 Ollama(bge-m3)로 동일 쿼리를 테스트했을 때는 두 쿼리 모두 정답
  공고가 1순위로 정확히 매칭됐던 것과 대조적.
- **해결/우회**: `sentence-transformers`의 `paraphrase-multilingual-MiniLM-L12-v2`를 로컬
  프로세스 안에서 직접 로드하는 `local_multilingual` provider를 추가함 — 별도 서버 없이도
  bge-m3와 비슷한 수준으로 품질이 개선됨을 확인(4개 쿼리 모두 "무관한 도메인 1순위" 실패
  패턴이 사라짐, 2개는 bge-m3와 완전히 동일한 결과). 다만 `sentence-transformers`+torch
  의존성이 무거워(설치 용량/메모리 큼) 무료 배포 티어의 빌드/메모리 제약에 걸릴 위험이 있어,
  `EMBEDDING_PROVIDER` 기본값은 일단 `chroma_default`로 유지하고 실제 전환 여부는 배포
  담당(Track D)이 배포 리소스를 보고 판단하도록 남겨둠.

- **문제**: 로컬 Windows 검증 환경에서 `sentence-transformers` 설치 후 import 시
  `ImportError: DLL load failed ... 애플리케이션 제어 정책에서 이 파일을 차단했습니다`
  (scipy/scikit-learn의 컴파일된 DLL 관련).
- **원인 추정**: 최신 `scipy`(1.18.1)/`scikit-learn` 조합이 이 머신의 Windows 애플리케이션
  제어 정책에 걸림. 다른 환경(특히 Linux 기반 배포 환경)에서는 재현 안 될 가능성 높음.
- **해결/우회**: `scipy==1.16.2`, `scikit-learn==1.7.2`로 버전을 낮춰서 해결. 재현되는
  환경을 위해 `requirements.txt`에 주석으로 남겨둠.

### 막힌 채로 남은 것
- `chroma_default` → `local_multilingual` 전환 여부는 아직 미결정 (배포 판단 대기)
- 사람인 API 키 승인 대기 중 — 승인되는 대로 `saramin_client.py`를 실제 데이터로 검증 필요

### 회고 / 생각
- "배포 전 반드시 확인 필요"라고 남겨뒀던 이슈를 나중에라도 실제로 검증하고 넘어간 것이
  중요했다. 만약 확인 없이 `chroma_default` 그대로 배포했다면, 데모 중 사용자가 흔히 쓸 법한
  "결제", "DB" 관련 낙서에서 엉뚱한 공고가 튀어나오는 걸 실시간으로 목격했을 것 — 신뢰도에
  직접 타격이었을 상황.
- 이날 저녁 CLAUDE.md 대개편(커리어 로그 피벗)이 있었지만, 이 작업(임베딩 품질/사람인 클라이언트)
  자체는 새 아키텍처(SQLite+FastAPI+Next.js)로 넘어가도 그대로 유효한 결과물이라 버려지지 않음 —
  Chroma 기반 벡터 매칭은 새 아키텍처에서도 그대로 쓰인다.
