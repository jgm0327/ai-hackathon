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
