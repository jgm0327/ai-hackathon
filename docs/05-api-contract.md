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
{
  "raw_text": "결제 API 느려서 레디스 캐시 붙임",
  "metric_answer": "1.2초 → 0.4초"   // 9/18 신규, 선택 — 아래 설명 참고
}

// 응답 201
{
  "id": 42,
  "project_id": 3,               // 현재 프로젝트에 자동 배정. 없으면 null
  "raw_text": "결제 API 느려서 레디스 캐시 붙임",
  "refined_sentence": "결제 API 응답 지연을 해소하기 위해 Redis 캐싱 레이어를 도입했습니다.",
  "skill_tags": ["Redis", "성능최적화", "결제시스템"],
  "confidence": 0.91,
  "created_at": "2026-02-14T18:45:00+09:00",
  "created_time": "18:45",       // 9/16 신규 — 아래 설명 참고
  "refinement_failed": false,    // 9/15 신규 — 아래 설명 참고
  "case_summary": "오늘 기록은 결제 API 성능 개선 케이스입니다.",  // 9/16 신규 — 아래 설명 참고
  "ai_sentence": "결제 API 응답 지연을 …",   // 9/18 신규 — 아래 설명 참고
  "sentence_edited": false                   // 9/18 신규 — 아래 설명 참고
}
```

> **JD 매칭을 여기서 하지 않는다.** 이직 준비 때만 필요한 걸 매일 돌릴 이유가 없다.
> 응답은 3~10초 걸린다. 프론트는 스켈레톤을 띄운다.

> **`refinement_failed` (9/15 신규)**: LLM 파싱이 실패해도 카드는 반드시 저장된다
> (CLAUDE.md P0 "저장소 없으면 제품이 없다") — 이 경우 `refined_sentence`는 원문과
> 동일하고 `skill_tags`는 빈 배열, `confidence`는 0.0, `refinement_failed`는 true로
> 온다. 이 필드는 DB에 저장되는 값이 아니라 **생성 시점에만** 라우터가 채워 넣는다
> — 이후 `GET`/`PATCH` 응답에서는 항상 `false`.

> **`case_summary` (9/16 신규, Figma 41:139 결과 출력 모달)**: `refined_sentence`를
> 한 문장으로 압축 요약한 문구("오늘 기록은 ~~ 케이스입니다" 형식) — 새로운 사실을
> 지어내지 않는다(2.2). 입력이 모호해 `refined_sentence`가 못 채워지면 빈 문자열.
> `refinement_failed`와 동일하게 DB에 저장되지 않고 **생성 시점에만** 채워지며,
> `GET`/`PATCH` 응답에서는 항상 빈 문자열이다.

> **`metric_answer` (9/18 신규, Figma "02 · 변환 결과" 3.1-q)**: 변환 전 추가 질문에
> 유저가 **직접 답한** 수치. 서버는 이 값을 메모 뒤에 `(결과 수치: …)` 줄바꿈 한 줄로
> 붙여서 저장한다 — 별도 컬럼이 아니라 `raw_text` 자체에 들어가야, 나중에 "다시 만들기"로
> 재파싱해도 그 숫자가 빠지지 않는다. 유저가 타이핑한 값만 들어가므로 CLAUDE.md 2.2
> (숫자 생성 금지)에 어긋나지 않는다. 안 보내면 예전과 완전히 같은 동작.

> **`ai_sentence` / `sentence_edited` (9/18 신규, Figma 3.1-d "문장 수정")**: 그 화면이
> "직접 고친 문장은 다시 변환해도 유지돼요"와 "AI 문장으로 되돌리기"를 동시에
> 약속하므로, AI가 만든 문장과 사람이 고친 문장을 **따로** 보관한다.
> `refined_sentence`는 **지금 보여줄 문장**(수정본이 있으면 수정본),
> `ai_sentence`는 **가장 최근에 AI가 만든 문장**이다. 둘 다 DB에 저장되며
> `GET`/`PATCH` 응답에도 실린다. 마이그레이션 이전 카드는 `ai_sentence`가 `null`이라
> 프론트가 되돌리기 버튼을 안 띄운다.

> **`created_time` (9/16 신규, Figma 100:692 홈 화면 "오늘 남긴 것")**: "HH:MM" 형식,
> 카드가 실제로 만들어진 시각. `created_at`(날짜만)과 달리 이 필드는 **DB에 저장된다**
> (표시 전용이라 `/stack` 주간 스트릭 등 어떤 로직도 이 필드로 판단하지 않는다 —
> 날짜 판단은 여전히 `created_at` 문자열 그대로 비교). 마이그레이션 이전에 저장된
> 카드는 `null`.

### `GET /api/cards?project_id=3`
`project_id` 생략 시 전체. 최신순 정렬.

```jsonc
{ "cards": [ /* 위 카드 객체 배열 */ ] }
```

### `GET /api/cards/skill-summary?project_id=3&top_n=4` (9/16 신규)
홈 화면(Figma 100:692) "무엇이 쌓였나요" 버블 차트 + `/stack` "역량 리스트"
(4.1-h) 공용 — 카드를 대표 태그(`skill_tags[0]`, 없으면 "미분류") 기준으로 묶어
몇 장씩인지 센다. `top_n`(기본값 4) 다음 순위는 전부 "미분류" 하나로 합친다 —
버블 차트는 기본값 그대로(최대 5개), `/stack` 역량 리스트는 개수 제한이 없는
막대 리스트라 `top_n=50`처럼 크게 줘서 사실상 전부 펼쳐 받는다. **태그를 지어내지
않는다(2.2)** — 실제 `skill_tags`에서만 계산.

```jsonc
// 응답 200
{
  "total_cards": 24,
  "categories": [
    { "tag": "캠페인 운영", "count": 8 },
    { "tag": "콘텐츠 기획", "count": 6 },
    { "tag": "ROI/ROAS", "count": 5 },
    { "tag": "그로스 해킹", "count": 3 },
    { "tag": "미분류", "count": 2 }
  ]
}
```

> **9/18**: `/stack`의 역량 리스트가 이 값을 그대로 쓰고, 각 항목은 역량 상세
> (`/stack/skill/<tag>`)로 이어진다. 역량 상세와 `POST /api/resume`의 `skill_tag`는
> 여기와 **같은 규칙**(대표 태그 `skill_tags[0]` 하나로만 판정)을 써야 한다 — 안 그러면
> 목록에 "8"이라고 적힌 역량을 눌렀을 때 기록 수가 안 맞는다.
`categories`의 `count` 합계는 항상 `total_cards`와 같다 — 카드 한 장은 정확히
하나의 카테고리에만 속한다(태그가 여러 개 있어도 대표 태그 하나로만 집계).

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

// 9/18 신규 — "AI 문장으로 되돌리기" (Figma 3.1-d). true면 refined_sentence를
// 무시하고 카드에 보관된 ai_sentence로 되돌린다. 되돌릴 원본이 없으면 400.
{ "revert_to_ai": true }

// 응답 200 — 위 카드 객체와 동일한 모양(refinement_failed는 항상 false)
```

