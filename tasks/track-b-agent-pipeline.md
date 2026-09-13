# Track B — 데이터 계층 및 에이전트 파이프라인

> **2026-09-13 개정.** 벡터 매칭과 파이프라인은 완료. 이번 개정으로 **저장소와 프로젝트 층이
> 추가**됐고, 이것이 P0 1순위다. 현재 앱은 `st.session_state`만 쓰고 있어 새로고침하면
> 모든 카드가 소실된다. 누적이 없으면 제품이 성립하지 않는다.

---

# 1부 — 저장소 (신규, P0 1순위)

## 목표
카드와 프로젝트를 영속 저장한다. SQLite로 충분하다.
OCI VM의 로컬 디스크는 재시작해도 유지되므로 별도 클라우드 DB는 불필요하다.

## 스키마
```sql
CREATE TABLE projects (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    ended_at    TEXT,
    is_current  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE cards (
    id               INTEGER PRIMARY KEY,
    project_id       INTEGER REFERENCES projects(id),
    raw_text         TEXT NOT NULL,
    refined_sentence TEXT NOT NULL,
    skill_tags       TEXT NOT NULL,   -- JSON 배열
    confidence       REAL,
    created_at       TEXT NOT NULL
);
```

`is_current`는 한 번에 하나만 1이어야 한다. `set_current_project()`에서 기존 값을 0으로
초기화한 뒤 설정할 것.

## 인터페이스 계약
```python
# src/storage/db.py
@dataclass
class Card:
    id: int; project_id: int | None
    raw_text: str; refined_sentence: str
    skill_tags: list[str]; confidence: float; created_at: str

@dataclass
class Project:
    id: int; name: str
    started_at: str; ended_at: str | None; is_current: bool

def save_card(project_id: int | None, parsed: ParsedEntry, created_at: str) -> int
def list_cards(project_id: int | None = None) -> list[Card]
def create_project(name: str, started_at: str) -> int
def list_projects() -> list[Project]
def set_current_project(project_id: int) -> None
def get_current_project() -> Project | None
```

## 작업 항목
- [x] `src/storage/db.py` 생성, 스키마 초기화 루틴 (`CREATE TABLE IF NOT EXISTS`) — 9/13
- [x] 위 6개 함수 구현 — 9/13
- [x] `skill_tags` JSON 직렬화/역직렬화 처리 — 9/13
- [x] `data/seed_cards.json` 로더 — 9/13, `db.load_seed_cards()`로 구현.
  실기기 없이도 확인 가능한 시드 데이터(B카드 시스템 구축 2건 + A은행 차세대 3건,
  02.14 조치/03.02 결과 시간차 페어 포함)를 함께 준비함
- [x] `tests/test_db.py` — CRUD + `is_current` 유일성 + 시드 로더 검증, 8개 전부 통과 — 9/13

### 구현 노트 (9/13)
- `DB_PATH`(`src/config.py`, 기본값 `data/app.db`)로 경로 관리. `data/app.db`는 실행 시
  생성되는 실데이터라 `.gitignore` 처리함(`data/seed_cards.json`은 예시 데이터라 커밋 대상).
- `create_project()`가 항상 새로 만든 프로젝트를 자동으로 `is_current`로 지정하므로,
  `load_seed_cards()`로 여러 프로젝트를 한 번에 넣을 때는 **JSON에 나열하는 순서가
  중요하다** — 마지막 항목이 자동으로 현재 프로젝트가 된다. `data/seed_cards.json`은
  종료된 프로젝트(B카드)를 먼저, 진행 중인 프로젝트(A은행)를 마지막에 둬서 이걸 활용함.

---

# 2부 — 프로젝트 층 (신규, P0 3순위)

## 왜 필요한가 (CLAUDE.md 3장 참조)

SI처럼 고객사를 옮겨 다니면 A은행의 "결제 API 개선"과 B카드의 "결제 API 개선"은
내용이 거의 같아도 **경력기술서에 별개로 들어가야 한다.** 내용 유사도로는 구분이
원천적으로 불가능하다 — 문장이 실제로 비슷하기 때문이다.

그래서 **바깥 상자는 유저가 만들고, 그 안의 작업 묶음만 AI가 만든다.**

