# CLAUDE.md — 원티드 AI 해커톤: 커리어 로그

이 문서는 이 레포에서 작업하는 모든 코딩 에이전트(Claude Code, Orca worktree 인스턴스 포함)가
가장 먼저 읽어야 하는 최상위 컨텍스트다. 세부 작업 지침은 `tasks/`, 배경 설계는 `docs/`를 참고한다.

> **2026-09-13 대폭 개정.** 제품 방향과 기술 스택이 모두 바뀌었다.
> 이전 버전의 "온보딩 다이어리 / Streamlit / Streamlit Cloud"를 전제한 코드와 문서는
> 전부 이 문서 기준으로 재검토할 것. 이식 절차는 `docs/06-migration.md`.

---

## 1. 프로젝트 한 줄 요약

유저가 퇴근 직전 대충 남긴 업무 낙서("결제 터진 거 막음")를 쌓아두었다가,
**이직이 필요한 순간에 프로젝트 단위로 묶어 완성된 경력기술서로 변환해주는 서비스.**

핵심 가치는 단건 변환이 아니라 **시간차 누적**에 있다.
2월에 쓴 "레디스 붙임"과 3월에 쓴 "오류율 0.8% → 0.3%"가 하나의 STAR 문장으로 합쳐지는 것 —
이것이 제품의 유일한 결정적 순간이고, 모든 설계 판단은 이 장면을 지키는 쪽으로 내린다.

**사용 맥락 2가지** (기능 판단 시 이 둘 중 하나를 만족해야 한다)
1. 퇴근 15분 전, 자리에서 한 줄 타이핑
2. 자차 출퇴근 중, 폰으로 음성 입력

2번 때문에 모바일은 포기 불가다. 이것이 Streamlit을 걷어낸 근본 이유다.

---

## 2. 절대 원칙 (기능 판단의 기준선)

기능을 넣을지 말지 헷갈리면 이 네 개로 판단한다.

### 2.1 평소 입력 비용은 0이어야 한다
슬로건은 **"3초 만에 끝내고 모니터 끄기"**다.
매일 반복되는 경로(메모 입력 → 변환)에 선택지·드롭다운·분류 작업을 추가하지 않는다.
유저에게 무언가를 고르게 하려면 그 빈도가 **월 1회 이하**여야 한다.

### 2.2 숫자를 지어내지 않는다
경력기술서는 면접에서 검증당하는 문서다.
**유저가 기록에 쓰지 않은 수치는 어떤 경우에도 생성하지 않는다.**
숫자가 없으면 결과 항목을 비우거나, 유저에게 되묻는다(건너뛰기 가능).
이 원칙을 깨는 프롬프트는 리뷰에서 반려한다.

### 2.3 분류는 임베딩, 묶기는 LLM
- **임베딩**: 새 카드를 기존 작업 그룹에 배정 (보조적, 틀려도 손해 작음)
- **LLM**: 조치와 결과를 인과로 묶기 (핵심, 임베딩으로는 원천적으로 불가)

임베딩은 "비슷한가"를 보고 LLM은 "이어지는가"를 본다.
시간차 두고 나온 결과 문장("지난달 캐싱 작업 이후로 지표 좋아짐")은 조치 문장과
어휘가 겹치지 않으므로 유사도로 못 묶는다. 이 구분을 흐리지 말 것.

### 2.4 스코프 확장 금지 목록
아래는 논의를 거쳐 **의도적으로 배제**한 것들이다. 다시 제안하지 말 것.

| 배제 항목 | 사유 |
|---|---|
| 채용공고 URL 크롤링 | 붙여넣기로 충분. 사이트별 파싱에 이틀 녹음 |
| Jira 연동 | 회사 계정 연동을 유저가 거부 + 관리자 승인 불가 |
| 노션 쓰기(write) | 읽기 + 클립보드 복사로 충분. OAuth 스코프 확대 부담 |
| 폴더 CRUD 고도화 | 프로젝트 생성/이름변경 최소 기능만 |
| 연차 직접 입력 | 세그먼트 4개(1-3/4-6/7-10/10년+)로 충분 |

---

## 3. 데이터 모델 (신규 — 이전 버전에 없던 층)

```sql
projects(id, name, started_at, ended_at, is_current)
cards(id, project_id FK, raw_text, refined_sentence,
      skill_tags JSON, confidence, created_at)
```

