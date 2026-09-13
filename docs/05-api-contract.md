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
  "created_at": "2026-02-14T18:45:00+09:00"
}
```

> **JD 매칭을 여기서 하지 않는다.** 이직 준비 때만 필요한 걸 매일 돌릴 이유가 없다.
> 응답은 3~10초 걸린다. 프론트는 스켈레톤을 띄운다.

### `GET /api/cards?project_id=3`
`project_id` 생략 시 전체. 최신순 정렬.

```jsonc
{ "cards": [ /* 위 카드 객체 배열 */ ] }
```

### `DELETE /api/cards/{id}`
응답 204.

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
      "source_dates": ["02.14", "02.17", "03.02"]
    }
  ]
}
```

### 프론트가 반드시 지킬 것

**`result`는 빈 문자열일 수 있다.** 기록에 숫자가 없으면 AI가 지어내지 않고
비워서 반환하도록 설계돼 있다 (CLAUDE.md 2.2).

- 빈 `result`를 "결과 없음"으로 렌더링하지 말 것 — 항목을 숨기거나 되묻기 칩을 노출
- `source_dates`로 "이 문장의 근거" 토글 제공 권장. 데모 신뢰도가 올라간다

> URL을 받는 필드는 없다. **채용공고 크롤링은 구현하지 않는다** (CLAUDE.md 2.4).

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

### `POST /api/push/subscribe`
```jsonc
{ "endpoint": "https://fcm.googleapis.com/...",
  "keys": { "p256dh": "...", "auth": "..." } }
```
응답 201. 기존 Upstash 저장소를 그대로 쓰거나 SQLite로 옮긴다
(`docs/06-migration.md` 참조).

### `DELETE /api/push/subscribe`
응답 204.

---

## 8. 헬스체크

### `GET /api/health`
```jsonc
{ "status": "ok", "db": true, "chroma": true, "llm": true }
```
배포 검증과 발표 직전 확인에 쓴다.

---

## 변경 규칙

이 문서를 바꾸면 **Track C에 즉시 알린다.**
필드를 제거하거나 이름을 바꾸는 변경은 프론트 작업 중에는 하지 않는다.
추가는 자유롭다.
