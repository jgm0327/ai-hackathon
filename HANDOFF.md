# 세션 인수인계 문서 (2026-09-15 기준)

> 새 Claude Code 세션에서 이 프로젝트를 이어갈 때 가장 먼저 읽을 문서. **`CLAUDE.md`를
> 이 문서보다 먼저(또는 같이) 읽을 것** — 제품 원칙(2장 절대 원칙, 3장 데이터 모델,
> 2.4 스코프 배제 목록)은 거기가 단일 진실 공급원이고, 여긴 "지금 상태 + 다음에
> 뭘 해야 하는지"만 담는다.

## 0. 마감/일정

마감 **9/19(토) 오후**, 오늘 9/15. Track D(OCI 배포) 100% 미착수, 실기기(iOS/Android)
검증 3종 미완료 — 사용자가 이미 인지한 상태로 Figma 재검토 작업을 우선 진행 중.

---

## 1. 저장소/브랜치/워크트리 구조 (★ 가장 먼저 이해할 것)

| 위치 | 브랜치 | 역할 |
|---|---|---|
| `C:\Users\user\Desktop\onboarding-hackathon` | `main` | **캔노니컬**. 여기의 `.env`, `data/app.db`(SQLite, 실사용자 데이터)가 유일한 진짜 상태 |
| `C:\Users\user\orca\workspaces\onboarding-hackathon\track-b-agent` | `onboarding-profile` | 백엔드(FastAPI/`src/`) 작업용 워크트리 |
| `C:\Users\user\orca\workspaces\onboarding-hackathon\track-c-frontend` | `figma-restyle` | 프론트(Next.js/`web/`) 작업용 워크트리 |

GitHub: `jgm0327/ai-hackathon` (origin). 커밋 메시지 끝에 `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` 붙이는 관례 유지 중.

### 표준 워크플로 (이번 세션 내내 이 순서로 진행함)
1. 해당 워크트리에서 코드 수정
2. 백엔드: `pytest` 통과 확인 / 프론트: `npm run lint` + `npm run build` 0 에러 확인
3. 워크트리에서 커밋 (heredoc으로 커밋 메시지 작성 — 백틱/한글 깨짐 방지)
4. Desktop `main`으로 이동 → `git merge <브랜치> --no-edit`
   - **주의**: Desktop main의 워킹카피에 같은 내용을 먼저 실험적으로 손댔다면
     `git checkout -- <파일>`로 되돌린 뒤 merge할 것(안 그러면 merge가 씹히거나
     충돌남 — 이번 세션에서 여러 번 겪은 패턴).
5. `git push origin main`
6. 워크트리로 돌아가 `git push origin <브랜치>`
7. **백엔드 코드를 고쳤으면 반드시 재기동** (아래 2절 참고 — auto-reload 없음)

---

## 2. 로컬 실행 환경

### 백엔드 (FastAPI, :8000)
```
cd "C:\Users\user\Desktop\onboarding-hackathon"
"C:\Users\user\orca\workspaces\onboarding-hackathon\track-b-agent\.venv\Scripts\python.exe" -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```
- **중요**: cwd가 `Desktop\onboarding-hackathon`이므로 `src.api.main`은 **Desktop main의
  코드**를 실행한다 — `track-b-agent`의 venv python.exe는 그냥 설치된 패키지를 빌려
  쓰는 것뿐, 코드 자체는 항상 main 기준. 그래서 백엔드 코드를 고치면 반드시
  **main에 merge까지 끝난 뒤** 재기동해야 반영됨.
- `--reload` 없음 → 코드 고치면 수동 재기동 필수. `data/app.db` 경로도 cwd 기준
  상대경로(`data/app.db`)라 항상 Desktop main의 DB.
- 이번 세션 종료 시점 상태: 정상 기동 중, 실제 `LLM_API_KEY`(.env의 진짜 키) 사용.
  (중간에 폴백 기능 검증하려고 일부러 잘못된 키로 재기동했다가 다시 정상 키로
  복구해뒀음 — `.env` 자체는 안 건드림, 셸 env var 오버라이드만 썼음.)

### 프론트엔드 (Next.js dev, :3001)
- **`track-c-frontend/web`에서 이미 `npm run dev`가 실행 중**이며 이게 **유일하게
  hot-reload되는 서버**다. Desktop main의 `web/` 디렉터리는 dev 서버가 안 붙어있어서
  거기만 고쳐봤자 브라우저에 반영 안 됨.