**프로젝트는 사람이 만들고, 그 안의 작업 묶음은 AI가 만든다.**

SI처럼 고객사를 옮겨 다니는 경우 A은행의 "결제 API 개선"과 B카드의 "결제 API 개선"은
내용이 거의 같아도 경력기술서에 별개로 들어가야 한다. 섞이면 경력이 반으로 줄어든다.
내용 유사도로는 이 구분이 원천적으로 불가능하므로 **바깥 상자(프로젝트)는 유저가 지정**한다.

`is_current`로 현재 상주 프로젝트를 표시하고 새 카드는 자동으로 거기 들어간다.
유저는 프로젝트가 바뀌는 날에만 손댄다(SI 기준 연 1~3회). 2.1 원칙을 지키는 설계다.

AI가 만드는 작업 묶음은 **DB에 저장하지 않는다.** 초안 생성 시점에 LLM이 그때그때 묶는다.
저장하면 관리 UI가 필요해지고 그 순간 2.1이 깨진다.

---

## 3.5 디자인 원본

```
https://www.figma.com/design/MbQqcE5hGWI5KXwT3OtvIb/Connecting-Dots
  node-id=10-2   기획 정리 (화면 흐름, 타임라인, 페르소나)
  node-id=41-10  화면 목업 (2.0 온보딩 ~ 4.2 빌더)
```

읽으려면 **Figma MCP 연결 + 편집자 권한**이 둘 다 필요하다. 뷰어 권한으로는 거부된다.
접근 방법과 화면 대응표는 `tasks/track-c-frontend.md` 3장.

> **Figma와 이 문서가 충돌하면 이 문서가 우선한다.**
> Figma 코멘트 핀의 논의 내용은 어떤 도구로도 읽을 수 없으므로(Plugin API에 comment 접근
> 자체가 없음), 거기서 나온 결정은 전부 문서로 옮겨져 있다. 프로젝트 층, JD 붙여넣기,
> 숫자 되묻기는 Figma에 그려져 있지 않지만 구현 대상이다.

---

## 4. 아키텍처

```
[브라우저]  Next.js — 화면, 마이크, PWA, 웹푸시
                ↓
[OCI VM]    nginx (TLS 종단, 리버스 프록시)
              ├─ /       → Next.js  (localhost:3000)
              └─ /api/   → FastAPI  (localhost:8000)
                             └─ SQLite + Chroma (로컬 디스크)
```

Streamlit을 걷어낸 이유는 iframe 제약이다. `components.html`이 만드는 샌드박스 iframe
안에서는 마이크 권한, 서비스워커 scope(`/app/static/` 하위로 제한), manifest 주입이
전부 정상 동작하지 않는다. 기존 `install_button.py` 주석이 이 실패를 스스로 기록하고 있다.

OCI 단일 VM에 상주 프로세스로 올리므로 **콜드 스타트와 디스크 유실 문제가 해소**된다.
`docs/03-risk-fallback.md`의 관련 조항은 이번 개정에서 삭제했다.

---

## 5. 트랙 구성 (worktree/브랜치)

> **진행 현황 (2026-09-14 갱신)**: 아래 표는 9/13 피벗 시점 기준 계획이다. 실제로는
> 같은 날 세션에서 P0 세 개(저장소/`build_resume()`/프로젝트 층+FastAPI)를 전부
> 끝냈고, 9/14엔 P1 라우터(JD 매칭/노션 REST+MCP), Track E/F 이식(마이크/PWA/웹푸시),
> 온보딩 프로필(`/onboarding`), Figma 디자인 반영(핵심 4화면)까지 마쳤다. 남은 건
> **Track D(OCI 배포)뿐**이며, 이건 실제 VM/도메인 접속 정보가 있어야 진행 가능하다.
> 실기기(iPhone/Android) 검증은 여전히 미완료 — CLAUDE.md 8장 참고. 세부 현황은 각
> `tasks/track-*.md`의 체크리스트가 최신 진실이다.

