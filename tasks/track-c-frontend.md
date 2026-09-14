# Track C — Next.js 프론트엔드 (9/16)

> **2026-09-13 전면 재작성.** Streamlit을 폐기하고 Next.js로 전환한다.
> 기존 `src/frontend/`는 이식하지 않고 버린다. 사유는 아래 1장.

---

## 1. 왜 Streamlit을 버리는가

**음성 입력이 제품 컨셉의 절반이기 때문이다.** 자차 출퇴근자가 폰으로 말해서 기록하는
경로는 노트북으로 대체가 안 된다. 그런데 Streamlit에서 마이크·PWA·푸시를 쓰려면
`components.html`이 만드는 **샌드박스 iframe** 안에서 동작해야 하고, 거기서 막힌다.

기존 코드가 이 실패를 스스로 기록하고 있다 (`src/frontend/components/install_button.py`):

```
window.parent.document          ← iframe 밖으로 나가 <head>에 manifest 주입
scope는 /app/static/ 하위로만 등록 가능 — 그 이상("/")을 넘기면 브라우저가 거부
push_setup.py에서 이미 겪은 것처럼 iframe 안에서의 서비스워커 등록이 실패하는 경우
```

Next.js에서는 페이지가 마이크와 서비스워커를 **직접 소유**하므로 이 문제가 통째로 사라진다.
`manifest.json`의 `start_url: "/"`도 정상 동작하고, 서비스워커도 루트 scope로 등록된다.

**부수 효과로 Figma 디자인을 실제로 구현할 수 있게 된다.** 390px 모바일, 바텀시트,
하단 탭바, 칩, 스켈레톤 로딩 전부 가능하다.

---

## 2. 전제 조건

- `docs/05-api-contract.md`가 먼저 고정돼 있어야 한다. **이 문서만 보고 작업한다**
- 백엔드 P0(저장소, `build_resume()`, 프로젝트 층)가 9/15까지 끝나 있어야 한다
- 9/13 실기기 음성 테스트 결과가 나와 있어야 한다 (CLAUDE.md 8장).
  **iOS 실패 시 음성 화면 설계가 달라진다** — 실시간 자막 → 녹음 버튼 하나

---

## 3. 화면 구성 (Figma 대응)

| Figma | 경로 | 내용 |
|---|---|---|
| 2.0 온보딩 | `/onboarding` | 현재 직무 / 목표 직무 / 연차 세그먼트 |
| 3.0 입력 | `/` | 텍스트 + 음성 입력, 프로젝트 스위처, 변환 버튼 |
| 3.0-e / 3.1 | `/` 내 모달 | 변환 대기 스켈레톤 → 결과 출력 |
| 4.1 커리어 스택 | `/stack` | 카드 목록, 프로젝트/태그 필터 |
| 4.2 빌더 | `/resume` | JD 붙여넣기, STAR 항목, 내보내기 |
| 신규 | `/projects` | 프로젝트 목록 + 생성 (최소 기능) |

### 3.1 프로젝트 스위처 (신규, Figma에 없음)
입력 화면 상단, 목표 직무 칩 옆에 `A은행 차세대 ›` 표시.
탭하면 프로젝트 목록 바텀시트 + "새 프로젝트" 버튼.

**이름과 시작일만 받는다.** 연 1~3회 쓰는 화면이므로 최소로 만든다 (CLAUDE.md 2.4).

### 3.2 숫자 되묻기 (P2)
결과 모달에서 `result`가 비어 있으면 "얼마나 좋아졌는지 기억나세요? (건너뛰기)" 칩 노출.
**AI가 숫자를 만들어내지 않는 대신 유저에게 묻는다** (CLAUDE.md 2.2).

---

## 4. 기술 스택

- Next.js (App Router), TypeScript
- 스타일: Tailwind 권장. Figma 토큰(색/간격/라운드)을 `tailwind.config`에 먼저 옮길 것
- 상태: 서버 상태는 `fetch` + React Server Components 또는 SWR. 전역 상태 라이브러리 불필요
- 차트: 역량 그래프는 Recharts. **Plotly는 Streamlit 전용 결정이었으므로 폐기**

