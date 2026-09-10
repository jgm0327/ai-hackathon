"""가상 원티드 JD 세트 임베딩 및 매칭 — Track B 담당.

배포 환경에서 Chroma 퍼시스턴스 유실 리스크가 있으므로 build_jd_index()는
언제 다시 호출해도 동일한 결과가 나오도록 멱등하게 구현한다.
(docs/03-risk-fallback.md 리스크 2 참고)
"""
import glob
import json
from pathlib import Path

import chromadb
import requests
from chromadb import Collection
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from src.config import settings

_INDEX: Collection | None = None  # build_jd_index() 호출 후 Chroma collection 객체로 채워짐
_COLLECTION_NAME = "jds"


class _OllamaEmbeddingFunction(EmbeddingFunction[Documents]):
    """로컬 Ollama 임베딩 모델(bge-m3 등) 호출용. EMBEDDING_PROVIDER=ollama 일 때만 사용.

    한국어 스킬 태그 임베딩 품질이 chroma 기본 모델(영어 위주)보다 좋지만,
    배포 환경엔 로컬 Ollama 서버가 없으므로 로컬 개발 전용이다.
    """

    def __init__(self) -> None:
        pass  # EmbeddingFunction 기본 __init__이 DeprecationWarning을 내므로 오버라이드

    def __call__(self, input: Documents) -> Embeddings:
        response = requests.post(
            f"{settings.ollama_base_url}/api/embed",
            json={"model": settings.ollama_embedding_model, "input": list(input)},
            timeout=60,
        )
        response.raise_for_status()
        return response.json()["embeddings"]

    @staticmethod
    def name() -> str:
        return f"ollama-{settings.ollama_embedding_model}"


def _get_embedding_function():
    if settings.embedding_provider == "ollama":
        return _OllamaEmbeddingFunction()
    return None  # None이면 Chroma 기본 임베딩 함수(all-MiniLM-L6-v2) 사용


def _get_client() -> chromadb.ClientAPI:
    return chromadb.PersistentClient(path=settings.chroma_persist_dir)


def _load_mock_jds(jd_dir: str) -> list[tuple[str, dict]]:
    """(문서 id, JD dict) 튜플 리스트로 로드. id는 파일명 기반이라 재실행해도 안정적이다."""
    jds = []
    for path in sorted(glob.glob(str(Path(jd_dir) / "*.json"))):
        with open(path, encoding="utf-8") as f:
            jd = json.load(f)
        doc_id = Path(path).stem  # 예: "jd_001"
        jds.append((doc_id, jd))
    return jds


def _jd_to_document(jd: dict) -> str:
    """임베딩 대상 텍스트. required_skills 위주로 구성해 스킬 태그 매칭에 최적화한다."""
    title = jd.get("title", "")
    skills = " ".join(jd.get("required_skills", []))
    return f"{title} {skills}".strip()


def build_jd_index(jd_dir: str = None) -> None:
    """data/mock_jds/*.json을 임베딩해서 Chroma 인덱스를 (재)구축한다.

    upsert를 사용하므로 몇 번을 다시 호출해도 동일한 결과(멱등)이다.
    """
    global _INDEX
    jd_dir = jd_dir or settings.mock_jd_dir
    jds = _load_mock_jds(jd_dir)

    client = _get_client()
    collection = client.get_or_create_collection(
        name=_COLLECTION_NAME,
        embedding_function=_get_embedding_function(),
    )
    if jds:
        collection.upsert(
            ids=[doc_id for doc_id, _ in jds],
            documents=[_jd_to_document(jd) for _, jd in jds],
            metadatas=[
                {
                    "company": jd.get("company", ""),
                    "title": jd.get("title", ""),
                    "description": jd.get("description", ""),
                    # Chroma 메타데이터는 스칼라만 지원하므로 리스트는 문자열로 직렬화
                    "required_skills": json.dumps(jd.get("required_skills", []), ensure_ascii=False),
                }
                for _, jd in jds
            ],
        )
    _INDEX = collection


def _metadata_to_jd(metadata: dict) -> dict:
    jd = dict(metadata)
    jd["required_skills"] = json.loads(jd.get("required_skills", "[]"))
    return jd


def match_jds(skill_tags: list[str], top_k: int = 5) -> list[dict]:
    """역량 태그로 유사 JD를 top_k개 반환한다.

    반환 형식은 data/mock_jds JSON 스키마와 동일한 dict 리스트.
    """
    if _INDEX is None:
        raise RuntimeError("build_jd_index()를 먼저 호출해야 합니다")

    query_text = " ".join(skill_tags)
    result = _INDEX.query(query_texts=[query_text], n_results=top_k)
    metadatas = result.get("metadatas", [[]])[0]
    return [_metadata_to_jd(m) for m in metadatas]
