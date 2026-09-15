"""미분류 카드 유사도 클러스터링 — Track B 담당 (9/14 신규, "4.1.1 AI 프로젝트 자동 제안").

CLAUDE.md 3장은 "프로젝트는 사람이 만든다"를 구조적 원칙으로 못 박는다 — 내용
유사도만으로는 "같은 회사, 이어지는 업무"와 "다른 회사, 우연히 비슷한 업무"를
원천적으로 구분할 수 없기 때문이다("A은행 결제 API 개선"과 "B카드 결제 API 개선"이
섞이면 안 됨). 이 모듈은 그 원칙을 깨지 않도록 설계했다 — **이미 어떤 프로젝트에
배정된 카드는 절대 건드리지 않고**, `project_id`가 아직 없는 카드
(`db.list_unassigned_cards()`)끼리만 비교해서 "비슷해 보이는 것들"을 후보로
제시한다. 애초에 프로젝트가 없는 카드들 사이에서 새 프로젝트를 제안하는 것뿐이라,
"서로 다른 프로젝트의 카드를 잘못 합친다"는 원래 우려 자체가 구조적으로 생기지
않는다.

프로젝트 이름도 이 모듈이 짓지 않는다 — 클러스터(카드 id 목록)만 반환하고, 이름은
`create_project(name, started_at)` 계약 그대로 사용자가 직접 입력한다(CLAUDE.md
2.2 — 숫자/사실을 지어내지 않는다는 정신을 프로젝트 이름에도 그대로 적용: AI가
멋대로 이름을 지으면 사용자가 검증 안 한 문구가 경력기술서에 들어갈 위험이 있다).

임베딩 함수는 `src/agent/vectorstore.py`의 provider 선택 로직을 그대로 재사용한다
(`tag_canonicalizer.py`와 동일한 재사용 패턴).
"""
from dataclasses import dataclass

from src.agent import vectorstore
from src.config import settings
from src.storage.db import Card


@dataclass
class CardCluster:
    card_ids: list[int]


def _cosine_distance(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 1.0  # 둘 중 하나가 영벡터면 방향을 정의할 수 없다 — 가장 먼 것으로 취급
    similarity = dot / (norm_a * norm_b)
    return 1.0 - similarity


def suggest_clusters(cards: list[Card], threshold: float | None = None) -> list[CardCluster]:
    """미분류 카드들을 문장 유사도로 그리디 클러스터링한다.

    2개 이상 모인 클러스터만 반환한다 — 혼자 남은 카드는 "묶을 만한 게 없다"는
    뜻이라 제안 후보에서 뺀다(사용자에게 의미 없는 제안을 보여주지 않기 위함).

    **구현 노트**: 카드 수만큼 임베딩 API를 따로 부르지 않고 배치 1회로 끝낸다 —
    `tag_canonicalizer.py`가 이미 겪은 문제(태그별 순차 호출 시 왕복 비용 급증)를
    처음부터 피하기 위함. 그리디 방식이라 클러스터링 품질이 최적은 아니지만,
    "AI가 제안 → 사람이 최종 확인" 흐름이라 완벽한 클러스터링이 필요하지 않다.
    """
    if len(cards) < 2:
        return []
    if threshold is None:
        threshold = settings.card_cluster_threshold

    embed = vectorstore._get_embedding_function()
    vectors = embed([c.refined_sentence for c in cards])

    n = len(cards)
    assigned = [False] * n
    clusters: list[CardCluster] = []

    for i in range(n):
        if assigned[i]:
            continue
        group = [i]
        assigned[i] = True
        for j in range(i + 1, n):
            if assigned[j]:
                continue
            if _cosine_distance(vectors[i], vectors[j]) <= threshold:
                group.append(j)
                assigned[j] = True
        if len(group) >= 2:
            clusters.append(CardCluster(card_ids=[cards[k].id for k in group]))

    return clusters