### 4.1 PWA
```
app/manifest.ts          → start_url: "/", display: "standalone"
public/service-worker.js → 루트 scope 등록
```
`next-pwa` 같은 플러그인을 쓰면 더 빠르지만, 푸시 로직이 이미 있으므로 수동 등록도 무방하다.

---

## 5. 작업 항목

- [x] Next.js 프로젝트 초기화, Tailwind 설정 — `web/`에 App Router + TypeScript +
      Tailwind v4로 초기화. **Figma 토큰 이식은 안 함** — Figma 접근 권한이 없어
      `app/globals.css`의 기본 토큰(Tailwind v4는 `tailwind.config.js` 대신 CSS
      `@theme`로 토큰을 정의함)을 플레이스홀더로 남겨둠. 디자이너 확정 시 후속 작업 필요
- [x] API 클라이언트 (`web/lib/api.ts`) — `docs/05-api-contract.md` §1~3(카드/프로젝트/
      경력기술서) + §8(헬스체크) 타입/함수 구현. `result: ""`, `source_dates: string[]`
      계약을 타입 레벨에서 그대로 반영
- [x] `/` 입력 화면 + 프로젝트 스위처 — `web/app/page.tsx` +
      `web/components/ProjectSwitcher.tsx` (바텀시트, 이름+시작일만 받음).
      "변환 모달"은 별도 모달 대신 인라인 카드 + 스켈레톤으로 구현 (동일 화면 흐름 유지가
      더 가볍다고 판단 — 필요시 모달로 전환 가능)
- [x] `/stack` 카드 목록 + 태그 필터 — `web/app/stack/page.tsx`
- [x] `/resume` JD 붙여넣기 + STAR 렌더링 + 클립보드 복사 — `web/app/resume/page.tsx`,
      `web/components/StarItemCard.tsx`. 빈 `result`는 "결과 없음" 대신 되묻기 칩으로
      표시, `source_dates` 토글("이 문장의 근거") 포함, 항목별/전체 클립보드 복사 버튼 포함
- [x] `/projects` 목록 + 생성 — `web/app/projects/page.tsx` (이름+시작일만, 폴더 CRUD
      고도화 없음)
- [x] `/onboarding` (P2, 9/14 3번째 세션) — `web/app/onboarding/page.tsx`. 백엔드
      계약(`docs/05-api-contract.md` §9, `GET/PUT /api/profile`)이 확정돼 진행함.
      직군(6개 칩, 단일 선택) → "개발" 선택 시 세부 직무 칩 노출 → 연차(4개 세그먼트) →
      퇴근 알림(기존 `<PushSetup />` 재사용) → 저장 후 `/`로 이동. 직군/연차는 자유
      입력이 아니라 고정 칩만 받는다(2.4) — 서버가 `Literal`로 다시 한번 강제.
      `<PushSetup />`을 입력 화면(`/`)에서 이 화면으로 옮겼다 — Figma "3.0" 화면엔
      원래 없던 요소였고, 연 1~3회만 건드리는 설정을 매일 쓰는 화면에 상시 노출할
      이유가 없다(2.1). `/`에는 대신 "⚙ 설정" 링크만 남겨 `/onboarding`으로 연결.
      **미완료**: 최초 방문 시 자동으로 이 화면으로 보내는 온보딩 게이팅은 넣지
      않음(요청 범위 밖) — 지금은 `/`의 설정 링크로만 진입 가능
