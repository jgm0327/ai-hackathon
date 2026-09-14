"""인풋 → 파싱 → 저장 오케스트레이션 — Track B 담당.

Track A(parsing.parser, parsing.resume)와 storage/vectorstore를 연결하는 지점.

**구현 노트 (9/13 피벗)**: JD 매칭을 매일 쓰는 경로(`run_pipeline`)에서 분리했다.
JD 매칭은 이직 준비 시점에만 필요한데, 매 입력마다 벡터 쿼리를 돌리는 건 낭비고
CLAUDE.md 2.1 원칙("일상 입력 비용은 거의 0")에도 어긋난다. 대신:
    - `run_pipeline()`: 매일 쓰는 가벼운 경로. 파싱 후 현재 프로젝트에 카드로 저장만 한다.
    - `build_career_doc()`: 이직 준비 시점의 무거운 경로. 카드를 모아 STAR 경력기술서로
      변환하고(`build_resume`), 필요하면 JD 매칭까지 여기서 수행한다.

반환 dict 스키마는 Track C(프론트엔드)가 그대로 렌더링하므로 임의로 바꾸지 않는다.
**주의**: `run_pipeline()`의 반환값에서 `matched_jds` 키가 사라졌다 — 예전 Streamlit
프론트엔드(`src/frontend/app.py`)는 `.get("matched_jds", [])`로 읽고 있어 에러 없이
빈 목록으로 동작하지만, 더 이상 JD가 채워지지 않는다. 이는 의도된 아키텍처 변경이다
(JD 매칭은 `build_career_doc()` 시점으로 이동).

**구현 노트 (9/14, 태그 캐노니컬라이제이션 추가)**: `parse_note()`가 매번 자유
텍스트로 `skill_tags`를 생성하다 보니 같은 개념이 "성능최적화"/"시스템최적화"처럼
표기가 갈라지는 문제가 있었다. `save_card()` 직전에 `canonicalize_tags()`(임베딩
유사도 기반, CLAUDE.md 2.3)를 한 번 더 거쳐 기존 태그로 통일한다. LLM 호출이 아니라
임베딩 조회라 매일 쓰는 경로에 부담을 주지 않는다(2.1). 기존에 저장된 카드는 소급
적용되지 않는다 — 필요하면 별도 마이그레이션 스크립트로 처리할 것.
"""
from datetime import date

from src.agent.tag_canonicalizer import canonicalize_tags
from src.parsing.parser import parse_note
from src.parsing.resume import StarItem, build_resume
from src.storage.db import get_current_project, list_cards, save_card


def run_pipeline(raw_text: str) -> dict:
    """단일 낙서 문장을 받아 파싱하고 현재 프로젝트에 카드로 저장한다.

    JD 매칭은 하지 않는다 (이직 준비 시점의 `build_career_doc()`으로 이동됨).

    반환 스키마:
        {
            "parsed": ParsedEntry,
            "card_id": int,
        }
    """
    parsed = parse_note(raw_text)
    parsed.skill_tags = canonicalize_tags(parsed.skill_tags)
    current_project = get_current_project()
    project_id = current_project.id if current_project else None
    card_id = save_card(project_id, parsed, date.today().isoformat())
    return {"parsed": parsed, "card_id": card_id}


def run_pipeline_batch(raw_texts: list[str]) -> list[dict]:
    """노션 동기화 등으로 여러 건을 한 번에 처리할 때 사용."""
    return [run_pipeline(text) for text in raw_texts]


def build_career_doc(project_id: int, jd_text: str | None = None) -> list[StarItem]:
    """한 프로젝트의 누적 카드를 모아 STAR 형식 경력기술서로 변환한다 (이직 준비 시점).

    jd_text가 주어지면 build_resume()이 해당 채용공고와 관련 있는 항목을 우선 배치한다.
    """
    cards = list_cards(project_id)
    return build_resume(cards, jd_text=jd_text)
