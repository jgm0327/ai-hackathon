# Track F — STT 음성 입력 (9/11 착수)

**상태: 구현 완료 (Web Speech API 경로).** 9/11에 착수 결정, 그대로 구현함.

## 아이디어
퇴근길 차 안처럼 손이 자유롭지 않을 때 "오늘 한 일"을 말로 얘기하면, STT로 텍스트로
바꾼 뒤 기존 `pipeline.run_pipeline()`에 그대로 태워서 **분석 + 등록까지 자동으로**
끝낸다 (수동으로 "분석하기"를 누를 필요 없음).

## 구현 방식: Web Speech API 채택
`tasks/track-f-stt-voice-input.md`(구버전)에서 제안한 두 후보 중 Web Speech API로
착수함 — 별도 API 키/서버 불필요, 브라우저 내장.

## 산출물
- `src/frontend/components/voice_input.py`
  - `render_voice_input_widget()`: "🎤 말로 기록하기" 버튼. 클릭 시
    `SpeechRecognition`(`ko-KR`, `continuous=false`)을 시작, 최종 인식 결과를
    base64(UTF-8 안전 인코딩)로 쿼리 파라미터(`voice_text`)에 실어 메인 페이지로
    리다이렉트.
  - `handle_pending_voice_entry()`: `voice_text` 쿼리 파라미터를 읽어 디코딩하고
    `run_pipeline()`을 호출, 결과를 반환 (app.py가 `session_state.results`에 추가).
- `tests/test_voice_input.py`: `handle_pending_voice_entry()`의 디코딩/파이프라인
  호출/쿼리 파라미터 정리 로직 테스트 (JS 쪽 음성 인식 자체는 단위 테스트 불가 영역).
- `app.py`: `col_input`에 위젯 연결, 최상단에서 `handle_pending_voice_entry()` 호출.

## 구현 노트 (9/11)

**cross-frame 문제 없음 — Push 알림 때와 다른 점**: Tier 2 푸시 알림 때는
`window.parent.navigator.serviceWorker`를 빌려 써야 해서 iframe 문제가 컸는데,
`SpeechRecognition`은 **컴포넌트 iframe 자기 자신의 컨텍스트에서 바로 동작**한다.
Streamlit의 `components.html()` iframe은 `allow` 속성에 이미 `microphone`이 포함돼
있어서(직접 확인함) 별도 우회 없이 마이크 권한을 요청할 수 있다.

**마이크 권한도 버튼 클릭 안에서 시작해야 함**: `Notification.requestPermission()`과
동일하게, `recognition.start()`를 자동으로(페이지 로드 등에 얹어서) 호출하면 최신
Chrome이 사용자 제스처 없음으로 판단해 조용히 막을 수 있음 — 처음부터 버튼 클릭
핸들러 안에서 시작하도록 구현함(이 문제를 Tier 1/2에서 이미 겪어서 처음부터 회피).

**한글 인코딩**: `btoa()`는 Latin1만 지원해서, 한글을 그대로 넣으면 깨진다.
JS에서 `btoa(unescape(encodeURIComponent(transcript)))`로 UTF-8 바이트로 풀어준 뒤
인코딩하고, Python에서 `base64.b64decode(...).decode("utf-8")`로 그대로 복원한다.

**결과를 바로 등록(수동 확인 단계 없음)**: 사용자가 원문 그대로 "말하면 등록까지"를
요청해서, 인식된 텍스트를 텍스트 입력창에 채워주고 기다리는 대신 곧바로
`run_pipeline()`을 호출하도록 구현함. STT 오인식 시 잘못된 내용이 그대로 분석/등록될
리스크가 있음 — 실사용 중 오인식이 잦으면 "인식 결과 확인 후 등록" 방식(텍스트
입력창에 채우기만 하고 별도 확인 버튼)으로 바꾸는 걸 고려할 것.

## 버그 및 수정 (9/11, 실사용 중 발견)

**증상**: "인식 중: ..."까지는 뜨는데 등록으로 안 넘어감 (실사용자 리포트: "밑에만
나오고 기록이 안 되는데").

**원인 진단**: 파이썬 쪽(`handle_pending_voice_entry` → `run_pipeline` → 결과 반영)은
쿼리 파라미터를 직접 조작해서 재현 테스트한 결과 **완전히 정상 동작**함을 확인함
(매칭 공고까지 정상 반영됨). 문제는 JS 쪽 — Chrome의 `SpeechRecognition`이
`isFinal: true` 결과 없이 그냥 조용히 `onend`로 종료되는 경우가 실제로 있음(Chrome의
알려진 동작). 원래 코드는 `isFinal`이 와야만 제출하도록 짜여있어서, 이 경우 영원히
제출이 안 됐음.

**수정**: `isFinal`에만 의존하지 않고, `recognition.onend`에서 "아직 제출 안 됐으면
그때까지 모인 텍스트(`latestTranscript`)로 대신 제출"하는 폴백을 추가함
(`submitted` 플래그로 중복 제출 방지). 이제 `isFinal`이 오든 안 오든, 인식이 끝나는
시점에는 반드시 제출 시도가 일어난다.

## 완료 기준
- [x] 코드 구현 완료, `handle_pending_voice_entry()` 유닛 테스트 통과 (4개)
- [x] 파이썬 쪽 등록 로직 재현 테스트 완료 (쿼리 파라미터 직접 주입 → 매칭 공고까지
  정상 반영 확인, 9/11)
- [x] `isFinal` 누락 시 무한정 등록 안 되는 버그 수정 (9/11, `onend` 폴백 추가)
- [ ] **실제 마이크로 말해서 등록까지 확인 — 수정 후 재테스트 필요** (마이크 권한
  팝업은 브라우저 자동화가 처리할 수 없는 영역이라 사용자 확인 필수)
- [ ] 실제 차량 환경(주행 소음 있는 상태)에서 인식 품질 확인 — 문제되면 Whisper API로
  교체 검토 (`src/parsing/stt.py` 신설, `voice_input.py`만 교체하면 되도록 설계돼 있음)
