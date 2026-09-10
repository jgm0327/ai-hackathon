# Track E — 퇴근 15분 전 알림 (선택 기능, 타임박스 필수)

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
- [ ] Streamlit에서 퇴근 시각 입력 위젯 (`st.time_input`) 추가
- [ ] JS `Notification.requestPermission()` 호출 (최초 1회 권한 요청)
- [ ] `setTimeout`으로 (퇴근시각-15분) 시점 계산 후 알림 예약
- [ ] `app.py`에 `render_reminder_widget()` 연결

### 완료 기준
- 브라우저 탭을 열어둔 채로 테스트 시각을 앞당겨 설정하면 실제로 알림이 뜬다

## Tier 2 — 탭 닫아도 알림 (스트레치 목표, 시간 남을 때만)

### 산출물
- `static/manifest.json`, `static/service-worker.js` (이미 스캐폴드 있음)
- `src/push/subscription_store.py`: 구독 정보 저장/조회
- `src/push/push_sender.py`: VAPID 키로 서명해서 실제 푸시 발송 (`pywebpush` 사용)
- `.github/workflows/send-reminder.yml`: 매일 지정 시각에 push_sender 호출하는
  GitHub Actions 스케줄 워크플로

### 작업 항목
- [ ] VAPID 키 쌍 생성 (`python -m py_vapid` 또는 `pywebpush` 유틸)하고 `.env`에 등록
- [ ] 서비스워커 등록 + 구독 발급 JS를 프론트엔드에 삽입
- [ ] 구독 정보를 저장할 방법 결정 (해커톤 규모면 JSON 파일도 충분, 여러 유저 지원 시
      가벼운 DB 고려)
- [ ] GitHub Actions에서 매일 정해진 시각(유저별 퇴근시각-15분)에 `push_sender.py` 호출
- [ ] 실제 폰/브라우저에서 탭을 완전히 닫은 상태로 알림 수신 테스트

### 완료 기준
- 브라우저 탭을 완전히 닫은 상태에서도 지정 시각에 OS 알림이 뜬다
- 안 되면 즉시 Tier 1로 롤백하고 이 트랙은 중단 (docs/04-push-notifications.md에 기록)
