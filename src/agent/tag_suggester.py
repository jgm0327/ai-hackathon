"""미분류 기록에 붙일 역량 후보 추천 — Figma "03 · 커리어 스택" 4.1-i (9/18 신규).

화면이 "AI가 먼저 나눠뒀어요"라고 말하고 **추천 칩 2개**를 보여준 뒤, 사용자가
그대로 확정하거나 다른 역량을 고른다. 딱 CLAUDE.md 2.3이 말하는 임베딩의 자리다 —
"새 카드를 기존 작업 그룹에 배정(보조적, 틀려도 손해 작음)". LLM을 부르지 않는다.

**없는 역량을 만들지 않는다.** 후보는 **이 유저가 이미 가진 역량 이름** 중에서만
고른다(2.2의 정신 — 사용자가 검증하지 않은 문구가 경력기술서 쪽으로 새어 들어가면
안 된다). 그래서 역량이 하나도 없는 계정에서는 추천이 빈 목록이고, 화면은 "역량
직접 추가"만 남는다.

임베딩 함수는 `vectorstore.py`의 provider 선택 로직을 그대로 재사용한다
(`tag_canonicalizer.py`/`card_clustering.py`와 동일한 재사용 패턴).
"""
from dataclasses import dataclass

from src.agent import vectorstore
from src.agent.card_clustering import _cosine_distance
from src.storage.db import Card


@dataclass
class TagSuggestion:
    """미분류 기록 한 건과 그 기록에 추천하는 역량 이름들."""

    card_id: int
    suggested_tags: list[str]


def suggest_tags_for_cards(
    cards: list[Card], known_tags: list[str], top_k: int = 2
) -> list[TagSuggestion]:
    """미분류 카드마다 가장 가까운 기존 역량 `top_k`개를 고른다.

    임베딩 호출은 **한 번**이다 — 카드 문장과 역량 이름을 한 배치로 같이 넘긴다.
    카드마다 따로 부르면 왕복 비용이 카드 수만큼 늘어난다(`tag_canonicalizer.py`가
    이미 겪은 문제).

    후보가 없거나(역량이 하나도 없는 계정) 카드가 없으면 빈 목록. 임베딩 호출이
    실패하면 예외를 그대로 올린다 — 이건 사용자가 "분류 수정" 화면에 직접 들어와서
    요청한 동작이라, 조용히 빈 추천을 돌려주면 "AI가 아무것도 못 찾았다"와 구분이
    안 된다. 호출부(라우터)가 502로 알린다.
    """
    if not cards or not known_tags:
        return []

    embed = vectorstore._get_embedding_function()
    vectors = embed([c.refined_sentence for c in cards] + list(known_tags))
    card_vectors = vectors[: len(cards)]
    tag_vectors = vectors[len(cards) :]

    suggestions: list[TagSuggestion] = []
    for card, card_vector in zip(cards, card_vectors):
        ranked = sorted(
            zip(known_tags, tag_vectors),
            key=lambda pair: _cosine_distance(card_vector, pair[1]),
        )
        suggestions.append(
            TagSuggestion(card_id=card.id, suggested_tags=[tag for tag, _ in ranked[:top_k]])
        )
    return suggestions
