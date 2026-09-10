# 수정된 해커톤 일정 (리스크 반영)

## 9/10(목) ~ 9/12(토) | AI 프롬프트 엔진 및 사전 테스트 — Track A
- 낙서 문장 → 정제된 경력기술서 문장 + JSON 역량 태그 파싱 프롬프트 엔지니어링
- Few-shot 테스트 및 엣지케이스(모호한 문장, 너무 짧은 입력) 방어 로직까지 완료
- 원래 계획과 동일하게 3일 유지. 여유 있는 구간이므로 앞당겨 끝나면 다음 구간 버퍼로 이전.

## 9/13(일) ~ 9/15(화) | AI 에이전트 빌드 + 데이터 연동 — Track B
우선순위 순서로 진행:
1. **(필수)** LangChain으로 유저 인풋 → AI 파싱 → Vector DB(Chroma) 매칭 파이프라인
2. **(필수)** 가상 원티드 JD 세트 임베딩 및 매칭 로직 테스트
3. **(투트랙)** 노션 연동
   - 1차(필수): Notion 공식 REST API로 개인 업무 일지 긁어오기 → 데모 가능 상태 확보
   - 2차(시간 남으면): 오픈소스 Notion MCP 서버로 교체 시도
   - MCP가 하루 이상 막히면 즉시 1차안으로 롤백하고 다음 구간으로 진행

## 9/16(수) ~ 9/17(목) | Streamlit 화면 구현 + 전체 루프 결합 — Track C
- 차트 라이브러리는 Chart.js 대신 **Plotly/Altair(Streamlit 네이티브)** 사용 (이유: docs/02-architecture.md)
- "실시간 갱신"은 진짜 push가 아니라 **Streamlit rerun + session_state 기반**으로 설계
- UX/UI 에셋 반영한 프론트엔드 + 역량 그래프/매칭 공고 카드 다이내믹 결합

## 9/18(금) ~ 9/19(토) 오후 | 클라우드 배포 및 마감 — Track D
- Streamlit Community Cloud 배포 (Vercel은 대안)
- API 키/시크릿 관리 (Notion 토큰, LLM API 키)
- Chroma 퍼시스턴스 이슈 사전 결정 (docs/03-risk-fallback.md)
- 에러 안정화 최종 점검

## 핵심 변경 3가지 (기존 계획 대비)
1. Notion MCP는 "필수"가 아니라 "가산점" 취급 → REST API 폴백 준비
2. Chart.js → Plotly/Altair 전환으로 Streamlit 통합 리스크 축소
3. Vector DB 퍼시스턴스 문제를 배포 직전이 아니라 미리 결정
