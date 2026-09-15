"""Track B 담당: card_clustering.suggest_clusters()에 대한 테스트.

test_tag_canonicalizer.py와 동일한 이유로, 실제 임베딩 서버 호출 없이 결정론적으로
검증하기 위해 간단한 벡터 기반 가짜 임베딩 함수로 대체한다.
"""
from unittest.mock import patch

from src.agent.card_clustering import suggest_clusters
from src.storage.db import Card

# 문장 → 3차원 벡터. "결제 API" 계열 둘은 가깝게, "정산 배치"는 멀게 뒀다.
_VECTORS: dict[str, list[float]] = {
    "결제 API 응답 지연 해소를 위해 Redis 캐싱 도입": [1.0, 0.0, 0.0],
    "결제 API 캐싱 적용 이후 오류율 감소": [0.95, 0.05, 0.0],
    "정산 배치 처리 로직을 병렬화": [0.0, 1.0, 0.0],
    "신규 입사자 온보딩 문서 작성": [0.0, 0.0, 1.0],
}


def _card(id, refined_sentence, project_id=None) -> Card:
    return Card(
        id=id,
        project_id=project_id,
        raw_text=refined_sentence,
        refined_sentence=refined_sentence,
        skill_tags=[],
        confidence=0.9,
        created_at="2023-02-14",
    )


class _FakeEmbeddingFunction:
    def __call__(self, input):
        return [_VECTORS.get(text, [0.5, 0.5, 0.5]) for text in input]


def test_similar_cards_are_clustered_together():
    cards = [
        _card(1, "결제 API 응답 지연 해소를 위해 Redis 캐싱 도입"),
        _card(2, "정산 배치 처리 로직을 병렬화"),
        _card(3, "결제 API 캐싱 적용 이후 오류율 감소"),
    ]
    with patch("src.agent.vectorstore._get_embedding_function", return_value=_FakeEmbeddingFunction()):
        clusters = suggest_clusters(cards, threshold=0.1)

    assert len(clusters) == 1
    assert set(clusters[0].card_ids) == {1, 3}  # "정산 배치"(카드 2)는 별개로 남아 제외됨


def test_no_cluster_when_all_cards_are_dissimilar():
    cards = [
        _card(1, "결제 API 응답 지연 해소를 위해 Redis 캐싱 도입"),
        _card(2, "정산 배치 처리 로직을 병렬화"),
        _card(3, "신규 입사자 온보딩 문서 작성"),
    ]
    with patch("src.agent.vectorstore._get_embedding_function", return_value=_FakeEmbeddingFunction()):
        clusters = suggest_clusters(cards, threshold=0.1)

    assert clusters == []  # 전부 서로 무관 -> 제안할 클러스터 없음


def test_fewer_than_two_cards_returns_empty_without_calling_embedding():
    with patch("src.agent.vectorstore._get_embedding_function") as mock_embed:
        assert suggest_clusters([]) == []
        assert suggest_clusters([_card(1, "혼자뿐인 카드")]) == []
        mock_embed.assert_not_called()


def test_uses_configured_threshold_by_default(monkeypatch):
    from src.agent import card_clustering

    class _FakeSettings:
        card_cluster_threshold = 0.1

    monkeypatch.setattr(card_clustering, "settings", _FakeSettings())
    cards = [
        _card(1, "결제 API 응답 지연 해소를 위해 Redis 캐싱 도입"),
        _card(2, "결제 API 캐싱 적용 이후 오류율 감소"),
    ]
    with patch("src.agent.vectorstore._get_embedding_function", return_value=_FakeEmbeddingFunction()):
        clusters = suggest_clusters(cards)  # threshold 인자 생략

    assert len(clusters) == 1
    assert set(clusters[0].card_ids) == {1, 2}
