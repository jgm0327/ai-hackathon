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
from dataclasses import replace

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
from src.storage.db import (
    Card,
    get_card,
    get_current_project,
    list_cards,
    list_projects,
    list_unassigned_cards,
    save_card,
    update_card,
)
from src.timeutil import now_local

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
    #
    # 9/17: 서버 로컬 시간(date.today()/datetime.now()) 대신 앱 기준 시간대를 쓴다.
    # UTC 서버(OCI 기본)에 그대로 올리면 "오늘"이 한국시간 09:00에 바뀌어서, 새벽에
    # 쓴 메모가 전날로 분류되고 홈 화면 "오늘 남긴 것"과 주간 스트릭이 조용히 어긋난다.
    now = now_local()
    card_id = save_card(
        user_id, project_id, parsed, now.date().isoformat(), now.strftime("%H:%M")
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


# Figma 4.2.1 "범위 선택"에서 프로젝트에 안 들어간 기록들을 담는 칸의 이름.
# 프로젝트가 아니라 "남은 것들"을 뜻하는 라벨이라 AI가 이름을 짓지 않는다.
UNASSIGNED_SECTION_NAME = "미분류 기록"


def collect_scoped_cards(
    user_id: int,
    project_id: int | None = None,
    *,
    project_ids: list[int] | None = None,
    include_unassigned: bool = False,
) -> list[Card]:
    """선택된 범위(프로젝트 여러 개 + 미분류)의 카드를 한 목록으로 모은다 (9/18 신규).

    `build_career_doc`과 달리 프로젝트 경계를 유지하지 않는다 — JD 요구사항 매칭이나
    기존 문장 보강처럼 "근거 카드가 어디 있든 상관없는" 경로가 쓴다.
    """
    cards: list[Card] = []
    for pid in _normalize_scope(user_id, project_id, project_ids):
        cards.extend(list_cards(user_id, pid))
    if include_unassigned:
        cards.extend(list_unassigned_cards(user_id))
    # build_resume()의 프롬프트가 "날짜순"을 전제하므로(resume.py `_format_prompt`)
    # 프로젝트별로 이어붙인 뒤 반드시 다시 정렬한다.
    cards.sort(key=lambda c: c.created_at)
    return cards


def _normalize_scope(
    user_id: int, project_id: int | None, project_ids: list[int] | None
) -> list[int]:
    """요청이 준 프로젝트 범위를 "이 유저가 실제로 가진 프로젝트 id 목록"으로 정리한다.

    - `project_ids`가 오면 그걸 쓰고, 없으면 예전 계약인 `project_id` 하나를 쓴다
    - 순서는 요청이 준 순서를 그대로 보존한다 (프론트가 최신 프로젝트부터 보낸다)
    - 중복과 남의 프로젝트 id는 조용히 버린다 — 다른 유저 데이터가 새지 않게 하는
      건 `list_cards()`가 이미 하지만, 여기서 걸러야 프로젝트 이름을 찍을 때 안전하다
    """
    requested = list(project_ids) if project_ids is not None else (
        [project_id] if project_id is not None else []
    )
    owned = {p.id for p in list_projects(user_id)}
    seen: set[int] = set()
    result: list[int] = []
    for pid in requested:
        if pid in owned and pid not in seen:
            seen.add(pid)
            result.append(pid)
    return result


def build_career_doc(
    user_id: int,
    project_id: int | None = None,
    jd_text: str | None = None,
    *,
    project_ids: list[int] | None = None,
    include_unassigned: bool = False,
) -> list[StarItem]:
    """선택한 범위의 누적 카드를 모아 STAR 형식 경력기술서로 변환한다 (이직 준비 시점).

    jd_text가 주어지면 build_resume()이 해당 채용공고와 관련 있는 항목을 우선 배치한다.

    **구현 노트 (9/18, 마스터 경력기술서)**: Figma 4.2.1 "범위 선택"이 프로젝트 여러
    개 + 미분류 기록을 한 문서로 묶으라고 해서 스코프를 넓혔다. 중요한 건 **프로젝트
    경계를 넘어 묶지 않는다**는 점이다 — CLAUDE.md 3장이 말하는 대로 A은행의 "결제 API
    개선"과 B카드의 "결제 API 개선"은 내용이 같아도 별개 경력이라, 카드를 한 덩어리로
    합쳐 build_resume()에 넣으면 경력이 반으로 줄어든다. 그래서 프로젝트마다 따로
    build_resume()을 부르고(= LLM 호출도 프로젝트 수만큼), 결과에 어느 프로젝트에서
    나왔는지를 찍어서 이어 붙인다. 프론트는 그 표시를 보고 프로젝트 헤드(Figma 41:254)를
    그린다.

    `project_id` 하나만 넘기던 기존 호출은 그대로 동작한다.
    """
    items: list[StarItem] = []
    projects = {p.id: p for p in list_projects(user_id)}

    for pid in _normalize_scope(user_id, project_id, project_ids):
        # 카드가 없어도 build_resume()을 그냥 부른다 — 빈 목록이면 LLM 호출 없이 바로
        # []를 돌려주므로(resume.py) 여기서 따로 가지치기할 이유가 없다.
        project_name = projects[pid].name
        for item in build_resume(list_cards(user_id, pid), jd_text=jd_text):
            items.append(replace(item, project_id=pid, project_name=project_name))

    if include_unassigned:
        for item in build_resume(list_unassigned_cards(user_id), jd_text=jd_text):
            items.append(replace(item, project_id=None, project_name=UNASSIGNED_SECTION_NAME))

    return items


def enhance_existing_resume(
    user_id: int,
    project_id: int | None,
    existing_items: list[str],
    *,
    project_ids: list[int] | None = None,
    include_unassigned: bool = False,
) -> list[EnhancedItem]:
    """유저가 이미 써둔 경력기술서 문장을 프로젝트 카드 근거로 보강한다 (9/15 신규).

    "기존 경력기술서 붙여넣기 → Before/After 대조" 기능(Figma 90:612/90:640). 다른
    유저 프로젝트를 넘겨도 `list_cards()`가 빈 목록을 반환하므로 build_career_doc()과
    동일하게 소유권이 자연히 지켜진다.

    9/18부터 build_career_doc()과 같은 범위(프로젝트 여러 개 + 미분류)를 받는다. 여기선
    프로젝트 경계를 유지할 이유가 없다 — 유저가 준 문장 하나하나의 근거를 찾는 일이라,
    근거 카드가 어느 프로젝트에 있든 상관없다(build_career_doc()과 다른 점).
    """
    cards = collect_scoped_cards(
        user_id, project_id, project_ids=project_ids, include_unassigned=include_unassigned
    )
    return enhance_resume_items(existing_items, cards)


def get_jd_requirements(
    user_id: int,
    project_id: int | None,
    jd_text: str,
    *,
    project_ids: list[int] | None = None,
    include_unassigned: bool = False,
) -> JdRequirementsResult:
    """채용 공고 요구사항과 프로젝트 카드를 매칭한다 (9/16 신규 — Figma "4.2-j2").

    build_career_doc()/enhance_existing_resume()과 동일하게 list_cards()가 소유권을
    자동으로 걸러주므로 별도 검증이 필요 없다.
    """
    cards = collect_scoped_cards(
        user_id, project_id, project_ids=project_ids, include_unassigned=include_unassigned
    )
    return match_jd_requirements(jd_text, cards)