> **9/18**: `refined_sentence`를 보내면 그 카드의 `sentence_edited`가 true가 된다 —
> 그 뒤로 "다시 만들기"(`/refine`)가 그 문장을 덮어쓰지 않는다. 태그만 고치는 요청은
> 이 플래그를 건드리지 않는다.

### `POST /api/cards/metric-question` (9/18 신규)
"3.1-q 변환 전 추가 질문" — 메모에 **성과 수치가 빠졌는지**만 판정해서 질문 하나를
돌려준다. CLAUDE.md 2.2가 정한 "숫자가 없으면 ... 유저에게 되묻는다(건너뛰기 가능)"
경로다. **카드를 만들지 않는다** — 저장은 뒤이은 `POST /api/cards`가 한다(유저가 질문
화면에서 뒤로 나가도 반쯤 저장된 카드가 남지 않게).

```jsonc
// 요청
{ "raw_text": "신규 가입 전환율 떨어져서 배너 문구 A/B 테스트 돌림." }

// 응답 200 — 물어볼 게 있을 때
{ "question": "전환율이 얼마나 올랐나요?", "placeholder": "예: 3.2%p, 12% → 15.2%" }

// 응답 200 — 물어볼 게 없을 때 (프론트는 화면을 건너뛰고 바로 변환한다)
{ "question": "", "placeholder": "" }
```

> **항상 질문이 오지 않는다.** 수치가 원래 안 붙는 일(회의/문서정리)이나 이미 숫자가
> 적힌 메모에는 빈 문자열이 온다 — 매일 쓰는 경로에 화면을 더하지 않기 위한 조건
> (CLAUDE.md 2.1). 판정이 실패해도 예외가 아니라 빈 문자열로 온다: 이건 부가
> 단계라 여기서 막히면 메모 저장 자체가 막힌다(P0).

### `POST /api/cards/{id}/translate` (9/18 신규)
"3.1-b 직무 전환 번역 결과" / "3.1-c 직무 접점 없음" — 같은 기록을 온보딩 2/4에서
고른 **목표 직무** 관점으로 다시 읽어준다. 현재 직무는 프로필에서 읽으므로 요청에
안 싣는다(유저에게 다시 묻지 않는다 — 2.1).

