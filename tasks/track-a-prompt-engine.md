# Track A — AI 프롬프트 엔진 (9/10~9/12)

## 목표
유저의 대충 쓴 낙서 문장을 정제된 경력기술서 문장 + JSON 역량 태그로 변환하는
LLM 시스템 프롬프트를 설계하고 검증한다.

## 산출물 (인터페이스 계약)
`src/parsing/parser.py`에 아래 시그니처를 구현한다. 이 시그니처는 Track B가 그대로
가져다 쓰므로 임의로 바꾸지 않는다.

```python
from dataclasses import dataclass

@dataclass
class ParsedEntry:
    raw_text: str            # 원본 낙서 문장
    refined_sentence: str    # 정제된 경력기술서 문장
    skill_tags: list[str]    # 역량 태그 (예: ["장애대응", "결제시스템", "트러블슈팅"])
    confidence: float        # 0~1, 파싱 신뢰도 (모호한 입력일수록 낮게)

def parse_note(raw_text: str) -> ParsedEntry:
    """낙서 문장을 받아 정제 문장 + 역량 태그를 반환한다."""
    ...
```

## 작업 항목
- [x] `prompt_templates.py`에 시스템 프롬프트 작성 (예시 입출력 3~5개 few-shot 포함) — 5개
- [x] 엣지케이스 테스트: 너무 짧은 입력("버그 고침"), 다중 사건이 섞인 입력, 비업무적 잡담 입력
- [x] 모호한 입력에 대해 `confidence`를 낮게 반환하도록 프롬프트에 명시
- [x] `tests/test_parser.py`에 최소 5개 케이스 스냅샷 테스트 작성 — 5개, 모두 통과
- [x] JSON 파싱 실패 시 재시도 로직(최대 1회) 포함

## 완료 기준
- [x] 임의의 낙서 문장 10개를 넣었을 때 9개 이상 유효한 `ParsedEntry`를 반환
  — **10/10** 검증 완료. 단, `LLM_API_KEY` 미발급 상태라 로컬 Ollama(`exaone3.5:2.4b`)
    폴백으로 검증함 (`LLM_PROVIDER=ollama`, `src/config.py`). Anthropic API 키 발급 후
    동일 10개 문장으로 재검증 필요 — 아래 알려진 이슈 참고.
- [x] `skill_tags`가 Track B의 JD 매칭에 쓰일 수 있는 수준으로 구체적인 단어 (너무 일반적인
  "성실함", "책임감" 같은 태그 금지 — JD 매칭에 쓸모없음)

## 알려진 이슈 (로컬 Ollama 검증 중 발견)
- `exaone3.5:2.4b`(로컬 폴백 모델)는 JSON 스키마는 100% 정확히 지키지만, 모호한/비업무적
  입력("오늘 좀 바빴음", "점심 뭐 먹을지 고민함", "슬랙에서 잡담함")에 대해 프롬프트의
  few-shot 예시(confidence 0.05~0.1)와 다르게 confidence 0.6~0.75로 높게, 구체적인
  스킬 태그까지 만들어내는 경향이 있음 — 지시사항 준수도가 낮은 소형 모델의 한계로 추정.
  Anthropic 모델(운영 환경)로는 재현되지 않을 가능성이 높지만, API 키 확보 후 반드시
  같은 케이스로 confidence 캘리브레이션 재검증할 것.
- `qwen2.5:3b`는 temperature=0에서도 JSON 키 앞에 `{`가 중복되는 버그(`{"{refined_sentence"`)가
  100% 재현되어 폴백 모델 후보에서 제외함.
