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

**구현 노트 (9/14, 카카오 로그인 Phase B)**: 모든 함수가 `user_id`를 맨 앞 인자로
받는다 — 호출부(라우터)가 `Depends(get_current_user)`로 받은 로그인 유저의 id를
그대로 넘긴다. 이 모듈 자체는 "누가 로그인했는지" 판단하지 않는다(그건 라우터의 몫).

**구현 노트 (9/15, 변환 실패 폴백 추가)**: `parse_note()`가 LLM 호출 실패(타임아웃,
API 오류, JSON 파싱 재시도까지 실패 등)로 예외를 던지면 예전엔 카드가 통째로
저장되지 않았다 — 새로고침하면 방금 쓴 메모가 사라졌다(CLAUDE.md P0 "저장소 없으면
제품이 없다" 원칙 위반). 이제 파싱 실패 시 원문을 그대로 폴백 저장하고
`refinement_failed=True`를 반환한다 — **저장 자체는 파싱 성공 여부와 무관하게
항상 일어난다.** `retry_refinement()`로 나중에 다시 정리를 시도할 수 있다.
"""
import logging
from datetime import date, datetime

from src.agent.tag_canonicalizer import canonicalize_tags
from src.parsing.parser import ParsedEntry, parse_note
from src.parsing.resume import (
    EnhancedItem,
    JdRequirementsResult,
    StarItem,
    build_resume,
    enhance_resume_items,
    match_jd_requirements,
)
from src.storage.db import Card, get_card, get_current_project, list_cards, save_card, update_card

logger = logging.getLogger(__name__)


def run_pipeline(user_id: int, raw_text: str) -> dict:
    """단일 낙서 문장을 받아 파싱하고 그 유저의 현재 프로젝트에 카드로 저장한다.

    JD 매칭은 하지 않는다 (이직 준비 시점의 `build_career_doc()`으로 이동됨).

    반환 스키마:
        {
            "parsed": ParsedEntry,
            "card_id": int,
            "refinement_failed": bool,
        }
    """
    try:
        parsed = parse_note(raw_text)
        parsed.skill_tags = canonicalize_tags(parsed.skill_tags)
        refinement_failed = False
    except Exception:
        # 어떤 이유로든(LLM 타임아웃/오류, JSON 파싱 재시도까지 실패 등) 정리에
        # 실패해도 유저가 쓴 메모 자체는 반드시 남겨야 한다 — 원문을 그대로 폴백.
        logger.warning("parse_note 실패 — 원문 그대로 폴백 저장", exc_info=True)
        parsed = ParsedEntry(raw_text=raw_text, refined_sentence=raw_text, skill_tags=[], confidence=0.0)
        refinement_failed = True
    current_project = get_current_project(user_id)
    project_id = current_project.id if current_project else None
    # created_time(9/16 신규, "HH:MM")은 홈 화면 "오늘 남긴 것" 목록 전용 — created_at
    # (날짜만)은 /stack 주간 스트릭이 문자열 동등 비교로 의존하고 있어 그대로 둔다.
    card_id = save_card(
        user_id, project_id, parsed, date.today().isoformat(), datetime.now().strftime("%H:%M")
    )
    return {"parsed": parsed, "card_id": card_id, "refinement_failed": refinement_failed}


def retry_refinement(user_id: int, card_id: int) -> Card | None:
    """폴백 저장된(원문 그대로인) 카드를 다시 AI로 정리한다 (9/15 신규).

    이 유저 소유가 아니거나 없으면 None. 파싱이 다시 실패하면 예외를 그대로
    전파한다(카드는 이미 저장돼 있으니 데이터 유실 위험이 없다 — 호출부가 그냥
    "다시 실패했다"고만 알리면 된다).
    """
    card = get_card(user_id, card_id)
    if card is None:
        return None
    parsed = parse_note(card.raw_text)
    parsed.skill_tags = canonicalize_tags(parsed.skill_tags)
    return update_card(
        user_id,
        card_id,
        skill_tags=parsed.skill_tags,
        refined_sentence=parsed.refined_sentence,
        confidence=parsed.confidence,
    )


def run_pipeline_batch(user_id: int, raw_texts: list[str]) -> list[dict]:
    """노션 동기화 등으로 여러 건을 한 번에 처리할 때 사용."""
    return [run_pipeline(user_id, text) for text in raw_texts]


def build_career_doc(user_id: int, project_id: int, jd_text: str | None = None) -> list[StarItem]:
    """한 프로젝트의 누적 카드를 모아 STAR 형식 경력기술서로 변환한다 (이직 준비 시점).

    jd_text가 주어지면 build_resume()이 해당 채용공고와 관련 있는 항목을 우선 배치한다.
    """
    cards = list_cards(user_id, project_id)
    return build_resume(cards, jd_text=jd_text)


def enhance_existing_resume(
    user_id: int, project_id: int, existing_items: list[str]
) -> list[EnhancedItem]:
    """유저가 이미 써둔 경력기술서 문장을 프로젝트 카드 근거로 보강한다 (9/15 신규).

    "기존 경력기술서 붙여넣기 → Before/After 대조" 기능(Figma 90:612/90:640). 다른
    유저 프로젝트를 넘겨도 `list_cards()`가 빈 목록을 반환하므로 build_career_doc()과
    동일하게 소유권이 자연히 지켜진다.
    """
    cards = list_cards(user_id, project_id)
    return enhance_resume_items(existing_items, cards)


def get_jd_requirements(user_id: int, project_id: int, jd_text: str) -> JdRequirementsResult:
    """채용 공고 요구사항과 프로젝트 카드를 매칭한다 (9/16 신규 — Figma "4.2-j2").

    build_career_doc()/enhance_existing_resume()과 동일하게 list_cards()가 소유권을
    자동으로 걸러주므로 별도 검증이 필요 없다.
    """
    cards = list_cards(user_id, project_id)
    return match_jd_requirements(jd_text, cards)