```jsonc
// 요청
{ "target_job": "UX/UI" }

// 응답 200 — 접점이 있을 때 (3.1-b)
{
  "related": true,
  "headline": "오늘 하신 카테고리 재편은 UX 정보 구조 설계로 읽힙니다.",
  "translated_sentence": "사용자의 콘텐츠 탐색 경로를 기준으로 …",
  "suggestion": ""
}

// 응답 200 — 접점이 없을 때 (3.1-c)
{
  "related": false,
  "headline": "오늘 하신 일정 정리는 UX/UI 경험으로 읽기는 어려워요.",
  "translated_sentence": "인스타 발행 일정을 정리하고 담당자를 배정했습니다.",  // 원래 문장 그대로
  "suggestion": "리서치나 구조 설계, 실험을 기록하면 UX/UI와 가까워져요"
}
```

> **결과를 저장하지 않는다.** 카드 하나가 목표 직무마다 다르게 읽힐 수 있는데 그걸 다
> 저장하면 관리 UI가 필요해진다(CLAUDE.md 3장이 AI 그룹핑을 저장하지 않는 것과 같은
> 판단). 남기고 싶으면 복사하거나 "문장 고치기"로 직접 적용한다.
>
> **없는 경험을 만들지 않는다.** 프롬프트가 "원문에 없는 행동/도구/성과/숫자를 추가
> 금지"를 못박고, 원문 숫자는 그대로 옮기게 한다(2.2). 접점이 없으면 억지로 갖다
> 붙이지 않고 `related: false`로 답한다. LLM 호출 실패는 502.

### `POST /api/cards/{id}/refine` (9/15 신규, 9/18 "다시 만들기"로 용도 확장)
카드를 다시 AI로 정리한다. 요청 바디 없음. 성공하면 `skill_tags`/`confidence`와
`ai_sentence`가 갱신된 카드 객체를 200으로 반환한다. 다시 실패하면 500 — 카드가 이미
저장돼 있어 데이터 유실 위험은 없다.

> **9/18**: 원래는 폴백 저장된(원문 그대로인) 카드 복구 전용이었는데, Figma 3.1의
> 액션이 "다시 만들기"로 바뀌면서 정상 카드에서도 불린다. **`sentence_edited`가 true인
> 카드의 `refined_sentence`는 덮어쓰지 않는다** — 새 문장은 `ai_sentence`에만 들어간다
> (3.1-d "직접 고친 문장은 다시 변환해도 유지돼요").

### `POST /api/cards/{id}/metric-answer` (9/18 신규)
"3.1-n 결과 · 수치 없음"의 [지금 채우기]. 3.1-q가 **변환 전에** 묻는 경로라면 이건
**변환 후에** 채우는 경로다.

```jsonc
// 요청
{ "answer": "3.2%p" }

// 응답 200 — 문장이 다시 만들어진 카드 객체
```

> 답한 값은 `raw_text` 뒤에 `(결과 수치: …)` 줄바꿈 한 줄로 붙는다 — 별도 컬럼에 두면
> 나중에 "다시 만들기"로 재파싱할 때 그 숫자만 조용히 빠진다. **사람이 직접 고친
> 문장은 덮어쓰지 않는다**(`sentence_edited`가 true면 새 문장은 `ai_sentence`에만).
> 없는 카드는 404, 빈 답은 422.

### `POST /api/cards/{id}/photos` (9/18 신규)
"4.1-b 첨부한 사진" — 기록 한 건에 사진 한 장을 붙인다. **`multipart/form-data`**로
보낸다(필드 이름 `file`). LLM을 타지 않아서 변환처럼 오래 걸리지 않는다.

```jsonc
// 응답 201
{
  "id": 7, "card_id": 42,
  "original_name": "photo.jpg", "mime_type": "image/jpeg",
  "byte_size": 184320, "created_at": "2026-09-18T18:45:00+09:00"
}
```

- 허용 형식: `image/jpeg`, `image/png`, `image/webp`, `image/gif` (그 외 **415**)
- 크기 한도: `PHOTO_MAX_BYTES`(기본 8MB) 초과 시 **413**
- 장수 한도: `PHOTO_MAX_PER_CARD`(기본 10) 초과 시 **409**
- 없는/남의 카드는 **404**

> **이미지는 DB가 아니라 디스크에 둔다** (`PHOTO_DIR`, 기본 `data/photos`). BLOB으로
> 넣으면 백업 내보내기가 사진까지 통째로 메모리에 올리게 되는데, OCI AMD Micro(RAM
> 1GB)에서 그건 바로 부담이다. DB엔 메타만 남는다.
>
> **서버는 리사이즈하지 않는다.** Pillow를 안 올리는 대신 프론트가 보내기 전에
> canvas로 긴 변 1600px JPEG로 줄인다(`web/lib/imageResize.ts`). 모바일 회선 업로드가
> 빨라지는 부수 효과도 있다(CLAUDE.md 1장 사용 맥락 2).

