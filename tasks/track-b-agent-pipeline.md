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
- [ ] `src/storage/db.py` 생성, 스키마 초기화 루틴 (`CREATE TABLE IF NOT EXISTS`)
- [ ] 위 6개 함수 구현
- [ ] `skill_tags` JSON 직렬화/역직렬화 처리
- [ ] `data/seed_cards.json` 로더 — 시드 투입 스크립트
- [ ] `tests/test_db.py` — CRUD + `is_current` 유일성 검증

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
- [ ] `run_pipeline()`이 현재 프로젝트를 조회해 자동 배정하도록 수정
- [ ] 프로젝트 없음(NULL) 상태 정상 동작 확인

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
- [ ] `run_pipeline()`에서 `match_jds()` 호출 제거, `save_card()` 추가
- [ ] `build_career_doc()` 신규 — Track A의 `build_resume()` 호출
- [ ] 기존 통합 테스트 수정

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
- [ ] 유저가 붙여넣은 JD 텍스트를 받는 경로 추가
- [ ] `build_resume(cards, jd_text=...)`로 전달
- [ ] **URL 크롤링은 구현하지 않는다** (CLAUDE.md 2.4)

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
- [ ] Notion REST API 연동 (읽기)
- [ ] **노션 쓰기는 구현하지 않는다** (CLAUDE.md 2.4) — 내보내기는 클립보드 복사로 처리
- [ ] (선택) MCP 연동 — 타임박스 하루, 초과 시 중단 기록

---

## 완료 기준
- [ ] 앱 재시작 후에도 카드가 남아 있다
- [ ] 현재 프로젝트에 새 카드가 자동 배정된다
- [ ] `build_career_doc()` 호출 하나로 STAR 항목 리스트가 나온다
- [ ] 노션 REST 경로 하나는 동작한다
