"""경력기술서(STAR) 생성 — Track A 담당 (CLAUDE.md P0 2순위, 9/13 피벗 신규).

한 프로젝트에 속한 카드들을 묶어 STAR(Situation/Task/Action/Result) 형식 경력기술서
항목으로 변환한다. 단건 변환(`parser.parse_note`)과 근본적으로 다르다 — 여러 카드를
가로질러 읽고, **시간이 떨어진 조치와 결과를 인과로 연결**해야 한다. 이것이 이 제품의
존재 이유다 (docs/02-architecture.md 5장 참고).

환각 방지(CLAUDE.md 2.2)가 가장 중요한 제약이다: 기록에 없는 숫자를 만들어내면
경력기술서를 쓴 유저가 면접에서 검증당한다. 이 원칙을 프롬프트에 명시하는 것만으로는
불충분하다고 보고, LLM이 답한 근거가 입력에 실재하는 카드인지 코드로 한 번 더
검증한다(사후 필터링) — LLM 출력을 무조건 신뢰하지 않는다.

구현 노트: tasks/track-a-prompt-engine.md는 LangChain의 `with_structured_output()`
사용을 제안했지만, 이 코드베이스는 처음부터(parser.py) LangChain 없이 Anthropic/Ollama
SDK를 직접 호출 + JSON 파싱 재시도 패턴을 써왔다. 새 의존성을 추가하는 대신 기존
패턴과의 일관성을 택했다.

**구현 노트 (9/14, ID 기반 매칭으로 전환)**: 원래는 LLM이 `source_dates`(날짜 문자열,
예: "09.14")로 근거를 답했는데, 같은 날짜에 카드가 여러 장 있으면(실제로 자주 있는
일) 어느 카드가 어느 항목 소속인지 날짜만으로 구분이 안 되는 문제가 있었다
(`/stack`의 "인과관계로 묶어보기"에서 무관한 카드가 같은 그룹으로 섞이는 버그로
발견됨). 이제 프롬프트에 각 기록 앞에 `[N]`(1-based 줄 번호)을 붙이고, LLM은
`source_indices`(정수 배열, 그 번호)로 답한다 — 번호는 프롬프트 안에서 항상 고유하므로
날짜가 같아도 모호해지지 않는다. `source_dates`(화면 표시용)는 이제 LLM이 직접 쓰지
않고, 검증된 `source_indices`로부터 백엔드가 계산한다 — 환각 방지가 오히려 더
튼튼해졌다(날짜를 잘못 쓸 방법 자체가 없어짐).
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
"[번호] [MM.DD] 정제된 문장 #태그1 #태그2" 형식 — 맨 앞 [번호]는 그 줄의 고유 번호이며
같은 날짜라도 절대 겹치지 않습니다). 선택적으로 채용 공고 본문이 함께 주어질 수 있습니다.

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
      "source_indices": [이 항목을 구성한 기록들의 번호(정수). 입력의 [번호]를 그대로 쓸 것]
    }}
  ]
}}

규칙 (반드시 지킬 것):
1. 같은 작업 흐름에 속하는 기록끼리 묶으세요. 특히 조치를 취한 기록과 그 결과가
   나중에 관측된 기록은 시간이 떨어져 있어도(어휘가 겹치지 않아도) 하나로 묶으세요.
2. 결과에는 기록에 실제로 적힌 숫자만 쓰세요. 숫자가 없으면 result를 빈 문자열로
   남기세요. 추정하거나 지어내지 마세요. 이것이 가장 중요한 규칙입니다.
3. source_indices에는 입력에 실제로 주어진 번호만 쓰세요. 없는 번호를 만들어내면
   안 됩니다.
4. 서로 무관한 기록은 별개의 항목으로 나누세요. **같은 날짜에 기록이 여러 개 있어도,
   서로 다른 작업이면 반드시 별개의 항목으로 나누세요 — 날짜가 같다는 이유만으로
   묶으면 안 됩니다.** 억지로 묶지 마세요.
5. 채용 공고(JD)가 함께 주어지면, 그 공고와 관련 있는 항목을 앞쪽에 배치하도록
   순서를 조정하세요. 관련 없는 항목이라도 삭제하지 말고 뒤로 미루기만 하세요.

예시 1 (시간차 병합 + 실제 수치 보존):
입력:
[1] [02.14] 결제 API 응답 지연을 해소하기 위해 Redis 캐싱 레이어를 도입함 #Redis #성능최적화 #결제시스템
[2] [02.17] 쿠폰 중복 적용 버그를 식별하고 긴급 수정 사항을 배포함 #버그수정 #핫픽스 #결제시스템
[3] [03.02] Redis 캐싱 적용 이후 결제 오류율을 0.8%에서 0.3%로 개선함 #성능최적화 #결제시스템 #모니터링
출력: {{"items": [{{"title": "결제 API 성능 및 안정성 개선", "period": "02.14 - 03.02", "situation": "결제 API 응답 지연과 쿠폰 중복 적용 버그로 결제 시스템 안정성이 저하된 상황이었습니다.", "task": "응답 지연을 해소하고 결제 오류를 줄여 시스템 신뢰도를 확보해야 했습니다.", "action": "Redis 캐싱 레이어를 도입하고 쿠폰 중복 버그에 대한 긴급 수정을 배포했습니다.", "result": "결제 오류율을 0.8%에서 0.3%로 개선했습니다.", "source_indices": [1, 2, 3]}}]}}

예시 2 (숫자 없으면 result 비움):
입력:
[1] [04.01] 신규 입사자 온보딩 문서를 작성함 #문서작성 #온보딩
출력: {{"items": [{{"title": "신규 입사자 온보딩 문서화", "period": "04.01", "situation": "신규 입사자를 위한 체계적인 안내 자료가 부족한 상황이었습니다.", "task": "온보딩 과정을 표준화할 문서가 필요했습니다.", "action": "신규 입사자 온보딩 문서를 작성했습니다.", "result": "", "source_indices": [1]}}]}}

예시 3 (같은 날짜여도 무관하면 나눔 — 규칙 4 강조):
입력:
[1] [09.14] Redis를 활용하여 실시간 이체 시스템의 처리 속도를 향상시켰다 #캐싱기술 #성능최적화
[2] [09.14] 아웃박스 알림 상태를 저장하여 데이터 정합성을 유지함 #데이터관리 #정합성유지
[3] [09.14] Redis를 이체 기능에 통합해 시스템 오류 감소율을 90% 향상시키고 성능을 10배 개선함 #성능최적화 #오류관리
출력: {{"items": [{{"title": "실시간 이체 시스템 성능 개선", "period": "09.14", "situation": "이체 시스템의 처리 속도와 오류율이 문제였습니다.", "task": "이체 처리 성능을 개선해야 했습니다.", "action": "Redis를 캐싱에 활용해 이체 기능에 통합했습니다.", "result": "시스템 오류 감소율을 90% 향상시키고 성능을 10배 개선했습니다.", "source_indices": [1, 3]}}, {{"title": "알림 데이터 정합성 개선", "period": "09.14", "situation": "알림 상태가 유실되면 데이터 정합성이 깨질 수 있는 상황이었습니다.", "task": "알림 상태를 안정적으로 보존해야 했습니다.", "action": "아웃박스 패턴으로 알림 상태를 저장했습니다.", "result": "", "source_indices": [2]}}]}}
- 1번과 3번은 같은 Redis 성능 개선 작업의 조치/결과라 하나로 묶였지만, 2번(아웃박스
  정합성)은 날짜가 같아도 완전히 다른 작업이라 별개 항목으로 남았습니다.
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
    # 9/14 신규 — 카드를 정확히 식별하는 필드. source_dates는 화면 표시(근거 토글)용으로
    # 남겨두지만, 카드 매칭(예: /stack "인과관계로 묶어보기")은 반드시 이걸로 해야 한다 —
    # 날짜만으로는 같은 날짜 카드 여러 장을 구분할 수 없다.
    source_card_ids: list[int] = field(default_factory=list)


def build_resume(cards: list[Card], jd_text: str | None = None) -> list[StarItem]:
    """한 프로젝트의 카드를 묶어 STAR 항목들로 변환한다.

    jd_text가 주어지면 해당 채용공고에 맞는 항목 위주로 재구성하고 순서를 조정한다.
    JSON 파싱 실패 시 최대 1회 재시도한다 (parser.parse_note()와 동일한 패턴).
    """
    if not cards:
        return []

    user_prompt = _format_prompt(cards, jd_text)

    for attempt in range(2):
        raw_response = _call_llm(user_prompt)
        try:
            data = json.loads(raw_response)
            items = [_dict_to_star_item(item, cards) for item in data["items"]]
            return items
        except (json.JSONDecodeError, KeyError, TypeError):
            if attempt == 1:
                raise
    raise RuntimeError("unreachable")


def _format_prompt(cards: list[Card], jd_text: str | None) -> str:
    lines = []
    for i, card in enumerate(cards, start=1):
        tags = " ".join(f"#{tag}" for tag in card.skill_tags)
        lines.append(f"[{i}] [{_short_date(card.created_at)}] {card.refined_sentence} {tags}".rstrip())
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


def _dict_to_star_item(data: dict, cards: list[Card]) -> StarItem:
    # 환각 방지(CLAUDE.md 2.2): source_indices는 입력에 실재하는 번호(1..len(cards))만
    # 남긴다. LLM이 없는 번호를 지어내도, 최종 결과에는 절대 포함되지 않도록 코드로 한
    # 번 더 거른다. 순서를 보존하면서 중복은 제거한다(프롬프트가 이미 날짜순이라 index
    # 오름차순 = 시간순).
    seen: set[int] = set()
    valid_indices: list[int] = []
    for i in data.get("source_indices", []):
        if isinstance(i, int) and 1 <= i <= len(cards) and i not in seen:
            seen.add(i)
            valid_indices.append(i)

    matched_cards = [cards[i - 1] for i in valid_indices]
    return StarItem(
        title=data["title"],
        period=data.get("period", ""),
        situation=data.get("situation", ""),
        task=data.get("task", ""),
        action=data.get("action", ""),
        result=data.get("result", ""),
        # source_dates는 더 이상 LLM이 직접 쓰지 않는다 — 검증된 카드로부터 백엔드가
        # 계산하므로, LLM이 날짜 문자열 자체를 잘못 쓸 여지가 아예 없어졌다.
        source_dates=[_short_date(c.created_at) for c in matched_cards],
        source_card_ids=[c.id for c in matched_cards],
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
    return _extract_text(response)


def _extract_text(response: anthropic.types.Message) -> str:
    """응답의 첫 텍스트 블록을 꺼낸다.

    `content[0]`이 항상 텍스트라고 가정하면 안 된다 — 모델이 ThinkingBlock 등 텍스트가
    아닌 블록을 먼저 반환하면 `content[0].text`에서 AttributeError가 난다(9/14 실제로
    발생, src/parsing/parser.py의 동일 패턴 참고). 여긴 아직 그 순서로 안 걸렸을 뿐
    같은 위험이 있어 동일하게 고쳐둔다.
    """
    for block in response.content:
        if block.type == "text":
            return block.text
    raise ValueError(f"Anthropic 응답에 텍스트 블록이 없습니다: {response.content!r}")


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
