# Track E — 퇴근 15분 전 알림 (선택 기능, 타임박스 필수)

> **9/13 CLAUDE.md 대개편으로 Next.js/OCI로 스택이 바뀌었다.** 이 문서의 구현 내용
> (VAPID 키, `push_sender.py`, 구독 저장소 등)은 그대로 유지하되, 이식 절차는
> `docs/06-migration.md` 1장을 참고할 것 — 새로 만들지 말고 이식한다.

> **9/13 후속**: HTTP 레이어(`GET /api/push/vapid-public-key`,
> `POST/DELETE /api/push/subscribe`)를 `src/api/routers/push.py`에 신설함
> (`docs/05-api-contract.md` 7장). `subscription_store.py`에 `delete_subscription()`
> 추가(테스트 포함). 로그인이 없어 endpoint 해시를 user_id로 씀. 프론트(Next.js)
> 이식은 아직 — `docs/06-migration.md` 1장 기준으로 진행 예정.

이 트랙은 **선택 기능**이다. 메인 4개 트랙(A/B/C/D)의 완료 기준을 해치면서까지
투입하지 않는다. 반드시 `docs/04-push-notifications.md`를 먼저 읽을 것.

## 타임박스
- Tier 1: 반나절 이내 (Track C 완료 후 여유 시간에)
- Tier 2: 하루(24시간) 이내. 초과 시 즉시 중단하고 Tier 1로 확정.

## Tier 1 — 탭 열려있을 때 알림 (기본 목표)

### 산출물
`src/frontend/components/reminder.py`
```python
def render_reminder_widget() -> None:
    """퇴근 시각을 입력받고, (퇴근시각 - 15분)에 브라우저 알림을 예약하는
    JS를 st.components.v1.html로 삽입한다."""
    ...
```

### 작업 항목
- [x] Streamlit에서 퇴근 시각 입력 위젯 (`st.time_input`) 추가
- [x] JS `Notification.requestPermission()` 호출 (최초 1회 권한 요청)
- [x] `setTimeout`으로 (퇴근시각-15분) 시점 계산 후 알림 예약
- [x] `app.py`에 `render_reminder_widget()` 연결

### 완료 기준
- [x] 브라우저 탭을 열어둔 채로 테스트 시각을 앞당겨 설정하면 실제로 알림이 뜬다
  — **9/10 버그 발견 및 수정**: 원래 코드가 `Notification.requestPermission()`을
  자동 호출해서 Tier 2와 동일한 이유로 권한 요청이 조용히 씹혀 알림이 전혀 안 떴음.
  "🔔 이 탭 알림 켜기" 버튼 클릭 핸들러 안에서 권한을 요청하도록 수정함.
  **알려진 한계**: 버튼 클릭 후 다른 위젯을 조작해 Streamlit이 rerun되면(예: 낙서 입력,
  분석하기 클릭 등) 이 컴포넌트가 다시 렌더링되면서 예약된 타이머가 초기화된다 — 버튼을
  다시 눌러줘야 함. 탭을 열어두고 아무 조작도 안 하면 문제없음. Tier 1은 애초에
  "저비용/제약 있음"으로 설계된 기능이라 이 한계는 문서화만 하고 더 손대지 않음.

## Tier 2 — 탭 닫아도 알림 (스트레치 목표, 시간 남을 때만)

### 산출물
- `src/frontend/static/manifest.json`, `src/frontend/static/service-worker.js`
  (9/10, repo-root `static/`에서 이동 — 이유는 아래 "구현 노트" 참고)
- `src/push/subscription_store.py`: 구독 정보 저장/조회
- `src/push/push_sender.py`: VAPID 키로 서명해서 실제 푸시 발송 (`pywebpush` 사용)
- `.github/workflows/send-reminder.yml`: 매일 지정 시각에 push_sender 호출하는
  GitHub Actions 스케줄 워크플로
- `src/frontend/components/push_setup.py` (9/10 신규): 버튼 클릭 → SW 등록 →
  구독 → `app.py`로 저장까지 연결하는 프론트엔드 위젯