### `GET /api/cards/{id}/photos` (9/18 신규)
붙인 순서대로 반환한다. `{ "photos": [ /* 위 객체 배열 */ ] }`

### `GET /api/photos/{photo_id}` (9/18 신규)
사진 원본. `<img src>`에 그대로 넣는다 — 같은 출처라 세션 쿠키가 자동으로 실린다.
응답 헤더는 `Cache-Control: private, max-age=31536000, immutable`이다(본인만 볼 수
있는 자원이라 공유 캐시에 담기면 안 되고, 내용은 안 바뀐다). 행은 있는데 파일이
없으면 500이 아니라 **404** — 썸네일 하나만 비우고 화면은 그대로 둘 수 있게.

### `DELETE /api/photos/{photo_id}` (9/18 신규)
응답 204. 없거나 남의 것이어도 204(멱등). **`DELETE /api/cards/{id}`는 그 카드의
사진 행과 파일도 같이 지운다** — Figma 4.1-c가 "되돌릴 수 없어요"라고 명시한다.

### `GET /api/cards/tag-suggestions?project_id=3` (9/18 신규)
"4.1-i 분류 수정" — 역량 태그가 **하나도 없는** 기록마다 가까운 역량 2개를 후보로
돌려준다. 임베딩 기반이고 **LLM을 부르지 않는다**(CLAUDE.md 2.3: 분류는 임베딩).

```jsonc
// 응답 200
{
  "suggestions": [
    { "card_id": 42, "card": { /* 카드 객체 */ }, "suggested_tags": ["그로스 해킹", "콘텐츠 기획"] }
  ],
  "known_tags": ["캠페인 운영", "콘텐츠 기획", "그로스 해킹"]   // "다른 역량에서 고르기"용
}
```

> **없는 역량을 지어내지 않는다.** 후보는 이 유저가 **이미 가진** 역량 이름뿐이다 —
> 역량이 하나도 없는 계정은 `suggestions`/`known_tags`가 둘 다 빈 배열이고, 화면엔
> "직접 추가"만 남는다. **확정은 이 엔드포인트가 하지 않는다**: 사용자가 고른 뒤
> 기존 `PATCH /api/cards/{id}`로 태그를 저장한다. 임베딩 호출 실패는 502.

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
고른 범위의 카드를 묶어 STAR 항목으로 변환한다. **이직 준비 경로 — 무겁게.**

```jsonc
// 요청
{
  // 아래 셋 중 최소 하나로 범위를 지정한다.
  "project_id": 3,            // 예전 계약. 프로젝트 하나. 단독으로 오면 9/18 이전과 동일
  "project_ids": [3, 1],      // 9/18 신규. 여러 프로젝트를 한 문서로("마스터 경력기술서")
  "include_unassigned": true, // 9/18 신규. 프로젝트 없는 기록도 한 구간으로 포함
  "jd_text": "...",           // 선택. 채용공고 본문 붙여넣기. 없으면 일반 초안
  "skill_tag": "캠페인 운영"    // 9/18 신규. 아래 설명 참고
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
      "source_card_ids": [12, 13, 15],
      // 9/18 신규 — 이 항목이 어느 프로젝트 카드에서 나왔는지. 프론트는 이 값으로
      // 프로젝트 헤드(Figma 41:254)를 그린다. 미분류 구간은 project_id가 null이고
      // project_name이 "미분류 기록"이다.
      "project_id": 3,
      "project_name": "A은행 차세대"
    }
  ]
}
```

**범위가 여러 프로젝트여도 프로젝트 경계를 넘어 묶지 않는다.** 서버가 프로젝트마다
따로 `build_resume()`을 부르고(= LLM 호출도 프로젝트 수만큼, 그만큼 느려진다) 결과를
요청이 준 순서대로 이어 붙인다. A은행의 "결제 API 개선"과 B카드의 "결제 API 개선"은
내용이 같아도 별개 경력이기 때문이다(CLAUDE.md 3장) — 한 덩어리로 합치면 경력이
반으로 줄어든다.

> **`skill_tag` (9/18 신규, Figma 4.1-j "이 역량으로 문장 만들기")**: 주면 **대표
> 태그**(`skill_tags[0]`)가 그 역량인 카드만 묶는다. 판정 규칙은
> `GET /api/cards/skill-summary`와 같아야 한다(대표 태그 하나로만) — 역량 목록의
> 숫자와 실제로 묶이는 기록 수가 어긋나면 안 된다. `"미분류"`를 주면 태그가 없는
> 카드가 대상이다.
>
> **프로젝트별로 나눠 부르는 구조는 그대로다.** 역량 기준으로 봐도 A은행의 "결제 API
> 개선"과 B카드의 "결제 API 개선"은 별개 경력이라(CLAUDE.md 3장), 한 덩어리로 합치면
> 경력이 반으로 줄어든다. 9/18 사용자가 "프로젝트 경계 유지"로 확정한 사항이다.