- **따라서 프론트 작업은 항상 `track-c-frontend`에서 먼저** 하고, 검증 끝나면
  Desktop main으로 merge하는 순서를 지킬 것 (반대로 하면 눈에 안 보여서 헷갈림 —
  이번 세션에서 실제로 이 문제로 한 번 되돌린 적 있음).

### DB 직접 조회/수정 (테스트 데이터 넣고 뺄 때)
```python
# track-b-agent의 venv python으로 실행 (cwd는 Desktop main)
import sqlite3
conn = sqlite3.connect('data/app.db')
```
- **콘솔에 한글이 깨져 보이는 건(예: `Redis\uf9e6...`) 실제 데이터 손상이 아니라
  Windows 콘솔 코드페이지 표시 문제일 뿐**이다 — 이번 세션에 여러 번 확인함
  (curl/API 응답으로 재확인하면 정상 UTF-8). 헷갈리지 말 것.
- 실제 유저: `user_id=1` (카카오 로그인, kakao_id `4251000635`). 실제 프로젝트
  `A은행 차세대`(id=1), `B은행 계정계`(id=2, 현재 프로젝트). 카드 5장 실존
  (`refined_sentence` 아이디만 참고 — 내용은 위 인코딩 문제로 여기 안 옮김, DB에서
  직접 확인).
- **테스트 세션 만들기** (API를 curl로 찌를 때):
  ```python
  from src.storage import db
  session = db.create_session(1, ttl_days=1)  # session.id를 쿠키로 사용
  # 반드시 db.create_session()을 쓸 것 — 직접 INSERT하면 expires_at 타임존 포맷이
  # 안 맞아서 500 남(get_session의 offset-aware/naive 비교에서 TypeError).
  ```
  검증 끝나면 `DELETE FROM sessions WHERE id=?`로 지울 것.
- **테스트로 만든 카드/프로젝트는 반드시 원복/삭제**(실사용자 데이터와 섞이면 안 됨)
  — 이번 세션 내내 지킨 원칙.

---

## 3. 이번 세션에서 완료된 작업 (요약, 최근 순)

전부 커밋/머지/푸시 완료, main에 반영됨.

00. **(9/18 세션) Figma 전수 재조사 후 남은 미구현 화면 구현** — 아직 커밋 안 함.
    캔버스 `10:2` 산하 화면 39개를 현재 `web/`과 1:1 대조해서 나온 갭 4종:
    - **4.2.1 범위 선택**(`89:161`) — `/resume`가 현재 프로젝트 하나에 고정돼 있어
      `/stack`의 "마스터 경력기술서 초안 짜기" 버튼이 실제로는 마스터가 아니었다.
      `POST /api/resume`에 `project_ids`/`include_unassigned` 추가(프로젝트마다 따로
      `build_resume()` — 합치면 CLAUDE.md 3장 위반), 결과에 프로젝트 헤드(`41:254`)
      표시, 범위 여러 개인 문서의 초안은 `master_resume_drafts`(유저당 1개)에 저장.
    - **4.1-b 기록 상세**(`89:479`) — `/stack/<id>` 신규. 주제(대표 태그+프로젝트)별
      타임라인 + "이 주제에 이어 쓰기"(`/?topic=`).
    - `/`의 이어 쓰기 배너(`41:119`)·타깃 트랙 칩(`41:116`)·노션 링크(`41:128`),
      복사 완료 토스트(`41:880`).
    - 설정 백업 내보내기/불러오기(`41:333`/`41:338`) — `GET /api/backup` +
      `POST /api/backup/import` 신규. 불러오기는 LLM을 안 타고 **덧붙이기만** 한다.

    검증: 백엔드 273 passed(신규 17개 포함), 프론트 lint/build 0 에러, 실사용자
    데이터(user_id=1, 프로젝트 2개·카드 10장)로 임시 세션 발급 후 **브라우저로 직접
    클릭스루** 완료 — 범위 선택 → 두 프로젝트 초안 생성(프로젝트 헤드/기간 정상) →
    기록 상세 → 이어 쓰기 칩까지 확인, 콘솔 에러 0. 테스트 데이터는 만들지 않았고
    임시 세션도 지웠다(카드/프로젝트/초안 개수 변화 없음 확인).

    **못 한 검증**: `python-docx`/`lxml` 관련 테스트 16개가 이 Windows 환경에서
    "애플리케이션 제어 정책" 때문에 lxml `.pyd` 로드가 막혀 전부 실패한다 — 내 변경과
    무관하고(Word 내보내기 코드는 건드리지 않음) 리눅스 배포에서는 정상이다. 백업
    파일 내려받기/불러오기의 **브라우저 클릭스루**도 안 했다(실제 파일 다운로드가
    일어나는 동작이라 사용자 확인 없이 누르지 않음) — API/단위 테스트로만 검증됨.