### 작업 항목
- [x] VAPID 키 쌍 생성하고 `.env`/`.env.example`에 등록 (9/10) — `python -m py_vapid --gen`은
  PEM만 만들어서 PUBLIC_KEY를 못 얻으므로, `py_vapid.Vapid`로 직접 raw base64url 생성함
- [x] 서비스워커 등록 + 구독 발급 JS를 프론트엔드에 삽입 (9/10, `push_setup.py`)
- [x] 구독 정보를 저장할 방법 결정 — JSON 파일(`data/push_subscriptions.json`) 그대로 사용,
  `st.session_state.user_id`(세션별 UUID)로 사용자 구분
- [x] GitHub Actions에서 매일 정해진 시각(유저별 퇴근시각-15분)에 `push_sender.py` 호출
  — 워크플로 자체는 이미 있었음(main에 커밋됨). 구독 데이터 접근 문제는 아래
  "구현 노트"의 Upstash 전환 참고, 9/10 해결.
- [x] 실제 폰/브라우저에서 탭을 완전히 닫은 상태로 알림 수신 테스트 — **9/10 성공**.
  Android 실기기(Chrome) + Cloudflare Tunnel로 구독 완료 → `send_push()` 수동 호출 →
  FCM 201 응답 → **실제 폰에 알림 수신 확인함**. 다만 "정해진 시각에 자동 발송"은
  위 GitHub Actions 항목이 아직 없어서 지금은 수동 트리거로만 검증된 상태.

### 구현 노트 (9/10)

**정적 파일 위치**: Streamlit의 앱 정적 파일 서빙(`[server] enableStaticServing = true`,
`.streamlit/config.toml`에 설정함)은 반드시 **메인 스크립트(src/frontend/app.py)와 같은
디렉토리의 `static/`**에서만 파일을 찾고, URL은 `/app/static/<파일명>`이 된다
(`/static/...` 아님). 그래서 기존 repo-root `static/`을 `src/frontend/static/`으로
옮기고 `manifest.json`/`service-worker.js`/`reminder.py`의 경로를 전부 갱신함.

**자동 트리거 대신 버튼 클릭 방식으로 구현함 (중요)**: 처음엔 퇴근 시각을 입력하면
자동으로 `Notification.requestPermission()`을 호출하도록 만들었는데, 로컬 브라우저로
직접 테스트해보니 최신 Chrome이 "실제 사용자 제스처 없이 호출된 권한 요청"으로 판단해서
프롬프트를 조용히 억제함 — `Notification.permission`이 계속 `"default"`에 머무르고
아무 일도 안 일어남. 그래서 버튼 클릭 이벤트 핸들러 안에서 직접 권한을 요청하도록 바꿈.

**components.html() 이프레임 방식 폐기 → 독립 정적 페이지로 교체 (중요, 9/10 2차 수정)**:
버튼 클릭까지는 잘 됐는데, 실제 브라우저(및 재현 테스트)에서 그 다음 단계
`window.parent.navigator.serviceWorker.register(...)`가 "서비스워커 등록 중..."에서
끝없이 멈추는 문제가 발생함. `components.html()`이 만드는 `about:srcdoc` 이프레임에서
`window.parent`의 서비스워커 컨테이너를 빌려 쓰는 cross-frame 트릭 자체가 근본적으로
불안정한 것으로 판단, **완전히 새 방식으로 교체**함:
- `src/frontend/static/subscribe.html`: 독립된 일반 페이지. 쿼리 파라미터(`vapid`, `leave`,
  `back`)로 필요한 값을 받아 그 페이지 자신의 `navigator.serviceWorker`로 정상 등록/구독한다
  (cross-frame 트릭 없음). 완료되면 `back` URL로 `push_sub`/`push_leave` 쿼리 파라미터를
  실어 리다이렉트.
- `push_setup.py`: 이제 `st.link_button()`으로 위 페이지를 새 탭에서 여는 링크만 렌더링.
  `st.context.url`로 앱의 현재 URL을 얻어 `back` 파라미터를 구성함.