- [x] 마이크 이식 (9/13, 2번째 세션) — `web/components/VoiceInput.tsx`
      (`docs/06-migration.md` §2.1). `src/frontend/components/voice_input.py`의 JS
      로직(`lang="ko-KR"`, `continuous=false`, `interimResults=true`, 버튼 클릭 안에서
      `recognition.start()`, `onend`에서 `isFinal` 누락 시 폴백 제출)을 그대로 포팅했다.
      iframe 우회(base64 쿼리 파라미터 리다이렉트)는 삭제 — React state로 직접 받는다.
      `web/app/page.tsx`의 `submitText()`를 텍스트/음성 공통 제출 경로로 추출해 동일한
      스켈레톤/결과 카드를 탄다. **CLAUDE.md 8장의 실기기(iPhone Safari) 검증은 여전히
      미완료** — iOS Safari가 14.5부터 `webkitSpeechRecognition`을 지원한다는 사전 조사
      결과에 기반해 Web Speech API로 진행을 결정했다(이번 세션 지시사항). 실기기에서 실패
      확인 시 `docs/05-api-contract.md` §6(`POST /api/stt` + `MediaRecorder`) 폴백으로
      전환할 것 — 아직 구현 안 함
- [x] PWA manifest + 서비스워커 루트 등록 (9/13, 2번째 세션) — `web/app/manifest.ts`
      (Next.js App Router 관례, `/manifest.webmanifest`로 서빙 확인), `web/public/service-worker.js`
      (push/notificationclick 핸들러, `src/frontend/static/service-worker.js`와 로직 동일),
      `web/components/ServiceWorkerRegistration.tsx`가 루트 scope(`/`)로 등록(`app/layout.tsx`에
      마운트). 아이콘은 실제 에셋이 없어 `web/public/icon.svg` 플레이스홀더 사용 —
      디자이너 확정 시 PNG로 교체 필요. manifest `name`/`short_name`을 "커리어 로그"로
      갱신함(이 파일 범위 내에서만 — README 등 나머지 이름 정리는 CLAUDE.md 우선순위상
      9/18로 미룸)
- [x] 웹푸시 구독 이식 (9/13, 2번째 세션) — `web/components/PushSetup.tsx`
      (`docs/06-migration.md` §1). `GET /api/push/vapid-public-key` → 권한 요청(버튼
      클릭 핸들러 안) → SW 등록/재사용 → `pushManager.subscribe()`(base64url→Uint8Array
      변환은 `web/lib/push.ts`) → `POST /api/push/subscribe`(+`leave_time`) 순서로 구현.
      `web/app/page.tsx` 상단(프로젝트 스위처 아래)에 배치. 재구독은 서버 upsert에
      기대 — 별도 클라이언트 분기 없음. 구독 해제(`DELETE /api/push/subscribe`)도
      구현함(선택 항목이었지만 시간 내 완료). 503(VAPID 미설정) 시 안내 문구만 보이고
      숨겨짐. **Tier 1(탭 열려있을 때 타이머, `reminder.py`)은 의도적으로 스킵** — Tier 2
      실 웹푸시가 있으므로 이식 가치가 낮다고 판단(이번 세션 지시사항, `docs/06-migration.md`
      본문에 대한 편차는 아님)
- [x] 로딩 상태 (스켈레톤) — `web/components/Skeleton.tsx`. `/`(카드 변환)와
      `/resume`(STAR 생성) 양쪽 다 3~10초 대기 스켈레톤 적용

### 5.1 이번 세션 검증 결과 (백엔드 미기동 상태에서)
- `npm run build`, `npm run lint` 모두 통과 (0 에러)
- `npm run dev`로 기동 후 `/`, `/stack`, `/resume`, `/projects` 4개 라우트 전부
  curl로 200 확인, 에러 페이지 없음 (백엔드가 없으므로 각 화면은 fetch 실패 시
  에러 메시지만 보여주고 크래시하지 않음 — 의도된 동작)
- 백엔드가 붙은 상태의 실제 통합 테스트는 아직 못 함 — Track B 완료 후 필요

