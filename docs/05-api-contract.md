# API 계약 (신규, 2026-09-13)

프론트/백 분리 이후 **이 문서가 단일 진실 공급원**이다.
Track C는 이 문서만 보고 작업하고, 백엔드는 이 문서를 먼저 고친 뒤 구현한다.

- Base: `/api`
- 모든 요청/응답 `application/json` (STT 업로드 제외)
- 인증 없음 (해커톤 단일 유저 데모 전제). **멀티유저는 스코프 밖**
- 에러: `{ "detail": "..." }` + 적절한 HTTP 상태코드

---

## 1. 카드

### `POST /api/cards`
메모 한 줄을 파싱해 저장한다. **매일 쓰는 경로 — 가볍게 유지.**

```jsonc
// 요청
{ "raw_text": "결제 API 느려서 레디스 캐시 붙임" }

// 응답 201
{
  "id": 42,
  "project_id": 3,               // 현재 프로젝트에 자동 배정. 없으면 null
  "raw_text": "결제 API 느려서 레디스 캐시 붙임",
  "refined_sentence": "결제 API 응답 지연을 해소하기 위해 Redis 캐싱 레이어를 도입했습니다.",
  "skill_tags": ["Redis", "성능최적화", "결제시스템"],
  "confidence": 0.91,
  "created_at": "2026-02-14T18:45:00+09:00",
  "refinement_failed": false     // 9/15 신규 — 아래 설명 참고
}
```

> **JD 매칭을 여기서 하지 않는다.** 이직 준비 때만 필요한 걸 매일 돌릴 이유가 없다.
> 응답은 3~10초 걸린다. 프론트는 스켈레톤을 띄운다.

> **`refinement_failed` (9/15 신규)**: LLM 파싱이 실패해도 카드는 반드시 저장된다
> (CLAUDE.md P0 "저장소 없으면 제품이 없다") — 이 경우 `refined_sentence`는 원문과
> 동일하고 `skill_tags`는 빈 배열, `confidence`는 0.0, `refinement_failed`는 true로
> 온다. 이 필드는 DB에 저장되는 값이 아니라 **생성 시점에만** 라우터가 채워 넣는다
> — 이후 `GET`/`PATCH` 응답에서는 항상 `false`.

### `GET /api/cards?project_id=3`
`project_id` 생략 시 전체. 최신순 정렬.

```jsonc
{ "cards": [ /* 위 카드 객체 배열 */ ] }
```

### `DELETE /api/cards/{id}`
응답 204.

### `PATCH /api/cards/{id}`
카테고리(스킬 태그)와 문장(정제된 문장)을 손으로 고친다 — 저장 시점엔 여전히
AI(LLM+캐노니컬라이제이션)가 자동으로 채우고, 이건 저장 후 가끔(`/stack`에서)
고치는 별도 경로다(CLAUDE.md 2.1). 두 필드 다 optional이지만 **최소 하나는
있어야 한다** — 둘 다 없으면 400.

```jsonc
// 요청 (둘 중 하나 이상, 둘 다 가능)
{ "skill_tags": ["결제/정산"], "refined_sentence": "사람이 직접 고친 문장" }

// 응답 200 — 위 카드 객체와 동일한 모양(refinement_failed는 항상 false)
```

### `POST /api/cards/{id}/refine` (9/15 신규)
폴백 저장된(원문 그대로인) 카드를 다시 AI로 정리해본다. 요청 바디 없음. 성공하면
`refined_sentence`/`skill_tags`/`confidence`가 갱신된 카드 객체를 200으로 반환한다.
다시 실패하면 500 — 폴백 저장이 이미 끝난 상태라 데이터 유실 위험은 없다.

