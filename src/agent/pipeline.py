"""인풋 → 파싱 → 매칭 오케스트레이션 — Track B 담당.

Track A(parsing.parser)와 이 파일의 vectorstore/notion_client를 연결하는 지점.
반환 dict 스키마는 Track C(프론트엔드)가 그대로 렌더링하므로 임의로 바꾸지 않는다.
"""
from src.agent.vectorstore import match_jds
from src.parsing.parser import parse_note


def run_pipeline(raw_text: str, top_k: int = 5) -> dict:
    """단일 낙서 문장을 받아 파싱 결과와 매칭 JD를 함께 반환한다.

    반환 스키마:
        {
            "parsed": ParsedEntry,
            "matched_jds": list[dict],  # vectorstore.match_jds()의 반환값
        }
    """
    parsed = parse_note(raw_text)
    matched_jds = match_jds(parsed.skill_tags, top_k=top_k) if parsed.skill_tags else []
    return {"parsed": parsed, "matched_jds": matched_jds}


def run_pipeline_batch(raw_texts: list[str], top_k: int = 5) -> list[dict]:
    """노션 동기화 등으로 여러 건을 한 번에 처리할 때 사용."""
    return [run_pipeline(text, top_k=top_k) for text in raw_texts]
