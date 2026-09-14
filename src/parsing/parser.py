"""낙서 문장 파싱 모듈 — Track A 담당.

주의: ParsedEntry와 parse_note()의 시그니처는 Track B(pipeline.py)가 그대로
가져다 쓰는 고정 계약이다. 변경 시 tasks/track-b-agent-pipeline.md 담당자와 반드시 상의.
"""
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache

import anthropic
import requests

from src.config import settings
from src.parsing.prompt_templates import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE


@dataclass
class ParsedEntry:
    raw_text: str
    refined_sentence: str
    skill_tags: list[str] = field(default_factory=list)
    confidence: float = 0.0


@lru_cache(maxsize=1)
def _get_client() -> anthropic.Anthropic:
    """Anthropic 클라이언트를 지연 초기화하고 재사용한다 (import 시점에 키 검증 안 함)."""
    return anthropic.Anthropic(api_key=settings.llm_api_key)


def _call_llm_anthropic(raw_text: str) -> str:
    response = _get_client().messages.create(
        model=settings.llm_model,
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": USER_PROMPT_TEMPLATE.format(raw_text=raw_text)},
        ],
    )
    return _extract_text(response)


def _extract_text(response: anthropic.types.Message) -> str:
    """응답의 첫 텍스트 블록을 꺼낸다.

    `content[0]`이 항상 텍스트라고 가정하면 안 된다 — 모델이 ThinkingBlock 등 텍스트가
    아닌 블록을 먼저 반환하면 `content[0].text`에서 AttributeError가 난다(9/14 실제로
    발생: `AttributeError: 'ThinkingBlock' object has no attribute 'text'`, POST
    /api/cards가 500으로 죽으면서 CORS 헤더가 안 붙어 브라우저엔 CORS 에러로 보였음).
    """
    for block in response.content:
        if block.type == "text":
            return block.text
    raise ValueError(f"Anthropic 응답에 텍스트 블록이 없습니다: {response.content!r}")


def _call_llm_ollama(raw_text: str) -> str:
    """로컬 Ollama 서버 호출. LLM_API_KEY 없이 프롬프트를 검증할 때 쓰는 폴백 경로.

    `format: "json"`으로 JSON 강제 출력을 유도한다 (배포용 Anthropic 경로와 별개).
    """
    response = requests.post(
        f"{settings.ollama_base_url}/api/chat",
        json={
            "model": settings.ollama_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_PROMPT_TEMPLATE.format(raw_text=raw_text)},
            ],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0},
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["message"]["content"]


def _call_llm(raw_text: str) -> str:
    """실제 LLM 호출부. `LLM_PROVIDER` 설정에 따라 Anthropic 또는 로컬 Ollama로 분기한다."""
    if settings.llm_provider == "ollama":
        return _call_llm_ollama(raw_text)
    return _call_llm_anthropic(raw_text)


_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL)


def _strip_code_fence(text: str) -> str:
    """LLM이 JSON을 마크다운 코드 펜스(` ```json ... ``` `)로 감싸서 반환하는 경우가
    있다(9/14 실제 발생 — Claude가 이렇게 응답해서 `json.loads()`가
    `Expecting value: line 1 column 1`로 죽고, POST /api/resume이 500이 되는 걸
    실측 재현함). 펜스가 있으면 벗겨내고, 없으면 그대로 둔다 — 두 경우 다 안전하게 처리.
    """
    stripped = text.strip()
    match = _CODE_FENCE_RE.match(stripped)
    return match.group(1).strip() if match else stripped


def parse_note(raw_text: str) -> ParsedEntry:
    """낙서 문장을 받아 정제 문장 + 역량 태그를 반환한다.

    JSON 파싱 실패 시 최대 1회 재시도한다.
    """
    for attempt in range(2):
        raw_response = _call_llm(raw_text)
        try:
            data = json.loads(_strip_code_fence(raw_response))
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