### `GET /api/resume/draft-count` (9/18 신규)
Figma 4.1-h "내 경력기술서  3개" — **저장본 개수**다(아래 4.3 목록과 같은 수).
화면에 띄울 숫자를 짐작하지 않기 위한 엔드포인트다(CLAUDE.md 2.2). `{ "count": 3 }`

### `GET|POST /api/resume/saved`, `GET|DELETE /api/resume/saved/{id}` (9/18 신규)
"4.3 내 경력기술서 (저장본)" — **`/resume/draft`와는 다른 저장소다.** 그쪽은 "작업 중
초안"(프로젝트당 1개, 덮어쓰기)이고, 이건 "이름 붙여 남겨둔 완성본"(여러 개, 지우기
전엔 안 사라짐)이다. 공고마다 다르게 쓴 버전을 나란히 두는 게 목적이다.

```jsonc
// POST 요청
{
  "title": "무신사 · 프로덕트 마케터",
  "content": "# 경력기술서

…",
  "item_count": 3,      // 목록에 그대로 찍히는 숫자 — 아래 설명 참고
  "card_count": 13,
  "jd_based": true      // "공고 기반" 배지
}

// GET /api/resume/saved 응답 200 — 본문(content)은 싣지 않는다
{ "resumes": [ { "id": 7, "title": "…", "item_count": 3, "card_count": 13,
                 "jd_based": true, "created_at": "…", "updated_at": "…" } ] }
```

> **숫자는 저장 시점에 클라이언트가 실제로 센 값을 받아 그대로 보관한다.** 나중에
> 본문을 파싱해서 역산하면 저장 당시와 달라질 수 있고, 그건 목록에 없던 숫자를
> 만들어내는 셈이다(2.2). `card_count`는 항목들의 `source_card_ids` 합집합 크기다
> (같은 카드가 여러 항목에 쓰였어도 한 번만 센다).
>
> 목록 응답에 `content`가 없는 이유: 저장본이 여럿이면 응답이 통째로 무거워진다.
> 본문은 `GET /api/resume/saved/{id}`로 하나만 받는다. 삭제는 204이고 없거나 남의
> 것이어도 204다(멱등).

`project_ids`에 남의 프로젝트 id나 없는 id를 넣으면 조용히 무시된다(다른 유저 데이터
존재 여부를 흘리지 않는 다른 엔드포인트와 같은 규칙).

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

**`project_id`를 생략하면 "마스터 초안"을 조회한다 (9/18 신규).** 범위가 여러
프로젝트인 문서는 프로젝트 하나에 귀속되지 않으므로 유저당 1개짜리 별도 저장소를
쓴다(`master_resume_drafts` 테이블). 이때 응답의 `project_id`는 `null`이다.

### `PUT /api/resume/draft`
```jsonc
// 요청
{ "project_id": 3, "content": "# 결제 API 성능 개선\n..." }

// 응답 200 — 저장된 그대로 반환. project_id가 이 유저 소유가 아니면 404
{ "project_id": 3, "content": "...", "updated_at": "2026-09-14T12:00:05+00:00" }
```
프로젝트당 초안 1개(upsert) — 여러 버전을 관리하는 기능은 없다(CLAUDE.md 2.4 정신:
최소 기능만). **`project_id`가 `null`이면 마스터 초안에 저장한다 (9/18 신규)** —
이쪽은 유저당 1개라 소유권 검사가 필요 없고 404도 나지 않는다.

### `POST /api/resume/enhance` (9/15 신규)

> **9/18**: `POST /api/resume`와 같은 범위 필드(`project_id` / `project_ids` /
> `include_unassigned`)를 받는다 — 화면에서 보고 있는 경력기술서와 같은 범위의 카드를
> 근거로 써야 대조 결과가 어긋나지 않는다. `POST /api/resume/jd-requirements`도 동일.
> 다만 이 둘은 프로젝트 경계를 유지하지 않고 범위 안의 카드를 한 목록으로 합쳐서 본다
> (유저가 준 문장/공고 요구사항의 근거를 찾는 일이라, 근거 카드가 어느 프로젝트에
> 있든 상관없다 — `POST /api/resume`와 다른 점).

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

### `POST /api/resume/jd-requirements` (9/16 신규)