0. **기존 경력기술서 붙여넣기 → Before/After 대조** (9/15, Figma 재검토로 새로
   발견된 미구현 화면 `90:612`/`90:640`, CLAUDE.md 3.5장에 구현 대상으로 명시돼
   있었으나 이전 배치 A/B/C에서 누락됐던 것). `POST /api/resume/enhance` 신규 —
   유저가 이미 써둔 경력기술서 문장을 프로젝트 카드로 보강해 근거(날짜/카드id)와
   함께 대조한다. `build_resume()`과 동일한 환각 방지(source_indices 사후 검증)
   패턴 재사용, 근거 카드가 없으면 원문 그대로 반환(2.2 원칙). `/resume`에 완전히
   선택적인 붙여넣기 섹션 + `ResumeCompareCarousel.tsx`(항목별 그대로 두기/적용
   캐러셀) 추가. 최종 결과는 새 저장 구조 없이 기존 `PUT /resume/draft`로 저장.
   백엔드 테스트 37개(신규 15개 포함) + 프론트 lint/build 통과, 실사용자 데이터
   (user_id=1, `B은행 계정계`, 카드 5장)로 임시 세션 발급해 curl로 실제 LLM 호출
   검증 완료(관련 카드 매칭 정상, 무관 문장은 원문 유지 정상). **브라우저 UI
   클릭스루 검증은 못 함** — 카카오 OAuth 실로그인이 필요해서 자동화 불가, 다음에
   실제로 로그인해서 `/resume`에서 "이미 쓰신 경력기술서가 있나요?" 펼쳐보고 직접
   확인할 것.
1. **카드 문장 자체 수정** — `/stack`에서 태그뿐 아니라 `refined_sentence`도 직접
   고칠 수 있음. `PATCH /api/cards/{id}`가 `skill_tags`/`refined_sentence` 둘 다
   optional로 받음(`db.update_card()`).
2. **변환 실패 시 원문 저장 폴백** — LLM 파싱 실패해도 카드는 항상 저장됨
   (`run_pipeline()`이 실패 시 원문 그대로 폴백 + `refinement_failed` 플래그 반환).
   `POST /api/cards/{id}/refine`로 나중에 재정리 가능. `/` 결과 모달이 실패 상태를
   별도 UI로 보여줌("다시 정리하기"/"확인").
3. **경력기술서 "숫자 되묻기" 인라인화** — `/resume`에서 결과가 비어있는 항목을
   `/`로 안 보내고 그 자리에서 바로 입력해 채울 수 있음(`StarItemCard.tsx`).
   서버 저장 안 함, 로컬 캐시(`resumeCache.ts`)만 갱신.
4. **`/onboarding` 재방문 버그 수정** — `AuthGate.tsx`가 이미 온보딩 끝난 유저를
   `/onboarding`에서 무조건 `/`로 튕기던 걸 고침. 이제 설정 변경(직군/연차/퇴근알림)
   목적으로 재방문 가능. 재방문 시 헤더/버튼 라벨이 "설정" 모드로 바뀜, 저장해도
   화면에 남음.
5. **`/stack` 주간 스트릭 점 클릭 가능화** — 기록 있는 날 점을 누르면 그 날짜
   카드만 필터링. 태그 필터와 배타적 동작.
6. **`/stack` 태그 필터 UX 3종** — ①가로 스크롤 화살표(‹›) ②태그 6개 넘으면 검색창
   ③카드 10개 넘으면 페이지네이션(그룹뷰는 제외). `/resume`의 카드 딥링크
   (`?cardId=`)가 다른 페이지에 있어도 자동으로 그 페이지로 이동하도록 재구성함.
7. **프로젝트 검색** — `ProjectSwitcher`에도 5개 넘으면 검색창.
8. **Figma 우선 재검토 배치 A/B/C** (이전 배치): 주간 스트릭 최초 구현, `/resume`
   저장 메타 표시, `/stack` 빈 상태, 카드 액션시트 BottomSheet화, 이어쓰기 배너,
   "4.1.1 AI 프로젝트 자동 제안"(미분류 카드 클러스터링→새 프로젝트 묶기).

## 4. 지금 열려있는 결정 사항 (다음 세션이 이어받을 것)

