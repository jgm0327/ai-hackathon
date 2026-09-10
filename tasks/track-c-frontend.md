# Track C — Streamlit 화면 구현 및 전체 루프 결합 (9/16~9/17)

## 목표
UX/UI 에셋을 반영한 Streamlit 프론트엔드를 구현하고, 유저 입력 또는 노션 동기화
버튼 클릭 시 역량 그래프와 매칭 공고 카드가 갱신되는 전체 루프를 완성한다.

## 사전 확인 사항 (반드시 숙지)
- Chart.js 대신 **Plotly/Altair** 사용 (`docs/02-architecture.md` 참고)
- "실시간 갱신"은 Streamlit rerun + `st.session_state` 기반. 버튼 클릭 시 재실행되는
  구조를 전제로 화면을 설계할 것 (진짜 웹소켓 실시간 push 아님)

## 산출물
`src/frontend/app.py` (엔트리포인트) + `src/frontend/components/`
- `components/skill_chart.py`: 역량 태그 빈도/카테고리를 Plotly 바/레이더 차트로 렌더링
- `components/jd_cards.py`: 매칭된 JD를 카드 형태로 렌더링 (회사명, 직무, 매칭 스킬 하이라이트)

## 작업 항목
- [ ] `st.session_state`에 `parsed_history`(누적 파싱 결과), `matched_jds`(최신 매칭 결과) 정의
- [ ] 텍스트 입력창 + "분석하기" 버튼 → `agent.pipeline.run_pipeline()` 호출 → 결과를
      session_state에 반영 → 재실행 시 그래프/카드 갱신
- [ ] "노션 동기화" 버튼 → `agent.notion_client.fetch_notion_entries()` → 여러 건을
      일괄로 `run_pipeline()`에 통과시켜 누적 반영
- [ ] UX/UI 디자이너 에셋(색상, 레이아웃) 반영 — CSS는 `st.markdown(..., unsafe_allow_html=True)`
      최소한으로만 사용
- [ ] 로딩 상태 표시 (`st.spinner`) — LLM 호출 중 화면이 멈춘 것처럼 보이지 않게

## 완료 기준
- 텍스트 입력 → 분석하기 클릭 → 그래프/카드가 화면에서 바뀌는 것을 눈으로 확인
- 노션 동기화 버튼도 동일하게 동작
- 9/16 저녁까지 최소 기능 버전으로 한 번 로컬 데모가 되는 상태 (Track D 사전 배포 테스트를 위해)