## 동작 규칙
- 새 카드는 `is_current=1`인 프로젝트에 **자동 배정**된다. 유저는 아무것도 안 한다
- 유저는 프로젝트가 바뀌는 날에만 새로 만든다 (SI 기준 연 1~3회)
- 프로젝트가 하나도 없으면 `project_id=NULL`로 저장하고, 나중에 일괄 배정 가능하게 둔다
  (자사 서비스 개발자는 프로젝트 개념이 필요 없을 수 있음)

## 금지 사항
- 매 입력마다 프로젝트를 고르게 하지 말 것 (CLAUDE.md 2.1 위반)
- 폴더 이동/병합/중첩 같은 CRUD 고도화 금지 (2.4 위반)

## 작업 항목
- [x] `run_pipeline()`이 현재 프로젝트를 조회해 자동 배정하도록 수정
- [x] 프로젝트 없음(NULL) 상태 정상 동작 확인 — `get_current_project()`가 `None`이면
      `project_id=NULL`로 저장 (`test_run_pipeline_saves_card_with_null_project_when_no_current_project`)

---

# 3부 — 파이프라인 개편

## 변경점

**기존**: 메모 입력할 때마다 `parse_note()` → `match_jds()`를 같이 실행
**변경**: 매일 쓰는 경로에서 JD 매칭을 **분리**한다

JD 매칭은 이직 준비 시점에만 필요한데 매 입력마다 벡터 쿼리를 돌리는 건 낭비다.
입력 경로는 가볍게 유지하고(2.1 원칙), 매칭은 초안 생성 시점으로 옮긴다.

```python
# 매일 경로 — 가볍게
def run_pipeline(raw_text: str) -> dict:
    """parse_note() → save_card(). JD 매칭은 하지 않는다."""

# 이직 준비 경로 — 무겁게
def build_career_doc(project_id: int, jd_text: str | None = None) -> list[StarItem]:
    """list_cards() → build_resume(). jd_text 있으면 매칭 반영."""
```

## 작업 항목
- [x] `run_pipeline()`에서 `match_jds()` 호출 제거, `save_card()` 추가 — 9/13
- [x] `build_career_doc()` 신규 — Track A의 `build_resume()` 호출 — 9/13
- [x] 기존 통합 테스트 수정 — `tests/test_pipeline.py` 신설(6개 케이스: 프로젝트 자동
      배정, NULL 프로젝트 폴백, match_jds 미호출 검증, batch, build_career_doc 위임/jd_text
      전달). 이전에는 pipeline 전용 테스트 파일이 없었음(vectorstore.match_jds()가
      pipeline.py 임포트 시점에 인덱스를 구축하던 구조라 별도 유닛 테스트가 없었다)

### 구현 노트 (9/13)
- `run_pipeline()`의 반환 스키마에서 `matched_jds` 키가 사라졌다. 기존 Streamlit
  프론트(`src/frontend/app.py`)는 `.get("matched_jds", [])`로 읽고 있어 에러 없이
  빈 목록으로 동작하지만, 더 이상 채워지지 않는다 — 의도된 변경(Track C 확인 필요).
- 모듈 임포트 시점에 `build_jd_index()`를 호출하던 구 코드를 제거했다. 매일 쓰는
  경로가 더 이상 벡터 인덱스에 의존하지 않으므로, 임베딩 서버 연결 실패가 앱
  임포트 자체를 위협하지 않게 됐다(기존에는 warning으로 방어하던 리스크였음).

---

# 4부 — 벡터 매칭 (완료, 유지)

## 완료 사항
- [x] `data/mock_jds/*.json` 20개, 고유 스킬 태그 66개
- [x] `build_jd_index()` 멱등 구현
- [x] `match_jds()` 구현 및 테스트 4개
- [x] `tests/test_vectorstore.py` 통과

## 임베딩 provider 이원화 (유지)
- `chroma_default`(배포용): Chroma 내장 ONNX(all-MiniLM-L6-v2, 영어 위주).
  **한국어 매칭 품질 미검증 — 배포 전 반드시 실제 품질 확인**
- `ollama`(로컬): `bge-m3` 다국어. 한국어 품질 좋음이 수동 검증됨. 프로덕션 사용 불가