| 트랙 | 브랜치 | 범위 | 상태 |
|---|---|---|---|
| A | `track-a-prompt` | `parse_note()` + `build_resume()` | ✅ 완료 |
| B | `track-b-agent` | 저장소 + 프로젝트 층 + Chroma + Notion(REST+MCP) + FastAPI + 온보딩 프로필 | ✅ 완료 |
| C | `track-c-frontend` | Next.js — 화면 5개(+온보딩) + 마이크 + PWA + 웹푸시 + Figma 반영 | ✅ 완료, **실기기 검증 대기** |
| D | `track-d-deploy` | OCI + nginx (Streamlit Cloud 폐기) | ⬜ 미착수 — VM 접속 정보 필요 |
| E | `track-e-push` | 웹푸시 — 이식 완료 | ✅ 이식 완료, **실기기 수신 확인 대기** |
| F | `track-f-voice` | 음성 입력 — 이식 완료 | ✅ 이식 완료, **iOS 실기기 검증 대기** |

### 트랙 간 계약 (먼저 고정할 시그니처)

```python
# src/storage/db.py  — 신규
def save_card(project_id: int | None, parsed: ParsedEntry, created_at: str) -> int
def list_cards(project_id: int | None = None) -> list[Card]
def create_project(name: str, started_at: str) -> int
def list_projects() -> list[Project]
def set_current_project(project_id: int) -> None

# src/parsing/resume.py  — 신규, 제품의 핵심
@dataclass
class StarItem:
    title: str; period: str
    situation: str; task: str; action: str; result: str
    source_dates: list[str]      # 근거 추적용 — 반드시 반환할 것

def build_resume(cards: list[Card], jd_text: str | None = None) -> list[StarItem]
```

`source_dates`는 생략 불가다. 어느 카드에서 나온 문장인지 추적할 수 있어야
2.2 원칙(환각 금지) 위반을 검증할 수 있고, 유저에게 근거를 보여줄 수 있다.

**프론트/백 분리 이후 진짜 계약은 HTTP다.** `docs/05-api-contract.md`를 먼저 고정하고
Track C는 그 문서만 보고 작업한다.

---

## 6. 우선순위 (일정이 밀릴 경우 이 순서로 지킨다)

### P0 — 없으면 제품이 성립하지 않음
1. **저장소** — 현재 `st.session_state`뿐이라 새로고침 시 전부 소실. 누적이 없으면 제품이 없다
2. **`build_resume()`** — 여러 카드를 STAR로 묶는 기능. 현재 레포에 0줄
3. **프로젝트 층** — 테이블 + 스위처 UI

### P1 — 데모 임팩트
4. JD 붙여넣기 → 맞춤 재구성
5. 시드 데이터 (6.1 참조)

### P2 — 여유 시
6. 온보딩 (현재 직무 / 목표 직무 / 연차)
7. 숫자 되묻기 UI
8. 임베딩 자동 배정

### 6.1 시드 데이터 요구사항 (P1이지만 실질 필수)
`data/seed_cards.json`에 **프로젝트 2개 × 각각 조치/결과 페어 1쌍 이상**을 넣는다.

```
[A은행] 02.14 "결제 API 느려서 레디스 캐시 붙임"
        03.02 "레디스 붙인 뒤 결제 오류율 0.8% → 0.3%"   ← 시간차 필수
```

현재 목업 카드가 전부 02.13~02.18에 몰려 있어 **핵심 기능을 시연할 수 없다.**
시간차 페어가 없으면 발표에서 보여줄 장면이 사라진다.

---

## 7. 일정 (2026-09-13 기준, 마감 9/19 오후)

| 날짜 | 작업 | 게이트 |
|---|---|---|
| 9/13 (일) | **실기기 음성 테스트** + SQLite 저장소 | |
| 9/14 (월) | `build_resume()` STAR 생성 | |
| 9/15 (화) | 프로젝트 층 + FastAPI 래핑 | **P0 완료 확인** |
| 9/16 (수) | Next.js 프론트 | |
| 9/17 (목) | OCI + nginx 배포 | **배포 성공 확인** |
| 9/18 (금) | JD 매칭 + 시드 데이터 | |
| 9/19 (토) 오전 | 리허설 | |

**9/15 화요일이 분기점이다.** 이 시점에 P0 세 개가 안 끝났으면 프론트 전환을 중단하고
Streamlit으로 마감한다. 화면은 포기해도 제품은 남지만, 백엔드가 비면 보여줄 것이 없다.

배포는 마지막에 몰지 않는다. 9/16부터 매일 한 번씩 연습 배포할 것.

---

## 8. 선행 검증 (다른 작업보다 먼저 — 9/13 중 완료)

**실기기 음성 입력 테스트.**