채용 공고 본문에서 요구사항을 뽑아, 프로젝트 카드 중 어떤 것이 각 요구사항에 근거가
되는지 매칭한다(Figma `4.2-j2 공고 요구사항 매칭`). `POST /resume`보다 앞선 단계 —
유저가 JD를 붙여넣으면 이 엔드포인트로 먼저 "요구사항 N개 중 M개에 기록이 있어요"를
보여준 뒤, "이 공고에 맞춰 초안 만들기"를 누르면 그때 `jd_text`를 그대로 `POST
/resume`에 넘겨 실제 초안을 만든다. **JD 텍스트를 URL로 받지 않는다**(2.4 배제 목록).

```jsonc
// 요청
{ "project_id": 3, "jd_text": "백엔드 엔지니어 채용...(공고 본문 전체)" }

// 응답 200
{
  "job_title": "백엔드 엔지니어",       // 공고에 명시 안 됐으면 빈 문자열
  "company": "A은행",
  "years_label": "경력 3~7년",
  "requirements": [
    { "requirement": "캐싱 시스템 설계 경험", "source_dates": ["02.14", "02.18"], "source_card_ids": [12, 13] },
    { "requirement": "Kubernetes 운영 경험", "source_dates": [], "source_card_ids": [] }
  ]
}
```

- `requirements`는 공고 본문에 실제로 적힌 것만 최대 8개까지 추출한다 — 없는 요구사항을
  지어내지 않는다(2.2).
- `source_card_ids`가 빈 배열인 요구사항은 "기록 없음"으로 표시하고 최종 초안에서
  자동으로 제외한다(사용자가 원하면 그 자리에서 새로 기록해 추가할 수 있음).
- 이 매칭 결과 자체는 저장하지 않는다(3장 원칙 — AI가 만든 그룹핑은 비영속).

### `POST /api/resume/star-questions` (9/16 신규)

생성된 STAR 항목 하나를 검토해 면접에서 나올 법한 역질문을 만든다(Figma `4.2-3 AI
역질문`). `StarItem`은 DB에 저장하지 않으므로(3장) 프론트가 들고 있는 값을 그대로
요청 본문에 실어 보낸다.

```jsonc
// 요청
{
  "item": {
    "title": "가입 배너 전환율 개선", "period": "02.14",
    "situation": "...", "task": "...", "action": "가입 배너 문구를 A/B 테스트했습니다.",
    "result": "전환율을 3.2%p 개선했습니다.",
    "source_dates": ["02.14"], "source_card_ids": [1]
  }
}

// 응답 200
{ "questions": ["왜 그 문구였나요? 다른 안도 있었을 텐데요."] }
```

- 이미 인과관계와 근거가 충분한 항목이면 `questions`가 빈 배열로 온다 — 억지로 질문을
  만들지 않는다. 프론트는 빈 배열이면 이 흐름 자체를 건너뛴다.
- 최대 3개까지만 온다.

### `POST /api/resume/star-apply-answers` (9/16 신규)

위 역질문에 대한 사용자 답변을 STAR 항목에 반영한다(Figma `4.2-2 Before·After 모드
B`). 건너뛴(빈 답변) 질문은 프론트가 보내지 않아도 되고, 보내도 서버가 무시한다.

```jsonc
// 요청
{
  "item": { /* star-questions와 동일한 형태 */ },
  "answers": [
    { "question": "왜 그 문구였나요?", "answer": "이탈이 문구 단계에 몰려 있어서" }
  ]  // 최대 3개
}

// 응답 200
{
  "updated_item": { /* item과 동일한 형태, action 또는 result 필드만 바뀜 */ },
  "changed_field": "action"
}
```

- `updated_item`에는 원래 항목 정보와 사용자가 직접 답한 내용만 반영된다 — 사용자가
  말하지 않은 새 사실/숫자를 추가하지 않는다(2.2). 이 검증은 `source_indices`처럼
  코드로 재확인할 수 있는 구조적 근거가 아니라 프롬프트 제약에 의존한다 — 자유
  서술 병합이라 `build_resume()`의 인과 묶기 품질과 동일한 신뢰 수준이다.
- `source_dates`/`source_card_ids`는 그대로 유지된다(새 카드 근거가 생긴 게 아니라
  사용자가 그 자리에서 직접 쓴 답변이 근거이므로).
- 답변을 전부 건너뛰면(빈 답변만 옴) LLM을 호출하지 않고 원본 `item`을 그대로
  돌려준다.

### `POST /api/resume/export/docx` (9/16 신규)

경력기술서를 Word(.docx)로 내보낸다. 그동안 프론트에서 `disabled` + "준비 중"으로
막아뒀던 버튼을 실제로 구현한 것 — LLM을 호출하지 않는 순수 변환 엔드포인트다.

