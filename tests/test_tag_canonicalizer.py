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
    """미리 정해둔 좌표를 반환하는 결정론적 가짜 임베딩. 목록에 없는 태그는 원점 근처.

    `call_count`/`call_sizes`로 실제 몇 번, 몇 개씩 묶여서 호출됐는지 기록한다 —
    태그별로 따로 호출되던 걸 배치로 묶은 최적화(9/14)가 회귀하지 않는지 검증하는 데 쓴다.
    """

    def __init__(self) -> None:
        self.call_count = 0
        self.call_sizes: list[int] = []

    def __call__(self, input: Documents) -> Embeddings:
        self.call_count += 1
        self.call_sizes.append(len(input))
        return [_VECTORS.get(text, [0.5, 0.5, 0.5]) for text in input]

    @staticmethod
    def name() -> str:
        return "fake-tag-vectors"


@pytest.fixture(autouse=True)
def _isolated_collection(monkeypatch, tmp_path):
    """각 테스트마다 캐시된 컬렉션을 리셋하고, 격리된 persist 디렉토리 + 가짜 임베딩을 쓴다.

    같은 가짜 임베딩 인스턴스를 매번 반환하도록 고정해서, 호출 횟수를 세야 하는
    테스트(배치 최적화 검증)가 `_isolated_collection` 픽스처 값으로 그 인스턴스를
    받아 쓸 수 있게 한다.
    """
    tag_canonicalizer.reset_collection()
    fake_embedding = _FakeEmbeddingFunction()
    monkeypatch.setattr(vectorstore, "_get_embedding_function", lambda: fake_embedding)

    class _FakeSettings:
        chroma_persist_dir = str(tmp_path / ".chroma_test")

    monkeypatch.setattr(vectorstore, "settings", _FakeSettings())
    yield fake_embedding
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


def test_batches_embedding_calls_regardless_of_tag_count(_isolated_collection):
    """태그별로 따로 임베딩 API를 부르지 않는지 검증한다 (9/14 배치화, 9/15 재축소).

    실측: 태그별로 query()+upsert()를 따로 부르던 예전 구현은 로컬 Ollama로 태그 3개
    처리에 ~14초가 걸렸다(태그당 왕복 2회). 배치로 묶어 query 1회 + upsert 1회(최대
    2번)로 줄였다가, 9/15에 임베딩을 함수 안에서 한 번만 계산해 query/upsert 양쪽에
    재사용하도록 다시 바꿔 태그 수·신규 여부와 무관하게 임베딩 함수 호출이 **최대
    1번**으로 끝나야 한다(query 1회 + upsert 1회 = 2번이 되면 이번 최적화가 깨진 것).
    """
    fake_embedding = _isolated_collection

    # 첫 호출 — 컬렉션이 비어 있어도(query 스킵) 임베딩은 여전히 1번만 계산한다.
    canonicalize_tags(["성능최적화", "결제시스템", "캐싱기술", "시스템최적화"], threshold=0.01)
    assert fake_embedding.call_count == 1
    assert fake_embedding.call_sizes == [4]

    fake_embedding.call_count = 0
    fake_embedding.call_sizes = []

    # 두 번째 호출 — 컬렉션이 비어있지 않아 query까지 타지만, 임베딩은 미리 계산해둔
    # 값을 query_embeddings=/embeddings=로 재사용하므로 여전히 1번(태그 3개 배치)뿐이다.
    canonicalize_tags(["완전히새로운태그1", "완전히새로운태그2", "완전히새로운태그3"], threshold=0.01)
    assert fake_embedding.call_count == 1
    assert fake_embedding.call_sizes == [3]


def test_uses_configured_threshold_by_default(monkeypatch):
    """threshold를 명시하지 않으면 settings.tag_canonicalize_threshold를 쓴다."""
    class _FakeSettings:
        tag_canonicalize_threshold = 0.15

    monkeypatch.setattr(tag_canonicalizer, "settings", _FakeSettings())
    canonicalize_tags(["성능최적화"])  # threshold 인자 생략

    result = canonicalize_tags(["시스템최적화"])  # threshold 인자 생략

    assert result == ["성능최적화"]