```
1. 터널 또는 배포 주소를 실제 iPhone Safari로 접속
2. 음성 입력 버튼 → 마이크 권한 팝업이 뜨는가 / 인식되는가
3. Android Chrome으로 동일 테스트
```

| 결과 | 판단 |
|---|---|
| 양쪽 성공 | Web Speech API 유지 |
| iOS만 실패 | 브라우저 미지원. **녹음(`MediaRecorder`) + STT API로 전환** |
| 양쪽 실패 | iframe 문제 확정. Next.js 전환으로 해결됨 |

iOS 실패 시 UX가 "실시간 자막"에서 "녹음 버튼 하나"로 바뀐다.
화면 설계가 달라지므로 **디자인에 즉시 공유**할 것. 이 결과 전에 음성 화면을 확정하지 않는다.

---

## 9. 병렬 작업 규칙 (Orca / git worktree)

- 트랙 간 계약은 `src/` 하위 모듈의 **함수 시그니처와 docstring으로 먼저 고정**한 뒤 구현한다
- 프론트/백 분리 이후 API 계약은 `docs/05-api-contract.md`가 단일 진실 공급원이다.
  이 문서를 바꾸면 Track C에 즉시 알린다
- 병합 전 `tests/` 해당 트랙 테스트를 통과시킬 것
- 백엔드 공용 설정은 `src/config.py`와 `.env`, 프론트는 `.env.local`
- CORS 허용 origin은 하드코딩 금지, 환경변수로 관리

---

## 10. 에이전트 작업 체크리스트

- [ ] `docs/`와 해당 `tasks/track-*.md`를 읽었는가
- [ ] 2장의 **절대 원칙 4개**에 위배되지 않는가
- [ ] 매일 쓰는 경로에 유저 선택지를 추가하지 않았는가 (2.1)
- [ ] LLM 프롬프트에 "숫자를 추정하지 마라" 제약이 들어 있는가 (2.2)
- [ ] 2.4 금지 목록에 있는 기능을 다시 제안하고 있지 않은가
- [ ] 시그니처나 API 계약을 변경했다면 다른 트랙에 영향 없는지 확인했는가
- [ ] `.env.example`에 새 환경변수를 추가했는가 (실제 키는 커밋 금지)
- [ ] 리스크 구간에서 하루 이상 막히면 즉시 폴백으로 전환했는가

---

## 11. 이 개정에 따른 정리 대상

- [x] `CLAUDE.md` — 본 문서
- [x] `tasks/track-a-prompt-engine.md` — `build_resume()` 추가
- [x] `tasks/track-b-agent-pipeline.md` — 저장소·프로젝트 층 추가
- [x] `tasks/track-c-frontend.md` — Next.js로 재작성
- [x] `tasks/track-d-deploy.md` — OCI + nginx로 재작성
- [x] `docs/01-schedule.md` / `02-architecture.md` / `03-risk-fallback.md` — 재작성
- [x] `docs/05-api-contract.md` — 신규
- [x] `docs/06-migration.md` — 신규 (Track E/F 이식 절차)
- [x] `tasks/track-e-push-notifications.md` / `track-f-stt-voice-input.md`
      — 본문은 유지하고 상단에 `docs/06-migration.md` 참조 링크 추가함 (9/13)
- [x] `logs/` 신설 — 기존 `tasks/track-{a,b,c,d}.md`에 있던 트러블슈팅/회고 기록을
      개정으로 덮어쓰기 전에 `logs/track-{a,b,c,d}.md`로 이관해서 보존함 (9/13)
- [ ] `src/frontend/` — **아직 삭제하지 않음.** 파일 자체는 참고/폴백용으로 남겨두되,
      9/13~14 사이 게이트를 통과하고 Next.js가 실제로 기능적으로 완성돼 requirements.txt
      제거는 이미 진행함(아래 항목). 파일 자체의 최종 폐기는 OCI 배포 확정 후로 미룸 —
      iframe 우회 코드(`install_button.py` 등)는 이식하지 않는다
- [x] `manifest.json`, `README.md` — 제품명 갱신 (9/14). `web/app/manifest.ts`가
      "커리어 로그"로, `README.md`가 현재 아키텍처(Next.js+FastAPI+SQLite+Chroma) 기준으로
      전면 갱신됨
- [x] `requirements.txt` — streamlit/plotly/langchain 제거, fastapi/uvicorn 추가 (9/14).
      Next.js 전환이 실제로 완료·검증돼 제거 조건 충족으로 판단함
