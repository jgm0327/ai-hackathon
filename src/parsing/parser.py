"""낙서 문장 파싱 모듈 — Track A 담당.

주의: ParsedEntry와 parse_note()의 시그니처는 Track B(pipeline.py)가 그대로
가져다 쓰는 고정 계약이다. 변경 시 tasks/track-b-agent-pipeline.md 담당자와 반드시 상의.
"""
import json
from dataclasses import dataclass, field

from src.config import settings
from src.parsing.prompt_templates import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE


@dataclass
class ParsedEntry:
    raw_text: str
    refined_sentence: str
    skill_tags: list[str] = field(default_factory=list)
    confidence: float = 0.0


def _call_llm(raw_text: str) -> str:
    """실제 LLM 호출부. TODO(Track A): Anthropic/OpenAI SDK 클라이언트 초기화 및 호출 구현.

    지금은 자리표시자(placeholder)만 있음 — 실제 구현 전까지 parse_note()는
    이 함수를 모킹해서 테스트한다.
    """
    raise NotImplementedError("Track A: LLM 클라이언트 연동 필요")


def parse_note(raw_text: str) -> ParsedEntry:
    """낙서 문장을 받아 정제 문장 + 역량 태그를 반환한다.

    JSON 파싱 실패 시 최대 1회 재시도한다.
    """
    for attempt in range(2):
        raw_response = _call_llm(raw_text)
        try:
            data = json.loads(raw_response)
            return ParsedEntry(
                raw_text=raw_text,
                refined_sentence=data["refined_sentence"],
                skill_tags=data.get("skill_tags", []),
                confidence=float(data.get("confidence", 0.0)),
            )
        except (json.JSONDecodeError, KeyError):
            if attempt == 1:
                raise
    raise RuntimeError("unreachable")