```jsonc
// 요청
{ "content": "# 백엔드 · 1-3년차\n\n## 결제 API 성능 개선\n- 상황: ...\n- 결과: ...\n" }

// 응답 200 (JSON 아님) — Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document
// Content-Disposition: attachment; filename="resume.docx"
<바이너리 .docx 파일>
```

- `content`는 프론트가 이미 "마크다운 복사" 버튼에 쓰는 텍스트와 동일하다
  (`buildResumeMarkdown()`) — 백엔드는 STAR 구조를 다시 조합하지 않고, 화면에서
  보는 것과 다운로드한 문서가 항상 일치하게 한다.
- 지원하는 마크다운은 이 앱이 실제로 생성하는 형태로 한정한다(`# 제목`,
  `## 항목 제목`, `- 불릿`) — 범용 마크다운 파서가 아니다.

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
  "leave_time": "18:00",
  "skip_weekends": true }   // 9/18 신규 — 토·일엔 보내지 않는다. 생략하면 false(매일 발송)
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

> **9/18 개정** — Figma "00 · 온보딩"(`268:5731`) 4단계 재설계에 맞춰 넓어졌다.
> 목표 직무(다중)와 회사·기간이 추가됐고, **연차는 더 이상 받지 않는다**(회사 기간에서
> 서버가 계산). 직군 세트도 바뀌었다.

### `GET /api/profile`
```jsonc
// 온보딩을 아직 안 했으면 job_field/job_detail/years_segment가 null, 나머지는 빈 값
{
  "job_field": "개발",
  "job_detail": "서버 개발자",
  "years_segment": "4-6",      // 아래 companies에서 서버가 계산해 저장한 값
  "target_jobs": ["프로덕트 매니저"],
  "companies": [
    { "name": "A은행", "started_at": "2020-03", "ended_at": null }   // null = 재직 중
  ],
  "total_months": 79           // 겹치는 기간은 한 번만 센 총 재직 개월 수
}
```

**응답의 `job_field`는 Literal로 검증하지 않는다.** 9/18에 직군 세트가 바뀌었는데
그 전에 저장된 값("기획·PM", "데이터")까지 읽기에서 막으면 기존 유저의 프로필 조회가
통째로 500난다. 고정 칩만 허용한다는 원칙(CLAUDE.md 2.4)은 **쓰기 경로에서** 계속 강제한다.

### `PUT /api/profile`
```jsonc
// 요청 — job_field는 아래 고정값만 허용, 그 외는 422
// job_field: "마케팅·광고" | "경영·비즈니스" | "디자인" | "개발" | "영업" | "고객서비스·리테일"
{
  "job_field": "개발",
  "job_detail": "서버 개발자",        // 선택. 직군별 목록은 프론트 분류표(web/lib/jobTaxonomy.ts)
  "target_jobs": ["프로덕트 매니저"],  // 선택, 최대 20개
  "companies": [                      // 생략하면 기존 목록을 건드리지 않는다
    { "name": "A은행", "started_at": "2020-03", "ended_at": null }
  ]
}
```
응답 200, 저장된 프로필 그대로 반환.

**`companies`의 생략(`undefined`)과 빈 배열(`[]`)은 다르다.** 생략하면 기존 회사
목록을 그대로 두고(직무만 고치러 다시 들어온 경우), 빈 배열은 "다 지워라"다.

**`years_segment`는 요청이 보내도 무시된다** — `companies`가 같이 오면 서버가 그
기간에서 계산한 값이 이긴다(`src/career_span.py`). 화면이 보여주는 "6년 3개월"과
저장되는 구간이 어긋난 채로 남는 경우를 아예 만들지 않으려는 것이다. 회사를 하나도
안 넣고 건너뛴 경우에만 요청 값이 쓰인다(그마저도 보통 null).

겹치는 재직 기간은 **한 번만 센다.** 그냥 더하면 실제보다 긴 경력이 나오는데,
경력기술서는 면접에서 검증당하는 문서라 부풀려진 숫자가 나가면 안 된다(CLAUDE.md 2.2).

---

## 10. 백업 내보내기 / 불러오기 (9/18 신규)

Figma "5.0 설정"의 두 행(`41:333` / `41:338`).

**불러오기가 왜 별도 엔드포인트인가**: `POST /api/cards`는 원문을 LLM에 태워 새로
정리하는 경로라 복원에 쓸 수 없다 — 백업에 들어있던 정리 문장/태그가 다른 문장으로
바뀌고, 카드 수만큼 LLM 비용이 발생한다. 이 엔드포인트는 **LLM을 전혀 타지 않고**
저장된 값을 그대로 되살린다.

