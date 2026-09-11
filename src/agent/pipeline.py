"""인풋 → 파싱 → 매칭 오케스트레이션 — Track B 담당.

Track A(parsing.parser)와 이 파일의 vectorstore/notion_client를 연결하는 지점.
반환 dict 스키마는 Track C(프론트엔드)가 그대로 렌더링하므로 임의로 바꾸지 않는다.
"""
import warnings

from src.agent.vectorstore import build_jd_index, match_jds
from src.parsing.parser import parse_note

# 모듈 임포트 시 1회 인덱스를 구축해둔다 (upsert 기반이라 재실행해도 안전).
# 이렇게 해두면 match_jds()가 "인덱스 미구축" 에러를 신경 쓸 필요 없이 항상 쓸 수 있다.
# 임베딩 서버(Ollama 등) 연결 실패로 앱 임포트 자체가 죽지 않도록 방어한다 —
# 이 경우 match_jds()는 원래 계약대로 RuntimeError를 던진다.
try:
    build_jd_index()
except Exception as e:  # noqa: BLE001 — 임포트를 막지 않는 게 우선
    warnings.warn(f"JD 인덱스 초기 구축 실패, match_jds() 호출 시 에러가 날 수 있음: {e}")


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
