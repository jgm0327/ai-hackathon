# Track A — 프롬프트 엔지니어링

각 트랙(A~E)마다 하나의 누적 로그 파일을 둔다. **작업 세션이 끝날 때마다**
(하루 작업 끝, 또는 하나의 작업 항목을 완료했을 때) 해당 트랙 파일 맨 아래에
`TEMPLATE.md` 형식으로 새 항목을 추가한다.

---

## 2026-09-10~09-12 (세션 1, 9/13 CLAUDE.md 대개편 시 tasks/track-a-prompt-engine.md에서 이관)

### 오늘 한 일
- `prompt_templates.py` 시스템 프롬프트 작성 (few-shot 5개: 정상/모호/짧은 입력/다중 사건/비업무 잡담)
- `parser.py`의 `parse_note()` 구현 — JSON 파싱 실패 시 재시도(최대 1회)
- `tests/test_parser.py` 5개 케이스 작성, 전부 통과
- `LLM_API_KEY` 미발급 상태라 로컬 Ollama(`exaone3.5:2.4b`) 폴백 경로(`LLM_PROVIDER=ollama`)를
  `src/config.py`에 추가해서, 실제 Anthropic 키 없이도 낙서 문장 10개 검증(10/10)을 완료함

### 트러블슈팅
- **문제**: `qwen2.5:3b` 모델로 JSON 강제 출력(`format: "json"`)을 시켜도 `temperature=0`에서
  100% 재현되는 버그 — 응답 키 앞에 `{`가 중복됨 (`{"{refined_sentence": ...}`), 파싱 실패.
- **원인 추정**: 소형 모델의 JSON 스키마 준수 능력 한계로 추정.
- **해결/우회**: `qwen2.5:3b`를 폴백 후보에서 제외하고 `exaone3.5:2.4b`(한국어 특화)로 교체 —
  동일 조건에서 JSON 스키마를 100% 정확히 지킴.
- **참고**: `src/config.py`의 `OLLAMA_MODEL` 기본값.

- **문제**: `exaone3.5:2.4b`가 JSON 스키마는 지키지만, 모호/비업무 입력("오늘 좀 바빴음",
  "슬랙에서 잡담함")에 few-shot 예시(confidence 0.05~0.1)와 다르게 confidence 0.6~0.75로
  높게, 구체적인 스킬 태그까지 만들어냄.
- **원인 추정**: 지시사항 준수도가 낮은 소형 모델의 한계.
- **해결/우회**: 완전히 해결하지 않고 known issue로 남김 — Anthropic 모델(운영 환경)로는
  재현 안 될 가능성이 높다고 판단, 실제 키 확보 후 재검증하기로 함.

### 막힌 채로 남은 것
- Anthropic 실제 API 키로 confidence 캘리브레이션 재검증 (계속 대기 중, 9/13 기준 미해결)

### 회고 / 생각
- "로컬 폴백 provider 스위치"(`LLM_PROVIDER=ollama` vs `anthropic`) 패턴을 여기서 처음
  도입했는데, 이후 Track B의 `EMBEDDING_PROVIDER`(chroma_default/ollama/local_multilingual)
  설계에도 그대로 재사용됐다. "실제 키가 없어도 로컬로 검증 가능한 경로를 항상 만들어둔다"는
  원칙이 프로젝트 전체에 일관되게 적용된 사례.
- 소형 로컬 모델로 검증한 결과를 "확정된 품질"로 착각하지 않고 항상 "운영 모델로 재검증 필요"
  라고 명시적으로 남긴 것이 나중에 판단 실수를 막아줬다.
