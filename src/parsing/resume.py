"""경력기술서(STAR) 생성 — Track A 담당 (CLAUDE.md P0 2순위, 9/13 피벗 신규).

한 프로젝트에 속한 카드들을 묶어 STAR(Situation/Task/Action/Result) 형식 경력기술서
항목으로 변환한다. 단건 변환(`parser.parse_note`)과 근본적으로 다르다 — 여러 카드를
가로질러 읽고, **시간이 떨어진 조치와 결과를 인과로 연결**해야 한다. 이것이 이 제품의
존재 이유다 (docs/02-architecture.md 5장 참고).

환각 방지(CLAUDE.md 2.2)가 가장 중요한 제약이다: 기록에 없는 숫자를 만들어내면
경력기술서를 쓴 유저가 면접에서 검증당한다. 이 원칙을 프롬프트에 명시하는 것만으로는
불충분하다고 보고, `source_dates`는 입력에 실재하는 날짜인지 코드로 한 번 더
검증한다(사후 필터링) — LLM 출력을 무조건 신뢰하지 않는다.

구현 노트: tasks/track-a-prompt-engine.md는 LangChain의 `with_structured_output()`
사용을 제안했지만, 이 코드베이스는 처음부터(parser.py) LangChain 없이 Anthropic/Ollama
SDK를 직접 호출 + JSON 파싱 재시도 패턴을 써왔다. 새 의존성을 추가하는 대신 기존
패턴과의 일관성을 택했다.
"""
import json
from dataclasses import dataclass, field
from functools import lru_cache

import anthropic
import requests

from src.config import settings
from src.storage.db import Card

_SYSTEM_PROMPT = """\
당신은 개발자의 업무 기록(카드)들을 모아 STAR(Situation-Task-Action-Result) 형식의
경력기술서 항목으로 변환하는 전문 커리어 코치입니다.

입력: 한 프로젝트에 속한 업무 기록들을 날짜순으로 나열한 목록 (각 줄은
"[MM.DD] 정제된 문장 #태그1 #태그2" 형식). 선택적으로 채용 공고 본문이 함께 주어질 수
있습니다.

출력: 반드시 아래 JSON 스키마로만 응답하세요. 다른 설명은 붙이지 마세요.

{{
  "items": [
    {{
      "title": "항목 제목 (예: '결제 API 성능 개선')",
      "period": "관련 기록들의 날짜 범위 (예: '02.14 - 03.02', 기록이 하나면 그 날짜 하나만)",
      "situation": "어떤 상황이었는지",
      "task": "무엇을 해결해야 했는지",
      "action": "무엇을 했는지",
      "result": "수치로 확인된 결과 (없으면 빈 문자열 \"\")",
      "source_dates": ["이 항목을 구성한 기록들의 날짜(MM.DD), 입력에 있던 날짜만"]
    }}
  ]
}}

규칙 (반드시 지킬 것):
1. 같은 작업 흐름에 속하는 기록끼리 묶으세요. 특히 조치를 취한 기록과 그 결과가
   나중에 관측된 기록은 시간이 떨어져 있어도(어휘가 겹치지 않아도) 하나로 묶으세요.
2. 결과에는 기록에 실제로 적힌 숫자만 쓰세요. 숫자가 없으면 result를 빈 문자열로
   남기세요. 추정하거나 지어내지 마세요. 이것이 가장 중요한 규칙입니다.
3. source_dates에는 입력에 실제로 존재하는 날짜만 쓰세요. 없는 날짜를 만들어내면
   안 됩니다.
4. 서로 무관한 기록은 별개의 항목으로 나누세요. 억지로 묶지 마세요.
5. 채용 공고(JD)가 함께 주어지면, 그 공고와 관련 있는 항목을 앞쪽에 배치하도록
   순서를 조정하세요. 관련 없는 항목이라도 삭제하지 말고 뒤로 미루기만 하세요.

예시 1 (시간차 병합 + 실제 수치 보존):
입력:
[02.14] 결제 API 응답 지연을 해소하기 위해 Redis 캐싱 레이어를 도입함 #Redis #성능최적화 #결제시스템
[02.17] 쿠폰 중복 적용 버그를 식별하고 긴급 수정 사항을 배포함 #버그수정 #핫픽스 #결제시스템
[03.02] Redis 캐싱 적용 이후 결제 오류율을 0.8%에서 0.3%로 개선함 #성능최적화 #결제시스템 #모니터링
출력: {{"items": [{{"title": "결제 API 성능 및 안정성 개선", "period": "02.14 - 03.02", "situation": "결제 API 응답 지연과 쿠폰 중복 적용 버그로 결제 시스템 안정성이 저하된 상황이었습니다.", "task": "응답 지연을 해소하고 결제 오류를 줄여 시스템 신뢰도를 확보해야 했습니다.", "action": "Redis 캐싱 레이어를 도입하고 쿠폰 중복 버그에 대한 긴급 수정을 배포했습니다.", "result": "결제 오류율을 0.8%에서 0.3%로 개선했습니다.", "source_dates": ["02.14", "02.17", "03.02"]}}]}}

예시 2 (숫자 없으면 result 비움):
입력:
[04.01] 신규 입사자 온보딩 문서를 작성함 #문서작성 #온보딩
출력: {{"items": [{{"title": "신규 입사자 온보딩 문서화", "period": "04.01", "situation": "신규 입사자를 위한 체계적인 안내 자료가 부족한 상황이었습니다.", "task": "온보딩 과정을 표준화할 문서가 필요했습니다.", "action": "신규 입사자 온보딩 문서를 작성했습니다.", "result": "", "source_dates": ["04.01"]}}]}}
"""


