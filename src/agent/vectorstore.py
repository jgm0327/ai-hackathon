"""가상 원티드 JD 세트 임베딩 및 매칭 — Track B 담당.

배포 환경에서 Chroma 퍼시스턴스 유실 리스크가 있으므로 build_jd_index()는
언제 다시 호출해도 동일한 결과가 나오도록 멱등하게 구현한다.
(docs/03-risk-fallback.md 리스크 2 참고)
"""
import glob
import json
from pathlib import Path

from src.config import settings

_INDEX = None  # TODO(Track B): Chroma client/collection 객체로 교체


def _load_mock_jds(jd_dir: str) -> list[dict]:
    jds = []
    for path in glob.glob(str(Path(jd_dir) / "*.json")):
        with open(path, encoding="utf-8") as f:
            jds.append(json.load(f))
    return jds


def build_jd_index(jd_dir: str = None) -> None:
    """data/mock_jds/*.json을 임베딩해서 Chroma 인덱스를 (재)구축한다.

    TODO(Track B):
    1. jd_dir(기본값 settings.mock_jd_dir)에서 JD 목록 로드
    2. 임베딩 모델로 각 JD의 required_skills를 벡터화
    3. Chroma collection에 upsert (재실행해도 안전하도록 upsert 사용, add 금지)
    """
    jd_dir = jd_dir or settings.mock_jd_dir
    jds = _load_mock_jds(jd_dir)
    raise NotImplementedError(f"Track B: {len(jds)}개 JD 임베딩 로직 구현 필요")


def match_jds(skill_tags: list[str], top_k: int = 5) -> list[dict]:
    """역량 태그로 유사 JD를 top_k개 반환한다.

    반환 형식은 data/mock_jds JSON 스키마와 동일한 dict 리스트.
    """
    if _INDEX is None:
        raise RuntimeError("build_jd_index()를 먼저 호출해야 합니다")
    raise NotImplementedError("Track B: 유사도 검색 로직 구현 필요")