### 4-1. JD 링크(URL) 실제로 읽게 할지 — **보류 확정 (2026-09-15)**
사용자 결정: **아무것도 하지 않는다.** web_search 도구 붙이는 작업 착수 안 함. URL을
넣으면 별다른 경고 없이 그냥 무의미하게 동작하는 현재 상태 유지. 나중에 시간
남으면 재논의.

(아래는 보류 전 남겨둔 배경 메모)
사용자가 `/resume`의 "채용공고 붙여넣기"에 **본문 텍스트가 아니라 URL**을 넣었던
흔적을 발견 → 지금 코드는 URL이든 텍스트든 그냥 프롬프트에 문자열로 꽂아 넣을
뿐이라, URL을 넣으면 모델이 그 안의 내용을 알 방법이 없어 사실상 무의미함(실측
확인 완료: JD 없이 vs JD 텍스트로 항목 재정렬 자체는 정상 동작 — 문제는 "URL을
넣었을 때"만).

- **크롤링(직접 파싱)은 CLAUDE.md 2.4가 명시적으로 배제**("사이트별 파싱 이틀 녹음")
  — 이 결정은 안 바뀜.
- **Anthropic 공식 `web_search` 서버 도구**를 API 호출에 붙이는 건 별개 옵션 —
  기술적으로 가능함(SDK 1.4.0, 모델 `claude-sonnet-5` 둘 다 지원 확인함). 다만:
  - **검색 1회당 별도 과금**(토큰 비용과 별개, JD 링크 붙일 때마다 반복 발생)
  - `src/parsing/resume.py`의 `_call_llm_anthropic()`에 `tools=[...]` 추가 +
    tool-use 왕복 처리 필요(현재는 순수 텍스트 호출, 도구 없음)
  - **사용자가 아직 "붙이자"고 확정 답 안 함** — 마지막 메시지가 "가능은 한거야?
    크레딧 문제야?"였고, 그 다음 메시지가 이 인수인계 요청이라 **여기서 대화가
    끊긴 상태**. 다음 세션은 사용자에게 진행 여부부터 다시 물어볼 것.

### 4-2. 목표 직무/직무 전환 번역 기능 — **스코프 크다고 판단, 보류**
Figma 재검토에서 발견한 새 갭 중 하나(`89:368`, `89:206`, `89:286`, `3.1-b/c`) —
CLAUDE.md P2 "온보딩(현재 직무/목표 직무/연차)"의 절반(목표 직무)이 아직 없음.
지금 온보딩은 "현재 직무"만 있고 "목표 직무로 번역"하는 기능 자체가 없음. 사용자가
직접 고른 갭 3종(카드 문장 수정/변환 실패 폴백/숫자 되묻기)에는 포함 안 시켰음 —
스코프가 커서 별도 논의 필요.

### 4-3. Notion 읽기 OAuth — **명시적으로 보류 중**
사용자가 "일단 보류, 남은 3개만 먼저"라고 확정함. OAuth 앱 client_id/secret이 아직
없어서 착수 불가 — 사용자가 발급받아 오기 전엔 시작하지 말 것.

## 5. 알려진 잔여 백로그 (이번 세션에서 손 안 댐)

- **Track D (OCI + nginx 배포)** — 100% 미착수. 실제 VM/도메인 접속 정보 필요.
- **실기기 검증 3종**(CLAUDE.md 8장) — 마이크 입력(iOS Safari), 웹푸시 수신, PWA
  설치 — 전부 코드는 이식 완료됐지만 실기기 확인 자체가 안 됨.
- `.chroma_bench_tmp2/` — 정체불명의 untracked 디렉터리가 git status에 계속 뜸.
  이번 세션에서 만든 게 아니라 손 안 댐 — 필요하면 사용자에게 뭔지 물어볼 것.

## 6. 이번 세션에서 겪은 기술적 함정 (재발 방지용 메모)

- **Starlette 미들웨어 순서**: `app.add_middleware()`는 나중에 호출할수록 더
  바깥쪽(= `ServerErrorMiddleware`에 더 가까움). 예외 핸들러(`@app.exception_handler`)는
  `CORSMiddleware`를 안 거치고 `ServerErrorMiddleware`로 바로 감 — CORS 헤더가
  안 붙어서 브라우저가 "CORS 에러"로 오인 표시했던 실제 사례 있었음(진짜 원인은
  서버 500). 커스텀 ASGI 미들웨어를 `CORSMiddleware` **뒤에** 추가해서 해결함
  (`src/api/main.py`의 `_CORSSafeErrorMiddleware`).
- **`EMBEDDING_PROVIDER`는 `LLM_PROVIDER`와 완전히 별개 설정**이다 — 헷갈려서
  `EMBEDDING_PROVIDER=anthropic`처럼 잘못 넣으면 chromadb가 `None` 임베딩함수를
  못 받아들여서 카드 생성이 통째로 깨짐. `.env`는 `EMBEDDING_PROVIDER=ollama`가
  맞는 값.
- **Claude가 JSON을 마크다운 코드펜스로 감싸서 응답하는 경우**가 실제로 있음 —
  `_strip_code_fence()` 정규식으로 벗겨내야 `json.loads()`가 안 죽음
  (`src/parsing/parser.py`/`resume.py` 둘 다 적용됨).
- **Anthropic 응답의 `content[0]`이 텍스트라고 가정하면 안 됨** — `ThinkingBlock`이
  먼저 올 수 있어 `.text` 접근 시 AttributeError. `_extract_text()`로 텍스트 블록만
  골라내야 함.
- **브라우저 자동화(`computer` 도구)의 좌표계가 실제 CSS 픽셀과 안 맞을 때가 있음**
  (이번 세션에서 스크린샷 기준 클릭이 실제로는 다른 요소를 눌러서 실패한 사례 발견).
  안 먹히면 `javascript_tool`로 `document.querySelector(...).click()`을 직접
  호출하는 쪽이 훨씬 신뢰도 높음 — 이번 세션에서 확립된 우회 패턴.
- **`computer` 스크린샷이 가끔 30초 타임아웃 나며 탭이 잠깐 멎은 것처럼 보임** —
  대부분 재시도하면 바로 풀림(진짜 프리징 아님). `<input type="date">`에
  `computer.type`으로 값 넣으면 값이 깨지는 버그도 있었음(`91520-02-06`처럼) —
  네이티브 setter로 직접 값 넣는 `javascript_tool` 패턴을 쓸 것.
- **`.env`의 실제 값은 절대 이 문서/커밋/로그에 노출하지 말 것** — `LLM_API_KEY`
  등은 항상 마스킹해서 확인.

## 7. Figma 참고 정보

- 파일: `https://www.figma.com/design/MbQqcE5hGWI5KXwT3OtvIb/Connecting-Dots`
  (fileKey: `MbQqcE5hGWI5KXwT3OtvIb`)
- 진입 노드: `10:2`(캔버스, 기획정리+전체 화면 목업 다 이 밑에 있음). `get_metadata`로
  인자 없이 부르면 `0:1`(무관한 "일정관리" 캔버스, 해커톤 발표용 타임라인 그래픽)만
  나오는 이상한 동작이 있으니 속지 말고 `10:2`로 바로 들어갈 것.
- **9/18 재조사 결과**: 화면 39개 중 미구현으로 남은 건 전부 **사용자가 보류를
  확정한 것들**뿐이다 — 2.1 이력서 파일 업로드(`89:6`), 직무 전환·목표 직무 번역
  5화면(`89:368`/`89:206`/`89:286`/`89:46`/`89:76`, 4-2 참고), 노션 OAuth
  3화면(`41:452`/`41:486`/`41:832`, 4-3 참고). 다시 제안하기 전에 사용자에게 확인할 것.
- 최근 전수 재조사(캔버스 `10:2` 산하 48개 최상위 프레임, 실제 화면 39개) 완료 —
  대부분 이미 구현됐거나 아키텍처 피벗(로컬전용저장→서버+로그인)으로 배제 대상.
  **디자인 자체가 두 갈래로 갈린 화면 2개는 사용자가 "지금 그대로 둔다(추천)"로
  확정**: ①1.0 웰컴스크린(로고+카피 vs 365일 점 격자) ②메인 입력 홈(텍스트패드 —
  현재 구현 vs 스킬 버블차트, `145:590`). 재검토 필요 없음, 그냥 참고만.

---

## 8. 다음 세션 시작 시 체크리스트

1. `CLAUDE.md` 읽기 (2장 절대원칙, 2.4 배제목록, 3장 데이터모델)
2. 이 문서(`HANDOFF.md`) 읽기
3. 백엔드(`curl localhost:8000/api/health`)/프론트(`curl localhost:3001`) 살아있는지
   확인 — 이 세션 종료 시점엔 둘 다 정상 기동 중이었으나, 새 세션에서는 이전
   백그라운드 프로세스가 안 살아있을 수 있음(재기동 명령은 2절 참고)
4. **4절의 미결 사항부터 사용자에게 확인** — 특히 4-1(JD 웹서치 도구 진행 여부)은
   사용자 답변 없이 바로 구현 착수하지 말 것