@dataclass
class StarItem:
    title: str
    period: str
    situation: str
    task: str
    action: str
    result: str
    source_dates: list[str] = field(default_factory=list)


def build_resume(cards: list[Card], jd_text: str | None = None) -> list[StarItem]:
    """한 프로젝트의 카드를 묶어 STAR 항목들로 변환한다.

    jd_text가 주어지면 해당 채용공고에 맞는 항목 위주로 재구성하고 순서를 조정한다.
    JSON 파싱 실패 시 최대 1회 재시도한다 (parser.parse_note()와 동일한 패턴).
    """
    if not cards:
        return []

    valid_dates = {_short_date(c.created_at) for c in cards}
    user_prompt = _format_prompt(cards, jd_text)

    for attempt in range(2):
        raw_response = _call_llm(user_prompt)
        try:
            data = json.loads(raw_response)
            items = [_dict_to_star_item(item, valid_dates) for item in data["items"]]
            return items
        except (json.JSONDecodeError, KeyError, TypeError):
            if attempt == 1:
                raise
    raise RuntimeError("unreachable")


def _format_prompt(cards: list[Card], jd_text: str | None) -> str:
    lines = []
    for card in cards:
        tags = " ".join(f"#{tag}" for tag in card.skill_tags)
        lines.append(f"[{_short_date(card.created_at)}] {card.refined_sentence} {tags}".rstrip())
    prompt = "아래는 한 프로젝트의 업무 기록들이다 (날짜순):\n\n" + "\n".join(lines)
    if jd_text:
        prompt += f"\n\n다음 채용 공고에 맞춰 관련 있는 항목을 우선하고 순서를 조정해라:\n{jd_text}"
    return prompt


def _short_date(iso_date: str) -> str:
    """'2023-02-14' -> '02.14'."""
    parts = iso_date.split("-")
    if len(parts) == 3:
        return f"{parts[1]}.{parts[2]}"
    return iso_date


def _dict_to_star_item(data: dict, valid_dates: set[str]) -> StarItem:
    # 환각 방지(CLAUDE.md 2.2): source_dates는 입력에 실재하는 날짜만 남긴다.
    # LLM이 없는 날짜를 지어내도, 최종 결과에는 절대 포함되지 않도록 코드로 한 번 더 거른다.
    source_dates = [d for d in data.get("source_dates", []) if d in valid_dates]
    return StarItem(
        title=data["title"],
        period=data.get("period", ""),
        situation=data.get("situation", ""),
        task=data.get("task", ""),
        action=data.get("action", ""),
        result=data.get("result", ""),
        source_dates=source_dates,
    )


@lru_cache(maxsize=1)
def _get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings.llm_api_key)


def _call_llm_anthropic(user_prompt: str) -> str:
    response = _get_client().messages.create(
        model=settings.llm_model,
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text


def _call_llm_ollama(user_prompt: str) -> str:
    response = requests.post(
        f"{settings.ollama_base_url}/api/chat",
        json={
            "model": settings.ollama_model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0},
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["message"]["content"]


def _call_llm(user_prompt: str) -> str:
    if settings.llm_provider == "ollama":
        return _call_llm_ollama(user_prompt)
    return _call_llm_anthropic(user_prompt)
