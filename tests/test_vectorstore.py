"""Track B 담당: build_jd_index() / match_jds()에 대한 테스트.

Track A의 test_parser.py가 _call_llm()을 모킹하듯, 여기서도 실제 임베딩 서버
(Ollama/Chroma 기본 ONNX 모델) 호출 없이 오프라인/결정론적으로 검증하기 위해
간단한 bag-of-words 가짜 임베딩 함수로 대체한다.

실제 임베딩 품질(bge-m3 기준)로 매칭이 잘 되는지는 로컬 수동 검증으로 확인했고
결과는 tasks/track-b-agent-pipeline.md에 기록했다.
"""
import json

import pytest
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from src.agent import vectorstore

VOCAB = [
    "장애대응", "결제시스템", "트러블슈팅", "동시성제어", "React", "상태관리",
    "백엔드", "개발자", "프론트엔드", "엔지니어",
]


class _FakeEmbeddingFunction(EmbeddingFunction[Documents]):
    """단어 등장 여부를 원-핫에 가깝게 인코딩하는 결정론적 가짜 임베딩."""

    def __init__(self) -> None:
        pass

    def __call__(self, input: Documents) -> Embeddings:
        return [[1.0 if word in text else 0.0 for word in VOCAB] for text in input]

    @staticmethod
    def name() -> str:
        return "fake-bag-of-words"


@pytest.fixture
def jd_dir(tmp_path):
    jds = [
        {
            "company": "가상핀테크",
            "title": "백엔드 개발자",
            "required_skills": ["장애대응", "결제시스템", "트러블슈팅"],
            "description": "결제 장애 대응 경험자",
        },
        {
            "company": "가상테크",
            "title": "프론트엔드 개발자",
            "required_skills": ["React", "상태관리"],
            "description": "React 상태관리 경험자",
        },
    ]
    for i, jd in enumerate(jds, start=1):
        (tmp_path / f"jd_{i:03d}.json").write_text(json.dumps(jd, ensure_ascii=False), encoding="utf-8")
    return tmp_path


@pytest.fixture(autouse=True)
def _reset_index_and_fake_embedding(monkeypatch, tmp_path):
    """각 테스트마다 전역 _INDEX를 리셋하고, 격리된 persist 디렉토리 + 가짜 임베딩을 쓴다."""
    monkeypatch.setattr(vectorstore, "_INDEX", None)
    monkeypatch.setattr(vectorstore, "_get_embedding_function", lambda: _FakeEmbeddingFunction())

    class _FakeSettings:
        chroma_persist_dir = str(tmp_path / ".chroma_test")
        mock_jd_dir = ""

    monkeypatch.setattr(vectorstore, "settings", _FakeSettings())
    yield


def test_match_jds_raises_if_index_not_built():
    with pytest.raises(RuntimeError):
        vectorstore.match_jds(["장애대응"], top_k=3)


def test_build_and_match_returns_expected_schema(jd_dir):
    vectorstore.build_jd_index(str(jd_dir))
    results = vectorstore.match_jds(["장애대응", "결제시스템", "트러블슈팅"], top_k=1)

    assert len(results) == 1
    top = results[0]
    assert top["company"] == "가상핀테크"
    assert top["title"] == "백엔드 개발자"
    assert top["required_skills"] == ["장애대응", "결제시스템", "트러블슈팅"]
    assert top["description"] == "결제 장애 대응 경험자"


def test_match_jds_includes_score_between_zero_and_one(jd_dir):
    vectorstore.build_jd_index(str(jd_dir))
    results = vectorstore.match_jds(["장애대응", "결제시스템", "트러블슈팅"], top_k=2)

    assert len(results) == 2
    for jd in results:
        assert "score" in jd
        assert 0.0 <= jd["score"] <= 1.0
    # 가장 잘 맞는 결과(정확히 일치하는 가짜 임베딩)가 더 높은 score를 가져야 한다.
    assert results[0]["score"] >= results[1]["score"]


def test_match_jds_picks_most_similar_jd(jd_dir):
    vectorstore.build_jd_index(str(jd_dir))

    payment_match = vectorstore.match_jds(["장애대응", "결제시스템"], top_k=1)
    assert payment_match[0]["company"] == "가상핀테크"

    frontend_match = vectorstore.match_jds(["React", "상태관리"], top_k=1)
    assert frontend_match[0]["company"] == "가상테크"


def test_build_jd_index_is_idempotent(jd_dir):
    """같은 디렉토리로 여러 번 빌드해도 문서 수가 늘어나지 않아야 한다 (upsert)."""
    vectorstore.build_jd_index(str(jd_dir))
    count_after_first = vectorstore._INDEX.count()

    vectorstore.build_jd_index(str(jd_dir))
    vectorstore.build_jd_index(str(jd_dir))
    count_after_repeat = vectorstore._INDEX.count()

    assert count_after_first == count_after_repeat == 2


