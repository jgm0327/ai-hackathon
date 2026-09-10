# 아키텍처 개요

## 전체 흐름
```
[유저 입력: 낙서 문장]
        │
        ▼
[Track A] parsing.parser.parse_note()
  - LLM 프롬프트로 정제 문장 + JSON 역량 태그 추출
        │
        ▼
[Track B] agent.pipeline.run_pipeline()
  - 파싱 결과 임베딩
  - agent.vectorstore에서 가상 JD 세트와 유사도 매칭
  - (선택) agent.notion_client로 노션 업무 일지 동기화
        │
        ▼
[Track C] frontend.app (Streamlit)
  - 역량 그래프(Plotly) 렌더링
  - 매칭 공고 카드 렌더링
  - session_state로 "실시간처럼" 갱신
        │
        ▼
[Track D] 배포 (Streamlit Community Cloud)
```

## 기술 선택 사유

### 왜 Chart.js가 아니라 Plotly/Altair인가
Streamlit은 Chart.js를 네이티브로 지원하지 않는다. `st.components.v1.html`로 iframe에
직접 심어야 하며, Streamlit의 rerun 모델과 JS 상태를 동기화하는 게 번거롭고 디버깅 시간이
예상보다 많이 든다. Plotly/Altair는 `st.plotly_chart()` / `st.altair_chart()`로 한 줄에
붙고 session_state와 자연스럽게 연동된다. 디자이너 에셋이 Chart.js 전용 스펙으로 이미
확정된 게 아니라면 Plotly/Altair로 대체하는 것을 권장한다.

### "실시간 갱신"의 실제 구현 방식
Streamlit은 위젯 상호작용(버튼 클릭 등)마다 스크립트 전체를 재실행(rerun)하는 모델이다.
"노션 동기화 버튼 클릭 시 실시간으로 그래프가 바뀐다"는 요구사항은 진짜 서버 푸시가
아니라, 버튼 클릭 → `st.session_state`에 새 데이터 반영 → 스크립트 재실행 → 그래프
재렌더링의 흐름으로 구현한다. 이 전제를 프론트엔드 담당 에이전트가 먼저 이해하고
설계해야 나중에 구조를 갈아엎는 일이 없다.

### Vector DB: Chroma
로컬 개발 단계에서는 Chroma가 설정이 가장 간단하다. 다만 기본적으로 로컬 디스크에
파일 기반으로 저장되기 때문에, 클라우드 배포 환경(특히 Streamlit Community Cloud처럼
컨테이너가 재시작될 수 있는 환경)에서는 데이터가 유실될 수 있다. 이에 대한 대응은
`docs/03-risk-fallback.md`를 참고.

### Notion 연동: REST API 우선, MCP는 선택
오픈소스 Notion MCP 서버는 생태계가 아직 어리고 구현체마다 인증/안정성 편차가 크다.
해커톤 기간 안에 안정적인 데모를 보장하려면 공식 Notion REST API로 먼저 연동을
완성하고, 시간이 남을 때 MCP로 교체를 시도하는 방식이 안전하다.
