"""Track B 담당: canonicalize_tags()에 대한 테스트.

test_vectorstore.py와 동일한 이유로, 실제 임베딩 서버(Ollama/Chroma 기본 ONNX 모델)
호출 없이 오프라인/결정론적으로 검증하기 위해 간단한 벡터 기반 가짜 임베딩 함수로
대체한다. 벡터는 "의미 축"별 좌표를 손으로 정해뒀다 — 코사인 거리로 "성능최적화"와
"시스템최적화"는 가깝게, "결제시스템"과는 멀게 만들어서 의도한 병합/비병합을 검증한다.
"""
import pytest
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from src.agent import tag_canonicalizer, vectorstore
from src.agent.tag_canonicalizer import canonicalize_tags

# 태그 문자열 → 3차원 벡터. "최적화" 계열 둘은 서로 가깝게, "결제시스템"은 멀게 뒀다.
_VECTORS: dict[str, list[float]] = {
    "성능최적화": [1.0, 0.0, 0.0],
    "시스템최적화": [0.95, 0.05, 0.0],  # 성능최적화와 코사인 거리 가까움
    "결제시스템": [0.0, 1.0, 0.0],
    "캐싱기술": [0.0, 0.0, 1.0],
}


class _FakeEmbeddingFunction(EmbeddingFunction[Documents]):
    """미리 정해둔 좌표를 반환하는 결정론적 가짜 임베딩. 목록에 없는 태그는 원점 근처."""

    def __init__(self) -> None:
        pass

    def __call__(self, input: Documents) -> Embeddings:
        return [_VECTORS.get(text, [0.5, 0.5, 0.5]) for text in input]

    @staticmethod
    def name() -> str:
        return "fake-tag-vectors"


@pytest.fixture(autouse=True)
def _isolated_collection(monkeypatch, tmp_path):
    """각 테스트마다 캐시된 컬렉션을 리셋하고, 격리된 persist 디렉토리 + 가짜 임베딩을 쓴다."""
    tag_canonicalizer.reset_collection()
    monkeypatch.setattr(vectorstore, "_get_embedding_function", lambda: _FakeEmbeddingFunction())

    class _FakeSettings:
        chroma_persist_dir = str(tmp_path / ".chroma_test")

    monkeypatch.setattr(vectorstore, "settings", _FakeSettings())
    yield
    tag_canonicalizer.reset_collection()


def test_first_call_registers_tags_as_is():
    """컬렉션이 비어 있으면 비교 대상이 없으므로 원본 그대로 반환/등록된다."""
    result = canonicalize_tags(["성능최적화", "결제시스템"], threshold=0.15)
    assert result == ["성능최적화", "결제시스템"]


def test_similar_tag_is_mapped_to_existing_canonical_tag():
    """이미 등록된 태그와 코사인 거리가 가까우면(threshold 이내) 기존 태그로 통일된다."""
    canonicalize_tags(["성능최적화"], threshold=0.15)  # 먼저 캐노니컬로 등록

    result = canonicalize_tags(["시스템최적화"], threshold=0.15)

    assert result == ["성능최적화"]  # 새 문자열이 아니라 기존 캐노니컬 태그로 치환됨


def test_dissimilar_tag_is_registered_as_new_canonical_tag():
    """충분히 다른 개념이면 threshold를 벗어나 새 캐노니컬 태그로 남는다."""
    canonicalize_tags(["성능최적화"], threshold=0.15)

    result = canonicalize_tags(["캐싱기술"], threshold=0.15)

    assert result == ["캐싱기술"]  # 병합되지 않고 별개로 유지


def test_duplicate_tag_within_same_card_is_not_double_registered():
    """한 카드 안에 같은 태그가 중복으로 나와도 컬렉션엔 한 번만 등록된다."""
    result = canonicalize_tags(["성능최적화", "성능최적화"], threshold=0.15)

    assert result == ["성능최적화", "성능최적화"]
    collection = tag_canonicalizer._get_collection()
    assert collection.count() == 1


def test_empty_tags_returns_empty_without_touching_collection():
    """스킬 태그가 없는(모호한) 입력은 컬렉션을 건드리지 않고 즉시 빈 리스트를 반환한다."""
    result = canonicalize_tags([])

    assert result == []
    # _get_collection()이 아예 호출되지 않아야 하므로, 컬렉션이 아직 생성되지 않았어야 한다.
    assert tag_canonicalizer._COLLECTION is None


def test_canonicalize_is_idempotent_across_repeated_calls():
    """같은 태그를 여러 번 넣어도 컬렉션에 쌓이는 캐노니컬 태그 수는 늘어나지 않는다."""
    canonicalize_tags(["성능최적화", "결제시스템"], threshold=0.15)
    canonicalize_tags(["성능최적화", "결제시스템"], threshold=0.15)
    canonicalize_tags(["시스템최적화"], threshold=0.15)  # 성능최적화로 흡수되어야 함

    collection = tag_canonicalizer._get_collection()
    assert collection.count() == 2  # "성능최적화", "결제시스템"만 캐노니컬로 존재


def test_uses_configured_threshold_by_default(monkeypatch):
    """threshold를 명시하지 않으면 settings.tag_canonicalize_threshold를 쓴다."""
    class _FakeSettings:
        tag_canonicalize_threshold = 0.15

    monkeypatch.setattr(tag_canonicalizer, "settings", _FakeSettings())
    canonicalize_tags(["성능최적화"])  # threshold 인자 생략

    result = canonicalize_tags(["시스템최적화"])  # threshold 인자 생략

    assert result == ["성능최적화"]
