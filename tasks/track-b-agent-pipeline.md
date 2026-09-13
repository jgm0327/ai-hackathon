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

## chroma_default 한국어 품질 검증 및 다국어 임베딩 대안 (9/13)

Track D 배포 전 반드시 확인이 필요하다고 남겨뒀던 `chroma_default`(Chroma 내장 ONNX
all-MiniLM-L6-v2)의 한국어 스킬 태그 매칭 품질을 실제로 검증했다. 검증 환경: venv +
`chromadb`/`requests`/`python-dotenv`/`pytest`/`anthropic`만 설치, `EMBEDDING_PROVIDER`는
기본값(`chroma_default`) 그대로. `data/mock_jds/*.json` 20개를 `build_jd_index()`로
인덱싱하고 아래 4개 한국어 스킬 태그 쿼리로 `match_jds(top_k=5)`를 직접 호출했다.

### 결과 요약 (chroma_default, top-1 기준)

| 쿼리 | chroma_default 1순위 | 기대(정답) 공고 | 판정 |
|---|---|---|---|
| 장애대응/결제시스템/트러블슈팅 | 가상뱅크(백엔드 개발자·인증) | 가상핀테크/가상페이먼츠(결제) | **오답** — 결제 관련 공고가 top-5에서 완전히 누락(가상핀테크), 인증 도메인이 1순위로 나옴 |
| 동시성제어/코드리뷰/버그해결 | 가상스타트업(신입 백엔드) | 가상클라우드(동시성제어) 등 | 애매 — 코드리뷰/버그수정은 근접하지만 동시성제어 정답 공고(가상클라우드)는 top-5에서 완전히 누락 |
| React/상태관리/성능최적화 | 가상테크(프론트엔드, React/상태관리/성능최적화 정확히 일치) | 가상테크 | **정답** |
| DB최적화/인덱스관리/쿼리튜닝 | 가상보안(보안 엔지니어) | 가상데이터랩(DB최적화 등 4개 스킬 정확히 일치) | **오답** — 정답 공고가 2순위로 밀림, 완전히 무관한 보안 공고가 1순위 |

4개 쿼리 중 2개(장애대응/결제시스템, DB최적화)에서 명백히 무관한 공고가 1순위로 나왔고,
한 쿼리(동시성제어)는 스킬 태그를 정확히 포함한 공고가 top-5에서 아예 빠졌다. 영어
로마자 태그가 섞인 React 쿼리만 정확히 매칭됐는데, 이는 all-MiniLM-L6-v2가 영어 위주
모델이라 한글 토큰 임베딩 품질이 낮기 때문으로 보인다.

**로컬 Ollama(bge-m3) 결과와 비교** (위 "벡터 매칭 구현 노트" 기록 기준): bge-m3는 동일한
장애대응/결제시스템/트러블슈팅 쿼리에서 가상핀테크를 1순위로 정확히 매칭했고,
DB최적화/인덱스관리/쿼리튜닝 쿼리에서도 가상데이터랩을 1순위로 정확히 매칭했다.
즉 **chroma_default는 실사용에 문제될 정도로 한국어 품질이 낮다** — 결제/DB 도메인처럼
사용자 낙서에서 흔히 나올 법한 스킬 태그 조합에서 완전히 무관한 공고를 1순위로 추천하는
것은 데모 신뢰도에 직접 타격을 준다.

### 다국어 임베딩 대안 검증: sentence-transformers 로컬 로드

서버 없이(로컬 프로세스 안에서 모델 가중치를 직접 로드) 쓸 수 있는 다국어 모델을
찾기 위해 `sentence-transformers`의 `paraphrase-multilingual-MiniLM-L12-v2`를
Chroma 커스텀 `EmbeddingFunction`으로 붙여서 동일한 4개 쿼리로 재검증했다.

**결과** (top-1 기준): React/상태관리/성능최적화 → 가상테크(정확), DB최적화/인덱스관리/
쿼리튜닝 → 가상데이터랩(정확, bge-m3와 동일), 장애대응/결제시스템/트러블슈팅 →
가상페이먼츠(결제 플랫폼 엔지니어, 결제시스템/장애대응 일치 — 도메인상 올바른 결제
공고이며 가상핀테크도 3순위로 근접 등장), 동시성제어/코드리뷰/버그해결 → 가상서비스
(고객지원 엔지니어, 완전 일치는 아니지만 chroma_default처럼 전혀 무관한 도메인은 아님).
즉 4개 쿼리 모두 "무관한 도메인이 1순위로 나오는" chroma_default의 실패 패턴이
사라졌고, 2개는 bge-m3와 동일하게 완전히 정확했다.

