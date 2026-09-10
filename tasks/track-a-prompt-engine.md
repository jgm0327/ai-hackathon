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
- [ ] `prompt_templates.py`에 시스템 프롬프트 작성 (예시 입출력 3~5개 few-shot 포함)
- [ ] 엣지케이스 테스트: 너무 짧은 입력("버그 고침"), 다중 사건이 섞인 입력, 비업무적 잡담 입력
- [ ] 모호한 입력에 대해 `confidence`를 낮게 반환하도록 프롬프트에 명시
- [ ] `tests/test_parser.py`에 최소 5개 케이스 스냅샷 테스트 작성
- [ ] JSON 파싱 실패 시 재시도 로직(최대 1회) 포함

## 완료 기준
- 임의의 낙서 문장 10개를 넣었을 때 9개 이상 유효한 `ParsedEntry`를 반환
- `skill_tags`가 Track B의 JD 매칭에 쓰일 수 있는 수준으로 구체적인 단어 (너무 일반적인
  "성실함", "책임감" 같은 태그 금지 — JD 매칭에 쓸모없음)