### `GET /api/backup`
```jsonc
{
  "version": 1,
  "exported_at": "2026-09-18T09:00:00+00:00",
  "projects": [{ "id": 3, "name": "A은행 차세대", "started_at": "2023-02-01", "ended_at": null }],
  "cards": [{
    "id": 12, "project_id": 3,
    "raw_text": "레디스 캐시 붙임",
    "refined_sentence": "결제 API 응답 지연을 해소하기 위해 Redis 캐싱 레이어를 도입함",
    "skill_tags": ["Redis", "성능최적화"], "confidence": 0.9,
    "created_at": "2023-02-14", "created_time": "18:45"
  }]
}
```

### `POST /api/backup/import`
```jsonc
// 요청 — GET /api/backup 응답의 projects/cards를 그대로 보낸다
{ "projects": [...], "cards": [...] }

// 응답 200
{ "imported_projects": 1, "imported_cards": 12 }
```

**덧붙이기다 — 기존 기록을 지우지 않는다.** "복원"이라는 말 때문에 기존 데이터가
날아갈 거라 오해하기 쉬운데, 그런 파괴적 동작은 되돌릴 방법이 없어서 일부러 넣지
않았다. 같은 파일을 두 번 넣으면 카드가 두 벌 생긴다 — 프론트가 누르기 전에 이 사실을
문구로 알린다.

파일 안의 `project_id`는 다른 기기에서 만든 id라 그대로 쓸 수 없다. 프로젝트를 먼저
새로 만들어 옛 id → 새 id 대응표를 만들고 카드를 옮겨 붙인다. 대응표에 없는
`project_id`를 가진 카드는 **버리지 않고 미분류로** 들어간다. 불러오기가 끝나면
현재 프로젝트(`is_current`)는 불러오기 전 상태로 되돌린다 — 백업을 넣었다고 지금
일하는 프로젝트가 바뀌면 안 된다(CLAUDE.md 2.1).

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

---

## 10. 공통 보호장치 (9/17 신규)

전 엔드포인트에 공통으로 걸리는 제한이다. 정상 사용에서는 닿지 않지만, 넘으면
**LLM 호출 전에** 거절되므로 API 비용이 발생하지 않는다.

### 입력 길이 상한

초과 시 `422`. 값은 `src/api/schemas.py` 상단 상수에 모여 있다.

| 필드 | 상한 | 대상 |
|---|---|---|
| `raw_text` | 2,000자 | `POST /cards` |
| `jd_text` | 20,000자 | `POST /resume`, `POST /resume/jd-requirements` |
| `existing_items[]` 각 항목 | 1,000자 (최대 10개) | `POST /resume/enhance` |
| `content` | 100,000자 | `PUT /resume/draft`, `POST /resume/export/docx` |
| `StarItemPayload` 각 문장 | 2,000자 | 역질문 경로 |
| `answers[]` 답변 | 1,000자 (최대 3개) | `POST /resume/star-apply-answers` |

프론트도 같은 값으로 `maxLength`를 걸어 둔다 — 서버 422를 보기 전에 브라우저가 먼저
막는 편이 UX가 낫기 때문이고, 서버 쪽이 진짜 방어선이다(API 직접 호출은 프론트를
거치지 않는다).

### 레이트 리밋

유저별 슬라이딩 윈도(60초). 초과 시 `429` + `Retry-After` 헤더.

| 묶음 | 분당 | 대상 |
|---|---|---|
| heavy | 10회 | `/resume`, `/resume/enhance`, `/resume/jd-requirements`, `/resume/star-*` (Sonnet) |
| light | 30회 | `POST /cards`, `POST /cards/{id}/refine` (Haiku) |
| batch | 3회 | `POST /notion/sync` |

카운터는 **프로세스 메모리**에 있다 — 재시작하면 비고, 워커를 여러 개 띄우면 워커마다
따로 센다. 현재 배포 구성(단일 VM + uvicorn 단일 프로세스)에서는 문제가 없지만, 워커를
늘리는 시점에 `src/api/rate_limit.py`를 공유 저장소 기반으로 교체해야 한다.

### 노션 동기화 페이지 상한

`POST /notion/sync`는 한 번에 최대 **50페이지**만 처리한다(페이지당 LLM 1회). 넘치면
거절하지 않고 앞에서부터 잘라 처리한 뒤 응답의 `skipped`에 남은 개수를 담는다 —
다시 호출하면 이어서 가져간다.

### 요청 본문 크기

`Content-Length`가 **2MB**를 넘으면 본문을 읽기 전에 `413`. 개별 필드 상한은 JSON을
파싱한 뒤에야 동작하므로, 거대한 본문이 메모리에 올라오는 것 자체를 막는 앞단 방어선이다.
