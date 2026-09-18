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
from src.parsing.prompt_templates import (
    JOB_TRANSLATION_SYSTEM_PROMPT,
    JOB_TRANSLATION_USER_TEMPLATE,
    METRIC_QUESTION_SYSTEM_PROMPT,
    METRIC_QUESTION_USER_TEMPLATE,
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
)


@dataclass
class ParsedEntry:
    raw_text: str
    refined_sentence: str
    skill_tags: list[str] = field(default_factory=list)
    confidence: float = 0.0
    # 9/16 신규 — 결과 출력 모달(Figma 41:139) "오늘 기록은 ~~ 케이스입니다" 문구.
    # refined_sentence를 압축 요약한 것일 뿐 새 사실을 담지 않는다(CLAUDE.md 2.2).
    # DB 컬럼이 아니다 — POST /api/cards 응답에만 실리고 저장되지 않는다
    # (refinement_failed와 동일한 패턴, src/api/routers/cards.py 참고).
    case_summary: str = ""


@lru_cache(maxsize=1)
def _get_client() -> anthropic.Anthropic:
    """Anthropic 클라이언트를 지연 초기화하고 재사용한다 (import 시점에 키 검증 안 함).

    timeout을 명시한다 (9/17) — SDK 기본값이 10분이라, 응답이 늦어지면 매일 쓰는 입력
    경로에서 유저가 하염없이 로딩만 보고 그동안 서버 커넥션도 붙잡힌다. 여긴 Haiku로
    보통 1~2초면 끝나는 호출이라 30초면 충분히 넉넉하다. 실패해도 `run_pipeline()`이
    원문을 폴백 저장하므로(pipeline.py 9/15 노트) 메모가 유실되지는 않는다.
    """
    return anthropic.Anthropic(api_key=settings.llm_api_key, timeout=30.0, max_retries=1)


def _call_llm_anthropic(raw_text: str) -> str:
    return _call_llm_anthropic_with(SYSTEM_PROMPT, USER_PROMPT_TEMPLATE.format(raw_text=raw_text))