### `GET /api/cards/unclassified/suggestions` (9/14 신규)
"4.1.1 AI 프로젝트 자동 제안" — `project_id`가 없는(아직 프로젝트 미배정) 카드끼리만
비교해서 비슷한 것들을 묶어 후보로 제시한다. **이미 프로젝트가 배정된 카드는 이
엔드포인트가 조회 대상으로도 삼지 않는다** — CLAUDE.md 3장("프로젝트는 사람이
만든다")을 지키기 위한 안전장치. 2개 미만이 모인 클러스터는 반환하지 않는다.

```jsonc
// 응답 200
{
  "clusters": [
    {
      "card_ids": [12, 15],
      "cards": [ /* 카드 객체 배열, §1 GET과 동일한 모양 */ ]
    }
  ]
}
```

### `POST /api/cards/bundle-into-project` (9/14 신규)
선택된 카드들을 새 프로젝트로 묶는다. **프로젝트 이름은 AI가 짓지 않는다** —
사용자가 직접 입력한 값을 그대로 받는다(CLAUDE.md 2.2 정신). 다른 유저 소유의
`card_id`를 섞어 보내도 그 카드만 조용히 무시되고 나머지는 정상 처리된다.

```jsonc
// 요청
{ "card_ids": [12, 15], "name": "결제 API 개선 프로젝트", "started_at": "2023-02-14" }

// 응답 201 — §2 프로젝트 객체와 동일한 모양
{ "id": 4, "name": "결제 API 개선 프로젝트", "started_at": "2023-02-14",
  "ended_at": null, "is_current": true }
```

---

## 2. 프로젝트

### `GET /api/projects`
```jsonc
{
  "projects": [
    { "id": 3, "name": "A은행 차세대", "started_at": "2023-02-01",
      "ended_at": null, "is_current": true },
    { "id": 2, "name": "B카드 시스템 구축", "started_at": "2022-05-01",
      "ended_at": "2023-01-31", "is_current": false }
  ]
}
```

### `POST /api/projects`
```jsonc
// 요청 — 이름과 시작일만. 최소 기능 (CLAUDE.md 2.4)
{ "name": "A은행 차세대", "started_at": "2023-02-01" }

// 응답 201 — 생성 시 자동으로 is_current: true
{ "id": 3, "name": "A은행 차세대", "started_at": "2023-02-01",
  "ended_at": null, "is_current": true }
```

### `PATCH /api/projects/{id}`
```jsonc
{ "is_current": true }      // 기존 current는 자동으로 해제된다
{ "name": "A은행 차세대 2차" }
{ "ended_at": "2023-11-30" }
```

---

## 3. 경력기술서 ★ 핵심

### `POST /api/resume`
프로젝트의 카드를 묶어 STAR 항목으로 변환한다. **이직 준비 경로 — 무겁게.**

```jsonc
// 요청
{
  "project_id": 3,
  "jd_text": "..."            // 선택. 채용공고 본문 붙여넣기. 없으면 일반 초안
}

// 응답 200
{
  "items": [
    {
      "title": "결제 API 성능 개선",
      "period": "2023.02 - 2023.03",
      "situation": "결제 API 응답 지연으로 사용자 이탈이 발생하는 상황이었습니다.",
      "task": "응답 시간을 개선하고 결제 도메인 안정성을 확보해야 했습니다.",
      "action": "Redis 캐싱 레이어를 도입하고 쿠폰 중복 버그를 수습했습니다.",
      "result": "결제 오류율을 0.8%에서 0.3%로 낮췄습니다.",
      "source_dates": ["02.14", "02.17", "03.02"],
      "source_card_ids": [12, 13, 15]
    }
  ]
}
```

### 프론트가 반드시 지킬 것

**`result`는 빈 문자열일 수 있다.** 기록에 숫자가 없으면 AI가 지어내지 않고
비워서 반환하도록 설계돼 있다 (CLAUDE.md 2.2).

- 빈 `result`를 "결과 없음"으로 렌더링하지 말 것 — 항목을 숨기거나 되묻기 칩을 노출
- `source_dates`로 "이 문장의 근거" 토글 제공 권장. 데모 신뢰도가 올라간다
- **`source_dates`와 `source_card_ids`는 역할이 다르다 (9/14 신규 필드).**
  `source_dates`는 사람이 읽는 화면 표시용(날짜 문자열, 같은 날짜 카드가 여러 장이면
  중복될 수 있음)이고, `source_card_ids`는 실제 카드를 정확히 가리키는 식별자다.
  **카드와 매칭하는 로직(예: `/stack`에서 이 항목에 해당하는 카드를 찾는 것)은 반드시
  `source_card_ids`로 할 것** — `source_dates`로 매칭하면 같은 날짜에 카드가 여러 장
  있을 때 무관한 카드까지 같이 묶이는 버그가 생긴다(9/14 실제로 발견/수정됨).

> URL을 받는 필드는 없다. **채용공고 크롤링은 구현하지 않는다** (CLAUDE.md 2.4).

### `GET /api/resume/draft?project_id=3` (9/14 신규)
유저가 `POST /resume` 결과를 가져다 직접 고친 자유 텍스트(마크다운) 초안을 조회한다.
**AI가 만든 STAR 구조 자체는 여전히 저장하지 않는다(CLAUDE.md 3장)** — 여기서 저장하는
건 그것과 다른 것으로, 유저가 명시적으로 "저장"을 눌러서 자기 문서로 삼은 자유 텍스트다.
카드 구조와 더 이상 엮여 있지 않으므로(재검증/재동기화 불필요), 3장이 막았던 문제가
생기지 않는다.

```jsonc
// 응답 200 — 저장된 초안이 없으면 content/updated_at이 둘 다 null
{ "project_id": 3, "content": "# 결제 API 성능 개선\n...", "updated_at": "2026-09-14T12:00:00+00:00" }
```

### `PUT /api/resume/draft`
```jsonc
// 요청
{ "project_id": 3, "content": "# 결제 API 성능 개선\n..." }

// 응답 200 — 저장된 그대로 반환. project_id가 이 유저 소유가 아니면 404
{ "project_id": 3, "content": "...", "updated_at": "2026-09-14T12:00:05+00:00" }
```
프로젝트당 초안 1개(upsert) — 여러 버전을 관리하는 기능은 없다(CLAUDE.md 2.4 정신:
최소 기능만).

### `POST /api/resume/enhance` (9/15 신규)

유저가 이미 써둔 경력기술서 문장을 프로젝트 카드로 보강해 Before/After로 대조한다
(Figma `90:612`/`90:640`, "기존 항목 붙여넣기 → Before·After 대조"). **완전히 선택
사항** — 안 써도 `POST /api/resume`로 새로 생성하는 기존 경로가 그대로 있다.

```jsonc
// 요청
{
  "project_id": 3,
  "existing_items": ["결제 API 성능 개선 담당", "신규 회원 온보딩 플로우 기획"]  // 줄바꿈 분리, 최대 10개
}

// 응답 200
{
  "items": [
    {
      "original": "결제 API 성능 개선 담당",
      "enhanced": "프로모션 트래픽 급증으로 발생한 결제 API 응답 지연을 Redis 캐싱 레이어 도입으로 해소하고, 응답 시간을 200ms 단축했습니다.",
      "gap_comment": "왜 Redis를 골랐는지가 없어요. 한 줄 더하면 판단 근거가 생깁니다.",
      "source_dates": ["02.14", "02.18"],
      "source_card_ids": [12, 13]
    }
  ]
}
```

- 관련 카드가 없으면 `enhanced`는 `original`과 동일하게 오고, `source_dates`/
  `source_card_ids`/`gap_comment`는 전부 비어 있다 — 근거 없이 보강된 것처럼 보이게
  만들지 않는다(2.2 원칙).
- `gap_comment`는 빈 문자열일 수 있다. 매칭된 카드에 없는 정보를 지어내 지적하지 않는다.
- `POST /resume`과 마찬가지로 `source_card_ids`로 카드를 매칭할 것(`source_dates`는
  화면 표시용).
- **AI가 만든 보강 결과 자체는 저장하지 않는다.** 유저가 "적용"한 최종 텍스트만
  프론트가 모아 기존 `PUT /resume/draft`로 저장한다(CLAUDE.md 3장).
- URL을 받는 필드는 없다(2.4 배제 목록 유지).

---

## 4. JD 매칭 (P1)

### `GET /api/jds/match?card_id=42&top_k=5`
카드의 스킬 태그로 유사 공고를 찾는다.

```jsonc
{
  "matches": [
    { "company": "가상핀테크", "title": "결제 백엔드 엔지니어",
      "required_skills": ["Redis", "결제시스템", "장애대응"],
      "description": "...", "score": 0.87 }
  ]
}
```

---

## 5. 노션 (읽기 전용)

### `POST /api/notion/sync`
```jsonc
// 요청 — user_token은 필수. optional 취급 금지 (docs/03-risk-fallback.md 리스크 6)
{ "user_token": "secret_...", "page_id": "..." }

// 응답 200
{ "imported": 12, "cards": [ /* 카드 객체 배열 */ ] }
```

> **쓰기 엔드포인트는 없다** (CLAUDE.md 2.4). 내보내기는 프론트에서 클립보드 복사.

---

## 6. 음성 (폴백 경로일 때만)

### `POST /api/stt`
`multipart/form-data`, 필드명 `audio`.

Web Speech API가 실기기에서 동작하면 **이 엔드포인트는 불필요하다.**
9/13 검증 결과에 따라 구현 여부를 결정한다 (CLAUDE.md 8장).

```jsonc
// 응답 200
{ "text": "결제 API 느려서 레디스 캐시 붙임" }
```

---

## 7. 웹푸시

### `GET /api/push/vapid-public-key` (9/13 추가)
```jsonc
{ "public_key": "..." }
```
프론트가 `pushManager.subscribe({ applicationServerKey: ... })`에 쓸 공개키.
VAPID_PUBLIC_KEY가 서버에 설정 안 돼 있으면 503.

### `POST /api/push/subscribe`
```jsonc
// 요청 — leave_time은 9/13 추가 필드(계약 초안엔 없었음). 발송 시각 계산
// (push_sender.send_due_reminders())에 필수라서 추가함. Track C에 공유 완료.
{ "endpoint": "https://fcm.googleapis.com/...",
  "keys": { "p256dh": "...", "auth": "..." },
  "leave_time": "18:00" }
```
응답 201. 로그인이 없으므로 `endpoint`를 해시해 구독 구분용 id로 쓴다 — 같은
구독으로 다시 호출하면 upsert된다. 기존 Upstash 저장소 그대로 씀
(`docs/06-migration.md` 참조).

### `DELETE /api/push/subscribe`
```jsonc
// 요청
{ "endpoint": "https://fcm.googleapis.com/..." }
```
응답 204. 존재하지 않는 구독을 지워도 204(멱등).

---

## 8. 헬스체크

### `GET /api/health`
```jsonc
{ "status": "ok", "db": true, "chroma": true, "llm": true }
```
배포 검증과 발표 직전 확인에 쓴다.

---

## 9. 온보딩 프로필 (P2, 9/14 신규)

로그인이 없는 단일 유저 데모 전제라 싱글턴이다 — 여러 유저를 구분하지 않는다.
`job_field`/`years_segment`는 자유 입력이 아니라 고정 칩 세트다(CLAUDE.md 2.4:
연차 직접 입력 배제). 아직 다른 기능(경력기술서 생성, JD 매칭)에는 연결돼 있지
않다 — 온보딩/입력 화면에 컨텍스트를 보여주는 용도.

### `GET /api/profile`
```jsonc
// 온보딩을 아직 안 했으면 전부 null
{ "job_field": "개발", "job_detail": "백엔드", "years_segment": "4-6" }
```

### `PUT /api/profile`
```jsonc
// 요청 — job_field/years_segment는 아래 고정값만 허용, 그 외는 422
// job_field: "개발" | "기획·PM" | "디자인" | "마케팅" | "영업" | "데이터"
// years_segment: "1-3" | "4-6" | "7-10" | "10+"
{ "job_field": "개발", "job_detail": "백엔드", "years_segment": "4-6" }
```
응답 200, 저장된 프로필 그대로 반환(항상 3개 필드 전체를 덮어씀). `job_detail`은
직군별 하위 선택지가 아직 다 정해지지 않아 자유 문자열로 둔다 — 생략 가능.

---

## 변경 규칙

이 문서를 바꾸면 **Track C에 즉시 알린다.**
필드를 제거하거나 이름을 바꾸는 변경은 프론트 작업 중에는 하지 않는다.
추가는 자유롭다.

### 구현 시점 알려진 차이 (9/13, FastAPI 구현)

- **1장 `created_at`**: 위 예시는 타임존 포함 datetime(`"...T18:45:00+09:00"`)이지만,
  실제 구현은 저장소가 가진 값(`"2026-02-14"`, 날짜만)을 그대로 반환한다. 저장소 계약
  (`save_card`)을 조율 없이 바꾸지 않기 위한 판단. 시각까지 필요하면 Track B와 논의 후
  `save_card`/`run_pipeline`부터 바꿀 것 — API 레이어만 고쳐서 해결되지 않는다.
- 나머지 필드/모양은 문서 그대로 구현함 (`tasks/track-b-agent-pipeline.md` 6부 참고).

### 3장 `source_card_ids` 필드 추가 (9/14)

`/stack`의 "인과관계로 묶어보기"에서 같은 날짜에 카드가 여러 장 있을 때 `source_dates`
문자열 매칭만으로는 정확히 어느 카드인지 구분이 안 돼 무관한 카드가 섞이는 버그가
실제로 발견됐다. `source_card_ids`(카드 id 정수 배열)를 추가해서 그 문제를 해결함 —
필드 추가라 "변경 규칙"상 자유롭게 허용되는 범위. `source_dates`는 그대로 유지(화면
표시용).