### 5.2 마이크/PWA/푸시 세션 검증 결과 (9/13, 2번째 세션)
- `npm run build`, `npm run lint` 재확인 — 0 에러 (신규 파일 포함)
- `npm run dev` 기동 후 curl로 확인:
  - `GET /` → 200, 마이크 버튼("말로 기록하기")·푸시 설정("퇴근 알림 켜기", "퇴근 시각")
    마크업 포함 확인
  - `GET /manifest.webmanifest` → 200, `application/manifest+json`, `name`/`short_name`/
    `start_url`/`display`/`icons` 필드 전부 정상 (Next.js는 `app/manifest.ts`를
    `/manifest.webmanifest`로 서빙함 — `/manifest.json` 아님, 착오 주의)
  - `GET /service-worker.js` → 200, `application/javascript; charset=UTF-8`, 루트 경로에서
    정상 서빙
- `web/lib/push.ts`의 base64url→Uint8Array 변환 로직을 Node 스크립트로 별도 검증 —
  샘플 VAPID 공개키(65바이트, 첫 바이트 `0x04` = 압축 안 된 EC 포인트) 디코딩 결과 정상
- **실기기로 확인 못 한 것** (브라우저 자동화가 처리할 수 없는 영역, 아래 7장 완료 기준의
  실기기 항목 참고): 마이크 권한 팝업/실제 인식 품질, `Notification`/푸시 권한 팝업,
  서비스워커 설치 후 실제 웹푸시 수신, iOS Safari 자체에서의 동작 여부 전부

---

## 6. STAR 렌더링 주의

`build_resume()`이 반환하는 `result`는 **비어 있을 수 있다.** 숫자가 기록에 없으면
AI가 지어내지 않고 빈 문자열을 반환하도록 설계돼 있기 때문이다.

- 빈 `result`를 "결과 없음"으로 렌더링하지 말 것. 항목 자체를 숨기거나 되묻기 칩을 노출한다
- `source_dates`를 활용해 "이 문장의 근거" 토글을 제공하면 데모에서 신뢰도가 올라간다

---

## 7. 완료 기준

- [ ] 텍스트 입력 → 변환 → 결과 표시가 실기기 브라우저에서 동작 — **실기기 확인 필요**
      (이번 세션에서 코드는 구현/빌드/curl 검증까지 끝났으나, 실제 폰 브라우저로는
      확인 못 함)
- [ ] 음성 입력이 **실제 폰에서** 동작 (또는 녹음+STT 폴백이 동작) — **실기기 확인 필요**.
      코드는 `web/components/VoiceInput.tsx`로 구현 완료(Web Speech API 경로,
      `docs/06-migration.md` §2.1), 브라우저 자동화로는 마이크 권한 팝업 자체를 다룰 수
      없어 이 항목은 이번 세션에서 체크 불가. CLAUDE.md 8장의 iPhone Safari 실기기
      테스트가 여전히 미완료 상태 — iOS 실패 시 `docs/05-api-contract.md` §6 폴백으로
      전환 필요
- [ ] 카드가 새로고침 후에도 남아 있음
- [ ] `/resume`에서 시간차 페어가 하나의 STAR로 합쳐진 것이 눈으로 확인됨
- [ ] 9/16 저녁까지 최소 기능 버전이 로컬에서 동작 (Track D 연습 배포용)
- [ ] (신규, 9/13 2번째 세션) PWA 설치 + 웹푸시 수신이 **실기기에서** 동작 —
      **실기기 확인 필요**. 코드는 `app/manifest.ts` + `public/service-worker.js` +
      `components/ServiceWorkerRegistration.tsx` + `components/PushSetup.tsx`로 구현
      완료, curl로 manifest/서비스워커 서빙까지만 검증함. `Notification.requestPermission()`
      팝업, `pushManager.subscribe()` 실제 성공 여부, 서버로부터의 실제 푸시 수신은
      브라우저 자동화로 확인 불가 — 사용자가 직접 폰/브라우저로 확인해야 함

---

## 8. 중단 조건

**9/15 화요일 저녁에 백엔드 P0가 안 끝났으면 이 트랙을 시작하지 않는다.**
Streamlit으로 마감한다. 화면은 포기해도 제품은 남지만, 백엔드가 비면 보여줄 것이 없다.