def _call_llm_anthropic_with(system_prompt: str, user_prompt: str, max_tokens: int = 512) -> str:
    """9/18 — 프롬프트를 인자로 받는 일반형. 원래 이 함수는 낙서 정리 프롬프트를
    하드코딩하고 있었는데, 같은 "가벼운 Haiku 호출 + JSON 응답" 형태의 경로가
    둘(숫자 되묻기 / 직무 전환 번역) 더 생겨서 공통부를 여기로 뺐다.
    타임아웃·재시도·텍스트 블록 추출 규칙을 세 경로가 똑같이 따르게 하는 게 목적이다.
    """
    response = _get_client().messages.create(
        # 매일 쓰는 가벼운 경로라 llm_model(Sonnet, 경력기술서용)이 아니라
        # llm_model_fast(Haiku)를 쓴다 — 9/15, 발표 데모 체감 속도 개선.
        model=settings.llm_model_fast,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
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
    return _call_llm_ollama_with(SYSTEM_PROMPT, USER_PROMPT_TEMPLATE.format(raw_text=raw_text))


def _call_llm_ollama_with(system_prompt: str, user_prompt: str) -> str:
    """`_call_llm_anthropic_with`의 Ollama 짝 (9/18)."""
    response = requests.post(
        f"{settings.ollama_base_url}/api/chat",
        json={
            "model": settings.ollama_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
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


def _call_llm_with(system_prompt: str, user_prompt: str, max_tokens: int = 512) -> str:
    """프롬프트를 지정하는 `_call_llm` (9/18). 분기 규칙은 동일하다."""
    if settings.llm_provider == "ollama":
        return _call_llm_ollama_with(system_prompt, user_prompt)
    return _call_llm_anthropic_with(system_prompt, user_prompt, max_tokens=max_tokens)


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
                case_summary=data.get("case_summary", ""),
            )
        except (json.JSONDecodeError, KeyError):
            if attempt == 1:
                raise
    raise RuntimeError("unreachable")


# ---------------------------------------------------------------------------
# 변환 전 추가 질문 — Figma "02 · 변환 결과" 3.1-q (9/18 신규)
# ---------------------------------------------------------------------------


@dataclass
class MetricQuestion:
    """"한 가지만 더" 화면에 띄울 질문 하나.

    `question`이 비어 있으면 **질문할 게 없다**는 뜻이고, 프론트는 화면을 건너뛰고
    바로 변환으로 넘어간다 — 매일 쓰는 경로에 화면이 하나 더 끼는 걸 이 판정이 막는다
    (CLAUDE.md 2.1).
    """

    question: str = ""
    placeholder: str = ""


def detect_missing_metric(raw_text: str) -> MetricQuestion:
    """메모에 성과 수치가 빠져 있으면 그걸 묻는 질문 하나를 만든다 (9/18 신규).

    CLAUDE.md 2.2가 정한 "숫자가 없으면 ... 유저에게 되묻는다(건너뛰기 가능)" 경로다.
    **되묻기만 하고 답을 지어내지는 않는다** — 유저가 건너뛰면 그냥 숫자 없이 간다.

    LLM 호출이 실패하거나 응답이 깨져도 예외를 던지지 않고 빈 `MetricQuestion`을
    반환한다. 이건 매일 쓰는 입력 경로에 얹히는 **부가** 단계라, 여기서 실패했다고
    메모 저장 자체가 막히면 안 된다(P0: 저장이 없으면 제품이 없다).
    """
    try:
        raw_response = _call_llm_with(
            METRIC_QUESTION_SYSTEM_PROMPT,
            METRIC_QUESTION_USER_TEMPLATE.format(raw_text=raw_text),
            max_tokens=256,
        )
        data = json.loads(_strip_code_fence(raw_response))
    except Exception:
        return MetricQuestion()
    question = data.get("question")
    if not isinstance(question, str) or not question.strip():
        return MetricQuestion()
    placeholder = data.get("placeholder")
    return MetricQuestion(
        question=question.strip(),
        placeholder=placeholder.strip() if isinstance(placeholder, str) else "",
    )


# ---------------------------------------------------------------------------
# 직무 전환 번역 — Figma "02 · 변환 결과" 3.1-b / 3.1-c (9/18 신규)
# ---------------------------------------------------------------------------


@dataclass
class JobTranslation:
    """같은 기록을 목표 직무 관점으로 다시 읽은 결과.

    `related`가 False면 3.1-c("직무 접점 없음") 화면이다 — 억지로 갖다 붙이는 대신
    "이건 그 직무로 읽기 어렵다"고 말하고, 대신 무엇을 기록하면 가까워지는지
    `suggestion`으로 알려준다.
    """

    related: bool
    headline: str
    translated_sentence: str
    suggestion: str = ""


def translate_for_target_job(
    raw_text: str, refined_sentence: str, current_job: str, target_job: str
) -> JobTranslation:
    """정제 문장을 목표 직무의 언어로 다시 쓴다 (9/18 신규).

    **없는 경험을 만들어내지 않는다** — 프롬프트가 "원문에 없는 행동/도구/성과/숫자를
    추가하지 말라"고 못박고 있고, 원문 숫자는 그대로 옮기게 한다 (CLAUDE.md 2.2).

    `parse_note()`와 달리 실패 시 예외를 던진다 — 이건 유저가 관점 라벨을 눌러서
    **명시적으로 요청한** 동작이라, 조용히 원문을 돌려주면 "번역이 됐는데 그대로인가"
    하고 헷갈린다. 호출부(라우터)가 502로 알린다.
    """
    raw_response = _call_llm_with(
        JOB_TRANSLATION_SYSTEM_PROMPT,
        JOB_TRANSLATION_USER_TEMPLATE.format(
            current_job=current_job,
            target_job=target_job,
            raw_text=raw_text,
            refined_sentence=refined_sentence,
        ),
        max_tokens=512,
    )
    data = json.loads(_strip_code_fence(raw_response))
    related = bool(data.get("related", False))
    translated = data.get("translated_sentence")
    return JobTranslation(
        related=related,
        headline=str(data.get("headline", "")).strip(),
        # 모델이 문장을 안 돌려주면 원래 문장을 그대로 쓴다 — 빈 카드를 보여주느니
        # 아무것도 안 바꾼 문장을 보여주는 쪽이 낫다(없는 문장을 만들지도 않는다).
        translated_sentence=(translated.strip() if isinstance(translated, str) and translated.strip() else refined_sentence),
        suggestion=str(data.get("suggestion", "")).strip() if not related else "",
    )