**검증 중 발견한 이슈(중요, 재현 시 참고)**: 이 로컬 Windows 검증 환경에서
`sentence-transformers`를 설치하면 딸려오는 `scipy`(1.18.1)/최신 `scikit-learn`의
컴파일된 DLL(`scipy.linalg._decomp_interpolative`, `sklearn.utils._isfinite` 등)이
"애플리케이션 제어 정책"에 의해 로드 자체가 차단되는 문제가 있었다 (`ImportError: DLL
load failed ... 애플리케이션 제어 정책에서 이 파일을 차단했습니다`). `scipy==1.16.2`,
`scikit-learn==1.7.2`로 버전을 낮춰 설치하니 문제없이 동작했다. 다른 환경(특히 실제
배포 환경인 Linux 기반 Streamlit Community Cloud)에서는 재현되지 않을 가능성이 높지만,
로컬에서 이 provider를 재검증할 다른 에이전트/사람을 위해 `requirements.txt`에 주석으로
남겨뒀다.

**결론**: `_get_embedding_function()`에 `local_multilingual` provider를 추가했다
(`src/agent/vectorstore.py`의 `_LocalMultilingualEmbeddingFunction`). 이 provider는
Ollama와 달리 별도 서버가 필요 없으므로(모델을 최초 1회 다운로드해 로컬 캐시에 저장한 뒤
in-process로 추론) "배포 기본값은 서버가 필요 없어야 한다"는 원칙에 위배되지 않는다.
다만 `EMBEDDING_PROVIDER`의 실제 **기본값은 `chroma_default`로 그대로 유지**했다 —
`sentence-transformers`(+torch) 의존성이 무겁고(설치 용량·메모리 사용량 큼), 무료 티어인
Streamlit Community Cloud의 빌드/메모리 제약에 걸릴 위험이 있어서, 배포 리소스 상황을
직접 확인할 Track D가 기본값 전환 여부를 최종 판단하는 게 맞다고 봤다. 요약하면:
- 로컬 개발/정확도 최우선: `EMBEDDING_PROVIDER=ollama` (bge-m3, 서버 필요, 품질 최상)
- 서버 없이 한국어 품질 개선이 필요하면: `EMBEDDING_PROVIDER=local_multilingual`
  (`pip install sentence-transformers` 추가 필요, 의존성 무거움)
- 아무 설정도 안 하면(배포 기본값): `chroma_default` — 서버/추가 설치 불필요하지만
  한국어 품질이 검증상 실사용에 부족함이 확인됨. **Track D는 배포 전 반드시
  `local_multilingual`로 전환할지, 아니면 품질 저하를 감수하고 `chroma_default`를
  유지할지 결정해야 한다.**

**테스트**: `tests/test_vectorstore.py`에 `TestGetEmbeddingFunction` 클래스로 4개 추가
(chroma_default/ollama/local_multilingual provider 선택 로직, `sentence-transformers`
미설치 시 명확한 ImportError). 실제 모델 다운로드 없이 가짜 모듈로 결정론적 검증.

## 사람인(Saramin) 오픈API 클라이언트 스캐폴드 (9/13)

사람인 오픈API 키가 승인 대기 중이라 실제 호출 없이 스캐폴딩만 준비해뒀다.
`src/agent/saramin_client.py`의 `fetch_saramin_jobs(keywords, count=50, access_key=None)`가
`GET https://oapi.saramin.co.kr/job-search` 응답(`jobs.job` 배열)을 `data/mock_jds/*.json`과
동일한 스키마(`company`/`title`/`required_skills`/`description`)로 매핑한다.
`access_key` 미지정 시 `settings.saramin_api_key`(`SARAMIN_API_KEY` env, `.env.example`에
추가함)를 쓰고, 둘 다 없으면 `ValueError`. 하루 호출 한도(500회)가 있어 분석 요청마다
실시간 호출하면 안 된다는 점, 캐싱 전략이 필요하다는 점을 모듈 docstring에 명시했다
(실제 캐싱 로직은 이번 스캐폴드 범위 밖).

**테스트**: `tests/test_saramin_client.py` — 실제 API 스펙 문서의 응답 예시로
`requests.get`을 모킹해 스키마 매핑, 키 없을 때 에러, `settings` 폴백, 빈 결과 처리를
검증 (`tests/test_notion_client.py`와 동일한 모킹 패턴). 4개 모두 통과.
