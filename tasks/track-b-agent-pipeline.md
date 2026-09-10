# Track B — AI 에이전트 빌드 및 MCP 인프라 (9/13~9/15)

가장 리스크가 높은 트랙. 반드시 `docs/03-risk-fallback.md`를 먼저 읽고 타임박스를 지킬 것.

## 목표 (우선순위 순서 — 위에서부터 완료)

### 1. Vector DB 매칭 파이프라인 (필수)
`src/agent/vectorstore.py`
```python
def build_jd_index(jd_dir: str = "data/mock_jds") -> None:
    """data/mock_jds/*.json을 임베딩해서 Chroma 인덱스를 (재)구축한다."""
    ...

def match_jds(skill_tags: list[str], top_k: int = 5) -> list[dict]:
    """역량 태그로 유사 JD를 top_k개 반환한다. 반환 형식은 mock_jds JSON 스키마와 동일."""
    ...
```
- `data/mock_jds/`에 최소 15~20개 가상 원티드 JD JSON을 만들어둔다 (직무, 요구 역량, 회사명 등)
- 배포 시 재임베딩 전략을 쓸 것이므로(리스크 문서 참고) `build_jd_index()`는 멱등하게 설계

### 2. 파이프라인 오케스트레이션 (필수)
`src/agent/pipeline.py`
```python
def run_pipeline(raw_text: str) -> dict:
    """
    parsing.parser.parse_note() -> agent.vectorstore.match_jds() 순서로 실행하고
    프론트엔드가 그대로 렌더링할 수 있는 dict를 반환한다.
    반환 예시: {"parsed": ParsedEntry, "matched_jds": [...]}
    """
    ...
```

### 3. 노션 연동 — 투트랙 (필수: REST / 선택: MCP)
`src/agent/notion_client.py`
- **1차(필수)**: `fetch_notion_entries()` — Notion 공식 REST API로 개인 업무 일지 페이지를
  긁어와 텍스트 리스트로 반환
- **2차(선택, 타임박스 하루)**: `fetch_notion_entries_via_mcp()` — 오픈소스 MCP 서버 연동.
  하루 안에 안 되면 즉시 중단하고 1차안 유지

## 작업 항목
- [ ] `data/mock_jds/*.json` 최소 15개 작성
- [ ] Chroma 인덱스 빌드 스크립트 및 재현성 확인 (재실행해도 같은 결과)
- [ ] `run_pipeline()` 통합 테스트 (Track A 결과물과 실제로 연결해서 검증)
- [ ] Notion REST API 연동 (개인 워크스페이스 토큰으로 테스트)
- [ ] (선택) Notion MCP 연동 시도 — 타임박스 초과 시 중단 기록을 `docs/03-risk-fallback.md`에 남길 것

## 완료 기준
- `run_pipeline(raw_text)` 호출 하나로 파싱+매칭 결과가 나온다
- 노션 연동은 최소 REST API 경로 하나는 반드시 동작해야 함
