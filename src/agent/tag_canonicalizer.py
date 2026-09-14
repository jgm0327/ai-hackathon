"""역량 태그 캐노니컬라이제이션 — Track B 담당 (신규).

`parse_note()`가 매번 자유 텍스트로 `skill_tags`를 생성하다 보니, 같은 개념인데
표기가 갈라지는 문제가 생긴다 (실측: "성능최적화" vs "시스템최적화"). CLAUDE.md 2.3
원칙("분류는 임베딩, 묶기는 LLM")에 따라 "이 태그가 기존 태그와 비슷한가"는 LLM이
아니라 임베딩이 판단한다 — LLM에게 기존 태그 목록을 프롬프트로 넘겨 고르게 하는
방식은 매 호출마다 비용이 커지고, 태그가 늘어날수록 프롬프트도 계속 길어진다.

Chroma에 `canonical_tags` 컬렉션을 별도로 두고(JD 매칭용 `jds` 컬렉션과는 독립),
새 태그가 들어올 때마다 가장 가까운 기존 캐노니컬 태그를 찾는다. 코사인 거리가
`settings.tag_canonicalize_threshold`보다 가까우면 그 기존 태그로 치환하고,
없으면(컬렉션이 비어 있거나 충분히 가까운 태그가 없으면) 새 캐노니컬 태그로 등록한다.

임베딩 함수/클라이언트 생성은 `src/agent/vectorstore.py`의 provider 선택 로직을
그대로 재사용한다(중복 구현 방지) — 모듈 자체를 참조해서 호출하므로, 테스트가
`vectorstore._get_embedding_function`을 monkeypatch하면 여기서도 그대로 적용된다.
"""
from chromadb import Collection

from src.agent import vectorstore
from src.config import settings

_COLLECTION_NAME = "canonical_tags"
_COLLECTION: Collection | None = None


def _get_collection() -> Collection:
    global _COLLECTION
    if _COLLECTION is None:
        client = vectorstore._get_client()
        _COLLECTION = client.get_or_create_collection(
            name=_COLLECTION_NAME,
            embedding_function=vectorstore._get_embedding_function(),
            # 코사인 거리로 고정한다 — threshold를 "0~2, 작을수록 유사"로 일관되게
            # 해석하려는 목적. 기본 space(l2 등)는 임베딩 함수마다 스케일이 달라 튜닝이 어렵다.
            metadata={"hnsw:space": "cosine"},
        )
    return _COLLECTION


def reset_collection() -> None:
    """테스트/재시작용 — 캐시된 컬렉션 핸들을 지워 다음 호출 시 다시 가져오게 한다."""
    global _COLLECTION
    _COLLECTION = None


def canonicalize_tags(raw_tags: list[str], threshold: float | None = None) -> list[str]:
    """LLM이 뽑은 raw_tags를 기존 캐노니컬 태그에 매핑한다.

    각 태그에 대해 기존 컬렉션에서 최근접 이웃 1개를 찾고, 코사인 거리가
    threshold 이내면 그 기존 태그명으로 치환한다. 그렇지 않으면(또는 컬렉션이
    비어 있으면) raw_tags의 표기 그대로 새 캐노니컬 태그로 등록한다(upsert라
    같은 태그를 다시 넣어도 안전 — 멱등).

    같은 카드 안에서 나온 태그끼리는 서로 비교하지 않는다 — "Redis"와 "결제시스템"처럼
    한 카드에 같이 나온 태그가 서로 다른 개념인 게 정상이므로, 카드 내부 구성으로
    유사도 판단을 흐리면 안 된다. 대신 이번 호출 안에서 완전히 같은 문자열이 두 번
    나오면(중복 태그) 컬렉션에 중복 upsert하지 않도록 한 번만 처리한다.
    """
    if not raw_tags:
        return []
    if threshold is None:
        threshold = settings.tag_canonicalize_threshold

    collection = _get_collection()
    canonical: list[str] = []
    resolved_in_this_call: dict[str, str] = {}

    for tag in raw_tags:
        if tag in resolved_in_this_call:
            canonical.append(resolved_in_this_call[tag])
            continue

        resolved = tag
        if collection.count() > 0:
            result = collection.query(query_texts=[tag], n_results=1)
            documents = result.get("documents") or [[]]
            distances = result.get("distances") or [[]]
            if documents[0] and distances[0] and distances[0][0] <= threshold:
                resolved = documents[0][0]

        if resolved == tag:
            # 신규 캐노니컬 태그로 등록. id=문서 내용으로 둬서 같은 태그 재등록이 upsert로
            # 자연스럽게 멱등 처리되게 한다.
            collection.upsert(ids=[tag], documents=[tag])

        resolved_in_this_call[tag] = resolved
        canonical.append(resolved)

    return canonical
