# Track B — AI 에이전트 빌드 및 MCP 인프라 (9/13~9/15)

가장 리스크가 높은 트랙. 반드시 `docs/03-risk-fallback.md`를 먼저 읽고 타임박스를 지킬 것.

## 목표 (우선순위 순서 — 위에서부터 완료)

### 1. Vector DB 매칭 파이프라인 (필수)
`src/agent/vectorstore.py`
```python
def build_jd_index(jd_dir: str = "data/mock_jds") -> None:
    """data/mock_jds/*.json을 임베딩해서 Chroma 인덱스를 (재)구축한다."""
    ...

def match_jds(skill_tags: list[str], top_k: int = 5) -> list[dict]:
    """역량 태그로 유사 JD를 top_k개 반환한다. 반환 형식은 mock_jds JSON 스키마와 동일."""
    ...
```
- `data/mock_jds/`에 최소 15~20개 가상 원티드 JD JSON을 만들어둔다 (직무, 요구 역량, 회사명 등)
- 배포 시 재임베딩 전략을 쓸 것이므로(리스크 문서 참고) `build_jd_index()`는 멱등하게 설계

### 2. 파이프라인 오케스트레이션 (필수)
`src/agent/pipeline.py`
```python
def run_pipeline(raw_text: str) -> dict:
    """
    parsing.parser.parse_note() -> agent.vectorstore.match_jds() 순서로 실행하고
    프론트엔드가 그대로 렌더링할 수 있는 dict를 반환한다.
    반환 예시: {"parsed": ParsedEntry, "matched_jds": [...]}
    """
    ...
```

### 3. 노션 연동 — 투트랙 (필수: REST / 선택: MCP)
`src/agent/notion_client.py`
- **1차(필수)**: `fetch_notion_entries()` — Notion 공식 REST API로 개인 업무 일지 페이지를
  긁어와 텍스트 리스트로 반환
- **2차(선택, 타임박스 하루)**: `fetch_notion_entries_via_mcp()` — 오픈소스 MCP 서버 연동.
  하루 안에 안 되면 즉시 중단하고 1차안 유지

**중요(멀티유저 설계 결정, 9/10 확정)**: `NOTION_TOKEN`(`.env`)은 로컬 개발용 폴백일 뿐,
배포된 앱에서는 **각 사용자가 프론트엔드에서 자기 Notion 통합 토큰을 직접 입력**해서
`fetch_notion_entries(user_token=...)`을 호출한다 (`src/frontend/app.py` col_notion 참고,
이미 반영됨). 즉:
- `user_token` 파라미터를 절대 optional 취급해서 내부적으로 `settings.notion_token`에
  암묵적으로 의존하는 로직을 프로덕션 경로에 넣지 말 것 (다른 사용자가 토큰 없이
  개발자 본인 노션 데이터를 끌어오는 사고로 이어짐). `settings.notion_token` 폴백은
  로컬 단독 테스트용으로만 남겨둔다.
- 토큰별로 별도 Notion 클라이언트 인스턴스를 써야 하므로, 모듈 전역에 클라이언트를
  캐싱하지 말 것 (Track A의 `_get_client()` 같은 `lru_cache` 패턴을 그대로 쓰면 안 됨).

## 작업 항목
- [x] `data/mock_jds/*.json` 최소 15개 작성 — 20개 준비 완료 (9/10, Track A 버퍼 시간에 선작업).
  스키마(`company`/`title`/`required_skills`/`description`) 검증 통과, 고유 스킬 태그 66개.
- [x] Chroma 인덱스 빌드 스크립트 및 재현성 확인 (재실행해도 같은 결과) — 9/10 조기 착수, 구현 완료
- [x] `run_pipeline()` 통합 테스트 (Track A 결과물과 실제로 연결해서 검증) — 9/10 완료
- [ ] Notion REST API 연동 (개인 워크스페이스 토큰으로 테스트) — 예정대로 9/13 진행
- [ ] (선택) Notion MCP 연동 시도 — 타임박스 초과 시 중단 기록을 `docs/03-risk-fallback.md`에 남길 것

## 완료 기준
- [x] `run_pipeline(raw_text)` 호출 하나로 파싱+매칭 결과가 나온다 — 확인 완료 (아래 검증 내용 참고)
- [ ] 노션 연동은 최소 REST API 경로 하나는 반드시 동작해야 함 — 9/13 예정

## 벡터 매칭 구현 노트 (9/10, 일정보다 3일 당겨서 조기 착수)

**임베딩 provider 이원화** (`src/config.py`의 `EMBEDDING_PROVIDER`):
- `chroma_default`(기본값, 배포용): Chroma 내장 ONNX 임베딩(all-MiniLM-L6-v2, 영어 위주).
  외부 서버 불필요해서 배포 환경에서 그대로 동작하지만, 한국어 스킬 태그 의미 매칭 품질은
  검증 안 됨 — **Track D 배포 전 반드시 실제 품질 확인 필요**.
- `ollama`(로컬 개발용): 로컬 Ollama의 `bge-m3`(다국어, 1024차원) 사용. 로컬에서 수동 검증한
  결과 한국어 스킬 태그 매칭 품질이 좋음 (예: "장애대응/결제시스템/트러블슈팅" → 가상핀테크
  결제 백엔드 공고가 1순위로 정확히 매칭, "DB최적화/인덱스관리/쿼리튜닝" → 가상데이터랩
  DB 엔지니어 공고가 1순위). `run_pipeline()`으로 Track A와 연결한 통합 테스트도 확인함.
  단, 배포 환경엔 로컬 Ollama 서버가 없으므로 **프로덕션에서는 쓸 수 없음** — 로컬 개발/데모 전용.

**인덱스 빌드 시점**: `pipeline.py` 모듈 임포트 시 `build_jd_index()`를 1회 자동 호출해서
`match_jds()`가 "인덱스 미구축" 에러를 신경 쓸 필요 없게 함 (upsert 기반이라 재실행 안전).
단, 임베딩 서버 연결 실패 시 앱 전체가 죽지 않도록 try/except로 감싸뒀음 — 이 경우
`match_jds()`는 원래 계약대로 `RuntimeError`를 던진다.

**패키지 버전**: `requirements.txt`의 `chromadb`를 `0.5.15` → `1.5.9`로 상향함 (Python 3.14 로컬
환경에서 구버전이 numpy 빌드 실패로 설치 자체가 안 됐음). Chroma의 커스텀 임베딩 함수 API가
버전 간 다르니(`EmbeddingFunction[Documents]`를 명시적으로 상속해야 `embed_query`가 자동
제공됨), 다른 Python/chromadb 버전 조합에서 재검증 필요.

**테스트**: `tests/test_vectorstore.py`에 Track A와 동일한 패턴(외부 호출부 모킹)으로 4개
작성 — bag-of-words 가짜 임베딩으로 오프라인/결정론적 검증 (인덱스 미구축 에러, 스키마,
유사도 매칭, 멱등성). 전체 `pytest tests/` 9개 통과.