> **OCI 전환으로 생긴 선택지**: OCI VM에는 Ollama를 직접 설치할 수 있다.
> ARM 무료 티어(4 OCPU / 24GB)면 `bge-m3` 임베딩 정도는 충분히 돈다.
> 한국어 매칭 품질이 데모에 중요하다면 검토할 가치가 있다. 단 **P0 완료 후에만.**

## 신규 작업 — JD 붙여넣기 (P1)
- [x] 유저가 붙여넣은 JD 텍스트를 받는 경로 추가 — `POST /api/resume`의 `jd_text` 필드 (6부)
- [x] `build_resume(cards, jd_text=...)`로 전달 — `build_career_doc()` 경유
- [x] **URL 크롤링은 구현하지 않는다** (CLAUDE.md 2.4) — 계약 문서에 URL 필드 자체가 없음

## 신규 작업 — 카드 기반 JD 매칭 (P1, 9/13)
`GET /api/jds/match?card_id=&top_k=` 구현 완료 (`src/api/routers/jds.py`).
- [x] 카드 id로 스킬 태그 조회 (`db.get_card()` 신규 추가 + 테스트 2개)
- [x] 인덱스는 라우터 최초 호출 시 지연 구축 후 프로세스 동안 재사용 (모듈 전역 플래그)
      — 9/13 파이프라인 개편으로 일상 경로가 인덱스에 안 기대는 원칙을 API 레이어에서도 유지
- [x] `match_jds()`에 `score`(0~1, distance 기반) 필드 추가 — 계약 문서 4장 응답 스키마 충족
- [x] 스킬 태그가 없는 카드(모호한 입력)는 매칭 시도 없이 빈 목록 반환
- [x] `tests/test_api_jds.py` 4개 케이스 + `tests/test_vectorstore.py`에 score 검증 1개 추가
- [x] 실제 Ollama(bge-m3) + Chroma로 라이브 검증 — Redis/성능최적화/결제시스템 태그 카드가
      Spring Boot·Redis 요구 공고, 결제 플랫폼 공고 순으로 합리적인 score와 함께 매칭됨

---

# 5부 — 노션 연동 (진행 중)

## 멀티유저 설계 결정 (유지)
`NOTION_TOKEN`(`.env`)은 **로컬 개발용 폴백일 뿐**이다. 배포 환경에서는 각 사용자가
자기 통합 토큰을 직접 입력해 `fetch_notion_entries(user_token=...)`을 호출한다.

- `user_token`을 optional 취급해 `settings.notion_token`에 암묵적으로 의존하는 로직을
  **프로덕션 경로에 절대 넣지 말 것.** 다른 사용자가 개발자 본인 노션 데이터를 끌어오는
  사고로 이어진다
- 토큰별 별도 클라이언트를 써야 하므로 **모듈 전역 캐싱 금지** (`lru_cache` 패턴 금지)

## 작업 항목
- [x] Notion REST API 연동 (읽기) — `POST /api/notion/sync` (`src/api/routers/notion.py`, 9/13)
      HTTP 레이어만 신규 추가. `fetch_notion_entries()` 자체는 이전부터 구현돼 있었음
- [x] **노션 쓰기는 구현하지 않는다** (CLAUDE.md 2.4) — 내보내기는 클립보드 복사로 처리
- [ ] (선택) MCP 연동 — 타임박스 하루, 초과 시 중단 기록. 미착수(선택 사항)

### 구현 노트 (9/13, `POST /api/notion/sync`)
- `user_token`은 빈 문자열도 "값 없음"으로 취급해 422로 거부한다 — Pydantic의 `str`
  타입은 빈 문자열을 통과시키므로, 스키마만으로는 "필수" 검증이 안 돼 라우터에서
  `.strip()` 체크를 추가했다. **`settings.notion_token`으로 암묵 폴백하지 않는다**는
  원칙(위 "멀티유저 설계 결정")을 API 경계에서도 지키기 위함.
- 계약 문서(5장)는 `page_id`를 요청 필드로 보여주지만, `fetch_notion_entries()`는
  특정 페이지 하나만 골라오는 기능이 없고 이 토큰과 공유된 페이지 전체를 가져온다.
  `page_id`는 스키마에 받되 아직 미사용 — 필요해지면 `notion_client.py`부터 확장 필요
  (`src/api/schemas.py`의 `NotionSyncRequest` docstring에도 기록).
