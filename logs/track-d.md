# Track D — 배포 (Streamlit Cloud → OCI 전환 전 기록)

각 트랙(A~E)마다 하나의 누적 로그 파일을 둔다. **작업 세션이 끝날 때마다**
(하루 작업 끝, 또는 하나의 작업 항목을 완료했을 때) 해당 트랙 파일 맨 아래에
`TEMPLATE.md` 형식으로 새 항목을 추가한다.

> 9/13 CLAUDE.md 대개편으로 배포 대상이 Streamlit Community Cloud에서 OCI VM + nginx로
> 바뀌었다 (`docs/06-migration.md`, `tasks/track-d-deploy.md` 참고).

---

## 2026-09-10~09-13 (세션 1)

### 오늘 한 일
- 실제 Streamlit Cloud 배포는 진행하지 않음 — 사용자가 "배포는 나중에 직접 하겠다"고
  결정해서, 로컬 + Cloudflare Tunnel(임시 터널)로 실기기(Android) 테스트까지만 진행함.
- Cloudflare Tunnel로 실기기 테스트 중 겪은 이슈:
  - ngrok 무료 플랜은 브라우저 경고 인터스티셜이 `service-worker.js` 같은 non-navigation
    요청에 HTML을 대신 얹어서 서비스워커 등록 자체가 깨짐 — Cloudflare Tunnel로 교체해서 해결.
  - 무료 Quick Tunnel은 오래 켜두면(하루 이상) 서버 쪽에서 "Tunnel not found"로 만료됨 —
    재시작하면 새 URL 발급, 매번 갱신 필요.

### 트러블슈팅
- **문제**: `requirements.txt` 전체를 로컬 Python 3.14 환경에 설치하면 `chromadb`가 끌어오는
  `numpy` 빌드가 실패해서 설치 자체가 안 됨.
- **원인 추정**: Python 3.14가 너무 최신이라 numpy 구버전이 사전 빌드 wheel을 제공하지 않음.
- **해결/우회**: 최신 버전으로 전체 업그레이드(Track B 로그 참고). 실제 배포 환경(Linux)의
  Python 버전이 다르면 재검증 필요하다는 점을 남겨둠 — 이게 실제로 배포를 안 해봐서 아직
  검증 안 된 채로 남아있던 리스크였다.

### 막힌 채로 남은 것
- 실제 배포(Streamlit Cloud든 이후 OCI든)를 통한 "새로고침/재시작 후에도 정상 동작" 검증은
  9/13 기준 아직 한 번도 안 해봄 — Chroma 재임베딩 전략이 실제로 배포 환경에서 통하는지도 미검증.

### 회고 / 생각
- CLAUDE.md에 "배포는 마지막까지 매일 조금씩 미리 연습 배포해볼 것 (마지막 날 몰아서 하지
  않기)"이라는 원칙이 처음부터 있었는데, 결국 9/13까지 실제 배포를 한 번도 안 해봤다.
  로컬 검증이 워낙 잘 되다 보니 배포를 미루기 쉬웠던 것 — 정확히 원칙이 경고했던 함정.
  9/13 개편에서 "9/16부터 매일 한 번씩 연습 배포"를 다시 명시적으로 박아둔 이유이기도 하다.
