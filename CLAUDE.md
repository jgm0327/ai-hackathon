# CLAUDE.md — 원티드 AI 해커톤: 신입사원 온보딩 다이어리 프로젝트

이 문서는 이 레포에서 작업하는 모든 코딩 에이전트(Claude Code, Orca worktree 인스턴스 포함)가
가장 먼저 읽어야 하는 최상위 컨텍스트다. 세부 작업 지침은 `tasks/`, 배경 설계는 `docs/`를 참고한다.

## 프로젝트 한 줄 요약
유저가 대충 쓴 업무 낙서("결제 터진 거 막음")를 AI가 정제된 경력기술서 문장 + JSON 역량 태그로
변환하고, 이를 벡터DB에 저장된 가상 원티드 JD 세트와 매칭해 역량 그래프와 추천 공고를
Streamlit 웹에서 실시간처럼(rerun 기반) 보여주는 MVP.

## 마감 및 마일스톤
전체 일정과 각 구간의 우선순위/리스크는 `docs/01-schedule.md`를 반드시 먼저 확인할 것.
요약:
- 9/10~9/12: 파싱 프롬프트 엔진 (Track A)
- 9/13~9/15: 에이전트 파이프라인 + Vector DB + Notion 연동 (Track B) — **가장 리스크 높은 구간**
- 9/16~9/17: Streamlit 프론트엔드 + 전체 루프 결합 (Track C)
- 9/18~9/19 오후: 클라우드 배포 (Track D)
- (선택) 퇴근 15분 전 알림 (Track E) — 메인 4개 트랙 완료 후 여유 시간에만 진행,
  자세한 내용은 `docs/04-push-notifications.md`와 `tasks/track-e-push-notifications.md` 참고

## 병렬 작업 규칙 (Orca / git worktree 기준)
- 각 트랙은 독립된 worktree/브랜치에서 작업한다: `track-a-prompt`, `track-b-agent`, `track-c-frontend`, `track-d-deploy`
- 트랙 간 계약(인터페이스)은 반드시 `src/` 하위 각 모듈의 함수 시그니처와 docstring으로 먼저 고정한 뒤 구현한다.
  예: `parsing.parser.parse_note(raw_text: str) -> ParsedEntry` 시그니처가 확정되면
  Track B는 이 시그니처만 보고 통합 코드를 짤 수 있어야 한다.
- 트랙을 병합하기 전 반드시 `tests/` 아래 해당 트랙 테스트를 통과시킬 것.
- 충돌 방지를 위해 공용 설정은 전부 `src/config.py`와 `.env`로만 관리하고, 각 트랙 코드에 하드코딩하지 않는다.

## 우선순위 원칙 (일정이 밀릴 경우)
1. 파싱 엔진 (Track A) — 절대 축소하지 않음, 핵심 가치
2. 벡터DB 매칭 로직 (Track B의 일부) — MVP 필수
3. Streamlit 데모 화면 (Track C) — 최소한 정적 데이터로라도 동작해야 함
4. Notion 연동 (Track B의 일부) — **REST API 폴백 우선, MCP는 가산점**. 자세한 폴백 조건은
   `docs/03-risk-fallback.md` 참고.
5. 배포 (Track D) — 마지막까지 매일 조금씩 미리 연습 배포해볼 것 (마지막 날 몰아서 하지 않기)

## 기술 스택 확정 사항
- LLM 오케스트레이션: LangChain (Dify는 시간 남으면 검토)
- Vector DB: Chroma (로컬), 배포 시 퍼시스턴스 이슈 있으므로 `docs/03-risk-fallback.md` 확인
- 프론트엔드: Streamlit + **Plotly/Altair** (Chart.js 아님 — 사유는 docs/02-architecture.md)
- Notion 연동: 공식 REST API 우선, MCP는 선택
- 배포: Streamlit Community Cloud 1순위, Vercel은 대안

## 에이전트 작업 시 체크리스트
- [ ] 작업 시작 전 `docs/`와 해당 `tasks/track-*.md`를 읽었는가
- [ ] 함수 시그니처/인터페이스를 변경했다면 관련된 다른 트랙 담당자(에이전트)에게 영향 없는지 확인했는가
- [ ] `.env.example`에 새 환경변수를 추가했는가 (실제 키는 절대 커밋하지 않음)
- [ ] 리스크 구간(Notion MCP, Chroma 퍼시스턴스)에서 하루 이상 막히면 즉시 폴백 전략으로 전환했는가