- 본문이 빈 페이지는 `parse_note()`에 넘길 근거가 없어 가져오기 단계에서 건너뛴다.
- 실제 Notion 토큰으로 라이브 검증은 못 함(테스트용 유효 토큰 없음) — 대신 라이브
  서버에 빈 토큰(422)과 잘못된 토큰(401, 실제 Notion API가 거부하는 것까지 확인)
  두 에러 경로는 실제로 호출해 검증함. 성공 경로는 유닛 테스트(모킹)로만 검증.

---

# 6부 — FastAPI 래핑 (신규, P0 3순위 마무리, 9/13)

## 목표
기존 파이썬 로직(1~4부)에 얇은 HTTP 레이어만 씌운다. 로직은 재구현하지 않는다.
`docs/05-api-contract.md` 1~3, 8절(카드/프로젝트/경력기술서/헬스체크)을 구현했다.

## 구현 위치
- `src/api/main.py` — FastAPI 앱, CORS(환경변수 `CORS_ALLOWED_ORIGINS`, 기본값 `*`)
- `src/api/schemas.py` — Pydantic 모델. dataclass(Card/Project/StarItem)와 필드명을
  1:1로 맞춰 `model_validate()`(from_attributes)로 바로 변환
- `src/api/routers/{cards,projects,resume,health,jds,notion}.py`

## 계약 문서와의 알려진 차이 (조율 없이 임의 변경하지 않음)
- **`created_at` 포맷**: 계약 문서 예시는 타임존 포함 ISO datetime
  (`"2026-02-14T18:45:00+09:00"`)이지만, 실제 저장소(`save_card`/`run_pipeline`)는
  `date.today().isoformat()`로 **날짜만**(`"2026-02-14"`) 기록한다. `db.py`/`pipeline.py`
  계약을 조율 없이 바꾸지 않기 위해 API는 저장된 값을 그대로 반환한다. 프론트가 시각까지
  필요하면 저장소 쪽 변경을 먼저 논의할 것.
- **`GET /api/cards` 정렬**: `list_cards()`는 내부 계약(오래된 순, `build_resume()`이
  시간순 입력을 기대함)을 유지해야 해서 그대로 두고, 라우터에서만 응답 직전에 뒤집어
  계약 문서가 요구하는 최신순을 맞췄다.
- `db.py`에 `delete_card()`, `update_project()`를 최소 구현으로 추가(각각 테스트 포함).
  `update_project()`는 계약 문서 2장이 보여주는 `name`/`ended_at`/`is_current` 3개
  필드만 API 스키마로 노출한다(2.4 원칙 — 폴더 CRUD 고도화 금지).

## 남은 P1 (`src/api/main.py` 하단 TODO 참고)
- `POST /api/stt` (6장) — 9/13 실기기 음성 검증 결과가 아직 없어 보류
- `POST/DELETE /api/push/subscribe` (7장) — `src/push/subscription_store.py` 연결만 하면 됨, 미착수

## 테스트
`tests/test_api_cards.py`, `tests/test_api_projects.py`, `tests/test_api_resume.py`,
`tests/test_api_jds.py`, `tests/test_api_notion.py`.
`FastAPI TestClient` + LLM/Notion/vectorstore 모킹 + 격리된 임시 SQLite, 기존 패턴 그대로.

---

## 완료 기준
- [x] 앱 재시작 후에도 카드가 남아 있다 — SQLite 영속화(1부)로 확인됨
- [x] 현재 프로젝트에 새 카드가 자동 배정된다 — `test_run_pipeline_auto_assigns_new_card_to_current_project`
- [x] `build_career_doc()` 호출 하나로 STAR 항목 리스트가 나온다
- [x] FastAPI로 카드/프로젝트/경력기술서/헬스체크 P0 엔드포인트가 동작한다 (6부)
- [x] 노션 REST 경로 하나는 동작한다 (5부) — `POST /api/notion/sync`, 에러 경로(422/401)는
      라이브 서버로도 검증, 성공 경로는 유닛 테스트로 검증
- [x] JD 매칭 HTTP 엔드포인트 — `GET /api/jds/match`, 실제 Ollama+Chroma로 라이브 검증 완료
- [ ] STT/푸시 HTTP 엔드포인트는 아직 없음 (P1, 위 "남은 P1" 참고 — 실기기 음성 검증 대기 중)
