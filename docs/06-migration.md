# 이식 가이드: Streamlit → Next.js (신규, 2026-09-13)

Track E(웹푸시)와 Track F(음성 입력)는 **이미 구현이 끝나 있다.**
새로 만들지 말고 이식한다. 상세 배경은 `tasks/track-e-push-notifications.md`,
`tasks/track-f-stt-voice-input.md`를 참조한다.

---

## 0. 이식의 핵심 — 대부분이 삭제 작업이다

기존 `src/frontend/components/`의 상당량은 **기능 코드가 아니라 iframe 우회 코드**다.
Next.js에서는 그 우회가 전부 불필요해진다.

| 기존 코드 | Next.js에서 |
|---|---|
| `window.parent.document`로 manifest 주입 | `app/manifest.ts` — 삭제 |
| `beforeinstallprompt` 가로채기 + 수동 안내 폴백 | 브라우저 기본 동작 — 대폭 축소 |
| scope `/app/static/` 우회 시도 | 루트 등록 — 삭제 |
| `components.html` 래핑 | 일반 컴포넌트 — 삭제 |

**코드가 줄어드는 방향이다.** 기존 로직을 그대로 옮기려 하지 말고,
"이 코드가 왜 있었는지"를 먼저 보고 iframe 때문이면 지운다.

---

## 1. 웹푸시 (Track E)

### 그대로 쓰는 것
- **VAPID 키 쌍** — 재발급 불필요. `.env`에 그대로
- **`src/agent/push_sender.py`** — 서버 측 발송 로직. 수정 없음
- **GitHub Actions 크론** — 스케줄 트리거. 엔드포인트 URL만 OCI 도메인으로 교체
- **구독 저장소** — Upstash Redis 유지 또는 SQLite로 이전.
  SQLite로 옮기면 외부 의존이 하나 줄지만, 이미 동작하므로 **P0 완료 전에는 손대지 말 것**

### 새로 쓰는 것
```
public/service-worker.js     ← 기존 service-worker.js 내용 거의 그대로
app/manifest.ts              ← 기존 manifest.json을 Next 형식으로
components/PushSetup.tsx     ← 구독 요청 UI (기존 push_setup.py의 JS 부분만)
```

### 서비스워커 등록
```ts
// 루트 scope로 등록된다 — Streamlit에서 막혔던 바로 그 지점
navigator.serviceWorker.register("/service-worker.js");
```

nginx가 `/service-worker.js`를 **루트 경로에서** 서빙하는지 반드시 확인할 것
(`tasks/track-d-deploy.md` 3.4).

### 구독 전송
`POST /api/push/subscribe` (`docs/05-api-contract.md` 7장).

### 검증
- [ ] 실기기에서 권한 요청이 뜨는가
- [ ] 구독이 서버에 저장되는가
- [ ] 크론이 실제로 알림을 보내는가
- [ ] iOS는 **홈 화면에 추가한 상태에서만** 웹푸시가 동작한다. 사파리 탭에서는 안 뜬다

---

## 2. 음성 입력 (Track F)

### 먼저 할 것 — 9/13 실기기 검증

**이식 방식이 검증 결과에 따라 갈린다.** 결과 없이 시작하지 말 것 (CLAUDE.md 8장).

| 검증 결과 | 이식 방식 |
|---|---|
| 양쪽 성공 | Web Speech API 이식 (2.1) |
| iOS만 실패 | 녹음 + STT 폴백 (2.2) |
| 양쪽 실패 | iframe 문제였음 → 2.1로 이식하면 해결 |

### 2.1 Web Speech API 이식
```
components/VoiceInput.tsx
```
기존 `voice_input.py`의 JS 로직을 그대로 가져온다.
`components.html` 래퍼와 Streamlit 쿼리 파라미터 전달 부분은 삭제하고,
인식 결과를 React state로 받는다.

**마이크 권한이 페이지 소유가 되므로 `allow="microphone"` 문제가 사라진다.**

### 2.2 녹음 + STT 폴백
```
MediaRecorder로 녹음 → Blob → POST /api/stt → 텍스트
```
실시간 자막이 아니라 **녹음 버튼 하나**짜리 UX가 된다.
운전 중 시나리오는 어차피 정차 후 한 번 말하는 쪽에 가깝다.

> **UX가 바뀌므로 디자인에 즉시 공유할 것.** 실시간 자막이 흐르는 화면과
> 녹음 버튼 하나짜리 화면은 다르게 그려야 한다.

### 2.3 운전 중 안전 (설계 확인 필요)
운전 중 실사용을 기대한다면 **화면을 보지 않고 끝나는 흐름**이 필요하다.
알림 탭 → 바로 녹음 시작 → 자동 종료 → 확인 없이 저장.

주차 후 사용을 전제한다면 현재 설계로 충분하다.
**이 결정이 안 나면 음성 UX를 확정하지 말 것.**

---

## 3. 버리는 것

```
src/frontend/app.py
src/frontend/components/install_button.py     ← 전체가 iframe 우회
src/frontend/components/push_setup.py         ← JS 부분만 추출
src/frontend/components/voice_input.py        ← JS 부분만 추출
src/frontend/components/reminder.py
src/frontend/components/skill_chart.py        ← Recharts로 재작성
src/frontend/components/jd_cards.py           ← React 컴포넌트로 재작성
.streamlit/
```

`requirements.txt`에서 `streamlit` 제거, `fastapi` / `uvicorn[standard]` 추가.

---

## 4. 이름 정리

제품 방향이 바뀌었으므로 아래 문자열을 갱신한다.

| 위치 | 기존 | 변경 |
|---|---|---|
| `manifest.json` `name` | 신입사원 온보딩 다이어리 | (신규 제품명) |
| `manifest.json` `short_name` | 온보딩다이어리 | (신규 짧은 이름) |
| `README.md` | 온보딩 다이어리 설명 | 커리어 로그 설명 |
| 푸시 알림 문구 | — | 문구 재검토 |

> 제품명이 아직 확정되지 않았다면 **이 작업은 9/18로 미뤄도 된다.**
> P0보다 우선하지 않는다.

---

## 5. 이식 순서

1. Next.js 프로젝트 생성 + API 클라이언트 (`docs/05-api-contract.md` 기준)
2. 화면 4개 골격 (`/`, `/stack`, `/resume`, `/projects`)
3. **음성 이식** — 9/13 검증 결과에 따라 2.1 또는 2.2
4. PWA manifest + 서비스워커 루트 등록
5. 푸시 구독 UI
6. 이름 정리 (선택, 9/18로 미뤄도 됨)

3번을 4·5번보다 먼저 하는 이유는, 음성이 제품 컨셉의 절반이고
실패 시 화면 설계가 바뀌기 때문이다. PWA와 푸시는 실패해도 제품이 남는다.