class TestGetEmbeddingFunction:
    """_get_embedding_function()의 provider 선택 로직 검증.

    모듈 상단의 autouse fixture(_reset_index_and_fake_embedding)가 매 테스트마다
    vectorstore._get_embedding_function 자체를 monkeypatch로 가짜 함수로 덮어쓰므로,
    이 클래스의 테스트들은 import 시점에 미리 캡처해둔 진짜 함수 객체(_real_get_embedding_function)를
    직접 호출해서 provider 선택 로직 자체를 검증한다.
    """

    def test_defaults_to_chroma_builtin(self, monkeypatch):
        class _FakeSettings:
            embedding_provider = "chroma_default"

        monkeypatch.setattr(vectorstore, "settings", _FakeSettings())
        # 9/14 버그 수정: 예전엔 여기서 None을 반환했는데, chromadb 1.5.9는
        # `embedding_function=None`을 "임베딩 함수 없음"으로 해석해 ValueError를 던진다
        # (POST /api/cards가 500으로 죽는 형태로 실제 재현됨). None이 아니라 실제
        # DefaultEmbeddingFunction 인스턴스를 반환해야 한다.
        fn = _real_get_embedding_function()
        assert isinstance(fn, vectorstore.DefaultEmbeddingFunction)

    def test_unrecognized_provider_falls_back_to_chroma_builtin(self, monkeypatch):
        """EMBEDDING_PROVIDER가 오타/지원 안 하는 값(예: "anthropic")이어도 죽지 않고
        Chroma 기본 임베딩 함수로 폴백해야 한다 (9/14 실측 버그: .env에 EMBEDDING_PROVIDER=
        anthropic이 잘못 들어가 있어서 canonicalize_tags()가 500을 냈던 상황 그대로 재현)."""

        class _FakeSettings:
            embedding_provider = "anthropic"

        monkeypatch.setattr(vectorstore, "settings", _FakeSettings())
        fn = _real_get_embedding_function()
        assert isinstance(fn, vectorstore.DefaultEmbeddingFunction)

    def test_selects_ollama(self, monkeypatch):
        class _FakeSettings:
            embedding_provider = "ollama"
            ollama_base_url = "http://localhost:11434"
            ollama_embedding_model = "bge-m3"

        monkeypatch.setattr(vectorstore, "settings", _FakeSettings())
        fn = _real_get_embedding_function()
        assert isinstance(fn, vectorstore._OllamaEmbeddingFunction)

    def test_selects_local_multilingual_without_real_package(self, monkeypatch):
        """실제 sentence-transformers를 설치/다운로드하지 않도록 가짜 모듈로 대체한다."""
        import sys
        import types

        fake_module = types.ModuleType("sentence_transformers")

        class _FakeArray(list):
            """실제 SentenceTransformer.encode()가 반환하는 numpy 배열의 .tolist()만 흉내."""

            def tolist(self):
                return list(self)

        class _FakeSentenceTransformer:
            def __init__(self, model_name):
                self.model_name = model_name

            def encode(self, texts, normalize_embeddings=True):
                return _FakeArray([0.0, 0.0, 0.0] for _ in texts)

        fake_module.SentenceTransformer = _FakeSentenceTransformer
        monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

        class _FakeSettings:
            embedding_provider = "local_multilingual"
            local_multilingual_model = "paraphrase-multilingual-MiniLM-L12-v2"

        monkeypatch.setattr(vectorstore, "settings", _FakeSettings())
        fn = _real_get_embedding_function()
        assert isinstance(fn, vectorstore._LocalMultilingualEmbeddingFunction)
        # chromadb의 EmbeddingFunction 래퍼가 반환값을 numpy 배열로 바꿔줄 수 있으므로
        # 리스트로 명시 변환해서 비교한다 (== 로 바로 비교하면 ndarray 진위값 판별 에러 발생).
        result = [list(row) for row in fn(["테스트 문서"])]
        assert result == [[0.0, 0.0, 0.0]]

    def test_local_multilingual_raises_clear_error_if_package_missing(self, monkeypatch):
        import sys

        monkeypatch.setitem(sys.modules, "sentence_transformers", None)

        class _FakeSettings:
            embedding_provider = "local_multilingual"
            local_multilingual_model = "paraphrase-multilingual-MiniLM-L12-v2"

        monkeypatch.setattr(vectorstore, "settings", _FakeSettings())
        with pytest.raises(ImportError, match="pip install sentence-transformers"):
            _real_get_embedding_function()


# 모듈 로드 시점의 진짜 함수 객체를 보존해둔다 (fixture가 vectorstore._get_embedding_function
# 자체를 monkeypatch로 가짜로 바꾸므로, provider 선택 로직 테스트는 이 원본을 직접 호출한다).
_real_get_embedding_function = vectorstore._get_embedding_function
