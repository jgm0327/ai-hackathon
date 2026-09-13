# Track C — Streamlit 프론트엔드 (9/13 이전, Next.js 전환 전 기록)

각 트랙(A~E)마다 하나의 누적 로그 파일을 둔다. **작업 세션이 끝날 때마다**
(하루 작업 끝, 또는 하나의 작업 항목을 완료했을 때) 해당 트랙 파일 맨 아래에
`TEMPLATE.md` 형식으로 새 항목을 추가한다.

> 9/13 CLAUDE.md 대개편으로 Streamlit 프론트엔드는 폐기되고 Next.js로 전환됐다
> (`docs/06-migration.md` 참고). 아래는 폐기되기 전까지의 작업 기록이다 — 특히
> "왜 Streamlit을 버렸는가"에 대한 직접적인 증거 자료라 삭제하지 않고 남겨둔다.

---

## 2026-09-10~09-13 (세션 1, tasks/track-c-frontend.md에서 이관 + 회고 추가)

### 오늘 한 일
- `src/frontend/app.py` + `components/`(skill_chart, jd_cards, reminder) 구현 — 텍스트
  입력/노션 동기화 → `run_pipeline()` → 역량 그래프(Plotly)/매칭 공고 카드 갱신하는
  전체 루프를 `st.session_state` 기반으로 완성.
- (9/11) 프론트엔드 서브에이전트가 레이아웃/그래프/카드 완성도 개선 (색상 그라데이션,
  `st.badge()`, 반응형 컬럼 gap 등) — 디자인 시안이 없는 상태에서 기존 구조를 유지한 채
  마감도만 높임.

### 트러블슈팅 — 이게 결국 Streamlit을 버린 이유가 됨
- **문제**: Tier 2 웹 푸시(`push_setup.py`)에서 서비스워커를 `window.parent.navigator
  .serviceWorker`로 등록하려는데, `components.html()`이 만드는 `about:srcdoc` 샌드박스
  iframe 안에서 cross-frame 등록이 계속 멈추거나 실패함.
- **원인 추정**: iframe 안에서의 서비스워커 등록 자체가 근본적으로 불안정한 구조였음.
- **해결/우회**: 당시에는 독립된 정적 페이지(`subscribe.html`)로 우회해서 해결했음
  (`tasks/track-e-push-notifications.md` 상세 기록 참고). 다만 이 우회 자체가 "Streamlit
  안에서 마이크/PWA/푸시를 정상적으로 쓸 수 없다"는 근본 한계를 보여주는 증거가 됨.

- **문제**: `install_button.py`(PWA "홈 화면에 추가")에서 서비스워커를 scope `"/"`로
  등록하려 하니 `SecurityError: ... scope ('/') is not under the max scope allowed
  ('/app/static/')`.
- **원인 추정**: Streamlit이 정적 파일을 `/app/static/` 하위에서만 서빙해서, 그 경로에서
  서빙되는 서비스워커는 그 이하로만 scope를 가질 수 있음. `manifest.json`의
  `start_url: "/"`와 구조적으로 안 맞음.
- **해결/우회**: 당시엔 scope 지정을 생략해서 에러만 피하고 넘어갔음(`beforeinstallprompt`
  자체는 별개로 동작 확인됨). 근본적으로는 해결이 아니라 회피였음.

### 회고 / 생각
- 이 두 문제(서비스워커 cross-frame 등록, scope 제한)와 마이크 권한 문제(Track F 로그 참고)가
  전부 "Streamlit의 `components.html`이 만드는 iframe 샌드박스" 하나의 근본 원인에서
  나왔다는 걸 9/13에 다시 정리하면서 깨달음 — `install_button.py`/`push_setup.py`/
  `voice_input.py`에 남긴 "구현 노트" 주석들이 사실상 "Next.js로 가야 하는 이유"를
  스스로 기록해온 셈이었다.
- 각각을 개별 버그로 우회하며 넘어갔지만, 돌아보면 "왜 이 우회가 필요했는가"를 더 일찍
  하나로 묶어 봤다면 프레임워크 전환 판단을 더 빨리 할 수 있었을 것. 개별 버그 픽스에
  매몰되지 않고 주기적으로 "이 문제들의 공통 원인이 뭔가"를 되짚어보는 게 중요하다는 교훈.