**로컬 검증 상태**: 새 방식으로 "퇴근 시각 설정 → 버튼 클릭 → 새 탭에서 subscribe.html
정상 렌더링 → '알림 켜기' 클릭 → 알림 권한 요청 중..." 까지 재현 확인함 (이전엔 서비스
워커 등록 단계에서 멈췄지만 이번엔 그 이전 단계인 권한 요청에서 정상적으로 대기 상태).
Chrome 네이티브 권한 팝업 자체는 브라우자 자동화 도구가 처리할 수 없는 영역이라, **"권한
허용 → 구독 성공 → save_subscription() 저장 → 실제 푸시 수신"까지 이어지는 마지막 구간은
반드시 사용자가 직접 눌러서 확인해야 함**.

**실기기(Android 등) 테스트용 터널**: `localhost`는 다른 기기에서 접근 불가하고 Web Push는
보안 컨텍스트(HTTPS)가 필요해서, 로컬 Streamlit을 외부에 노출하는 터널이 필요함.
- ngrok 무료 플랜은 쓰지 말 것 — 브라우저 경고 인터스티셜이 `service-worker.js`
  같은 non-navigation 요청에 HTML을 대신 얹어서 서비스워커 등록이 깨짐 (Traffic Policy로
  헤더 우회 시도했지만 무료 플랜에선 안 먹힘).
- 대신 **Cloudflare Tunnel**(`cloudflared tunnel --url http://localhost:8501`)을 씀 —
  경고 페이지 없이 그대로 통과됨, curl로 실제 JS 응답 확인함.

**해결 — GitHub Actions 트리거의 구독 데이터 접근 (9/10, 2차 — Upstash로 최종 확정)**:
처음엔 `docs/03-risk-fallback.md`의 첫 번째 폴백("구독 데이터를 리포에 커밋")으로
GitHub Contents API 방식을 구현했었는데, **저장소를 나중에 public으로 전환할 계획이
생기면서 폐기**함 — 구독 정보(엔드포인트+키, 사실상 브라우저/기기 식별자)가 커밋
히스토리에 영구 노출되는 게 문제였음(파일을 나중에 지워도 과거 커밋엔 남음).
**두 번째 폴백안(외부 스토리지)으로 교체**:
- `src/push/subscription_store.py`가 **Upstash Redis**(REST API, 무료 티어)를 기본
  저장소로 씀 — `HSET`으로 저장, `HGETALL`로 전체 조회. 배포된 앱(쓰기)과 GitHub
  Actions(읽기)가 서로 다른 프로세스라도 이 공용 저장소를 통해 같은 데이터를 봄.
- `UPSTASH_REDIS_REST_URL`/`UPSTASH_REDIS_REST_TOKEN`이 비어있으면 로컬 JSON 파일로
  자동 폴백 (LLM_PROVIDER/EMBEDDING_PROVIDER와 동일한 패턴, 로컬 개발 시 Upstash 없이도
  동작).
- GitHub 커밋 기반 동기화 코드/`GITHUB_TOKEN` 등 관련 설정은 전부 제거함.
- `.github/workflows/send-reminder.yml`에 Upstash 시크릿 2개를 env로 전달하도록 수정.
- `tests/test_subscription_store.py`를 Upstash API 모킹 테스트로 교체 (로컬 폴백,
  HSET 호출 형식, HGETALL 파싱, 빈 결과 처리 — 4개).

**Upstash 설정 방법**: upstash.com 가입(무료) → Redis DB 생성 → DB 상세 페이지의
REST API 섹션에서 URL/TOKEN 확인 → 로컬은 `.env`에, 배포 환경(Streamlit Cloud
Secrets)과 GitHub Actions(Repo Secrets) 양쪽에 동일한 값 등록 (토큰 값을 대화창에
붙여넣지 않도록 주의 — 사용자가 직접 등록).

### 완료 기준
- [x] 브라우저 탭을 완전히 닫은 상태에서도 OS 알림이 뜬다 — **9/10 실기기(Android Chrome)
  검증 완료**.
- [x] 정해진 시각에 GitHub Actions가 자동으로 발송할 수 있는 조건(워크플로 + secrets +
  구독 데이터 접근)이 모두 갖춰짐 — **다만 실제 GitHub Actions 실행을 통한 자동 발송
  자체는 아직 실기기로 최종 확인 전** (로컬 임시 스케줄러로는 확인함).
