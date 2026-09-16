"""Pydantic 응답/요청 스키마 — Track B(FastAPI) 담당.

docs/05-api-contract.md 1~3, 8절의 필드명/모양을 그대로 따른다. 필드 이름은
내부 dataclass(Card, Project, StarItem)와 1:1로 맞춰뒀으므로 `model_validate()`로
(from_attributes=True) dataclass 인스턴스를 바로 변환할 수 있다.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _FromAttributes(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CardCreateRequest(BaseModel):
    raw_text: str


class CardTagsUpdateRequest(BaseModel):
    """PATCH /api/cards/{id} — 카테고리(스킬 태그)/문장 직접 수정 (9/14 태그, 9/15 문장 추가).

    가끔(연 몇 회, `/stack`에서) 손보는 용도라 두 필드 다 optional — 최소 하나는
    와야 하고(라우터가 체크, 둘 다 없으면 400), 넘어온 것만 바뀐다.
    """

    skill_tags: list[str] | None = None
    refined_sentence: str | None = None


class CardResponse(_FromAttributes):
    id: int
    project_id: int | None
    raw_text: str
    refined_sentence: str
    skill_tags: list[str]
    confidence: float
    # 주의(구현 노트): 계약 문서는 타임존 포함 ISO datetime
    # ("2026-02-14T18:45:00+09:00")을 예시로 들지만, 실제 저장소(save_card/run_pipeline)는
    # `date.today().isoformat()`로 날짜만("2026-02-14") 기록한다. 저장소 계약을 조율 없이
    # 바꾸지 않기 위해 실제 저장된 값을 그대로 반환한다 — 불일치는 최종 보고에 기록.
    created_at: str
    # 9/16 신규 — 홈 화면(Figma 100:692) "오늘 남긴 것" 목록의 "09:40" 표시용.
    # created_at(날짜만)과 달리 /stack 어떤 로직도 이 필드에 의존하지 않는다 —
    # 순수 표시용 추가 필드. 마이그레이션 이전 카드는 null.
    created_time: str | None = None
    # 9/15 신규 — POST /api/cards가 LLM 파싱에 실패해 원문을 그대로 폴백 저장했을 때만
    # true. DB 컬럼이 아니라 생성 시점에 라우터가 채워 넣는 값이라, GET/PATCH 응답은
    # 항상 기본값 False다 (docs/05-api-contract.md 참고).
    refinement_failed: bool = False
    # 9/16 신규 — 결과 출력 모달(Figma 41:139) "오늘 기록은 ~~ 케이스입니다" 문구.
    # refinement_failed와 동일한 패턴: DB 컬럼이 아니라 POST /api/cards 생성 시점에만
    # 라우터가 채워 넣는다. GET/PATCH 응답에서는 항상 빈 문자열(카드 저장 후에는
    # 다시 보여줄 이유가 없는, 생성 순간 전용 문구라서).
    case_summary: str = ""


class CardListResponse(BaseModel):
    cards: list[CardResponse]


# 홈 화면(Figma 100:692) "무엇이 쌓였나요" 버블 차트 (9/16 신규). 카드 대표 태그
# (skill_tags[0]) 기준 집계 — src/storage/db.py의 get_skill_category_counts() 참고.
class SkillCategoryCount(BaseModel):
    tag: str
    count: int


class SkillSummaryResponse(BaseModel):
    total_cards: int
    categories: list[SkillCategoryCount]


# 4.1.1 "AI 프로젝트 자동 제안" (9/14 신규). project_id가 없는 카드끼리만 비교해서
# 후보를 만든다 — 이미 프로젝트가 배정된 카드는 절대 안 건드린다(CLAUDE.md 3장,
# src/agent/card_clustering.py 참고). 프로젝트 이름은 AI가 짓지 않고 사용자가
# 직접 입력한다.
class CardClusterSuggestion(BaseModel):
    card_ids: list[int]
    cards: list[CardResponse]


class UnclassifiedSuggestionsResponse(BaseModel):
    clusters: list[CardClusterSuggestion]


class BundleIntoProjectRequest(BaseModel):
    card_ids: list[int]
    name: str
    started_at: str


class ProjectCreateRequest(BaseModel):
    name: str
    started_at: str


class ProjectPatchRequest(BaseModel):
    """부분 업데이트. 계약 문서(2장)가 보여주는 3개 필드만 노출한다."""

    name: str | None = None
    ended_at: str | None = None
    is_current: bool | None = None


class ProjectResponse(_FromAttributes):
    id: int
    name: str
    started_at: str
    ended_at: str | None
    is_current: bool


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]


class ResumeRequest(BaseModel):
    project_id: int
    jd_text: str | None = None


class StarItemResponse(_FromAttributes):
    title: str
    period: str
    situation: str
    task: str
    action: str
    result: str
    source_dates: list[str]
    # 9/14 신규 — docs/05-api-contract.md 3장 참고. source_dates는 화면 표시(근거 토글)용,
    # source_card_ids는 카드 매칭(예: /stack "인과관계로 묶어보기")용으로 역할이 다르다.
    source_card_ids: list[int]


class ResumeResponse(BaseModel):
    items: list[StarItemResponse]


# 경력기술서 초안 저장 (9/14 신규, docs/05-api-contract.md 3장). AI가 만든 STAR
# 구조 자체가 아니라, 유저가 그걸 가져다 직접 고친 자유 텍스트(마크다운)를 저장한다
# — CLAUDE.md 3장이 막는 "AI 그룹핑을 정식 데이터로 저장"과는 다른 문제라서
# 별도로 허용됨(src/storage/db.py의 ResumeDraft 참고).
class ResumeDraftResponse(BaseModel):
    project_id: int
    # 저장된 초안이 없으면(또는 project_id가 이 유저 소유가 아니면) 둘 다 None.
    content: str | None
    updated_at: str | None


class ResumeDraftSaveRequest(BaseModel):
    project_id: int
    content: str


# "기존 경력기술서 붙여넣기 → Before/After 대조" (9/15 신규, docs/05-api-contract.md
# 3장). 완전히 선택 사항 — 위 STAR 생성/초안 저장 경로와 독립적으로 동작한다.
class ResumeEnhanceRequest(BaseModel):
    project_id: int
    existing_items: list[str] = Field(max_length=10)


class EnhancedItemResponse(_FromAttributes):
    original: str
    enhanced: str
    gap_comment: str
    source_dates: list[str]
    source_card_ids: list[int]


class ResumeEnhanceResponse(BaseModel):
    items: list[EnhancedItemResponse]


# 공고 요구사항 매칭 (9/16 신규, Figma "4.2-j2"). build_resume()보다 앞선 단계 —
# JD를 붙여넣은 직후, 실제로 초안을 만들기 전에 "요구사항 N개 중 M개에 기록이
# 있어요"를 보여준다.
class JdRequirementsRequest(BaseModel):
    project_id: int
    jd_text: str


class JdRequirementResponse(_FromAttributes):
    requirement: str
    source_dates: list[str]
    source_card_ids: list[int]


class JdRequirementsResponse(BaseModel):
    job_title: str
    company: str
    years_label: str
    requirements: list[JdRequirementResponse]


# AI 역질문 + 반영 (9/16 신규, Figma "4.2-3"/"4.2-2 모드 B"). StarItem은 DB에
# 저장하지 않으므로(CLAUDE.md 3장) 프론트가 들고 있는 값을 그대로 왕복시킨다 —
# StarItemResponse와 필드는 같지만 이건 입력(body)용이라 별도 모델로 둔다.
class StarItemPayload(BaseModel):
    title: str
    period: str
    situation: str
    task: str
    action: str
    result: str
    source_dates: list[str] = []
    source_card_ids: list[int] = []


class StarQuestionsRequest(BaseModel):
    item: StarItemPayload


class StarQuestionsResponse(BaseModel):
    questions: list[str]


class QaPair(BaseModel):
    question: str
    answer: str


class StarApplyAnswersRequest(BaseModel):
    item: StarItemPayload
    answers: list[QaPair] = Field(max_length=3)


class StarApplyAnswersResponse(BaseModel):
    updated_item: StarItemResponse
    changed_field: str


# Word(.docx) 내보내기 (9/16 신규). 프론트가 이미 "마크다운 복사"에 쓰는 텍스트를
# 그대로 보낸다 — 백엔드는 STAR 구조를 다시 조합하지 않는다.
class ResumeExportRequest(BaseModel):
    content: str


class HealthResponse(BaseModel):
    status: str
    db: bool
    chroma: bool
    llm: bool


class JDMatchItem(BaseModel):
    company: str
    title: str
    required_skills: list[str]
    description: str
    score: float


class JDMatchResponse(BaseModel):
    matches: list[JDMatchItem]


class NotionSyncRequest(BaseModel):
    """docs/05-api-contract.md 5장. user_token은 필수 — settings.notion_token으로
    암묵 폴백하지 않는다(다른 사용자가 개발자 본인 노션 데이터를 끌어오는 사고 방지).

    주의(구현 노트): 계약 문서는 page_id를 함께 받지만, 현재
    `notion_client.fetch_notion_entries()`는 특정 페이지 하나만 골라오는 기능이 없고
    이 토큰과 공유된 페이지 전체를 가져온다. page_id는 그래서 받되 아직 사용하지
    않는다 — 특정 페이지만 고르는 기능이 필요해지면 notion_client 쪽부터 확장해야 한다.
    """

    user_token: str
    page_id: str | None = None


class NotionSyncResponse(BaseModel):
    imported: int
    cards: list[CardResponse]


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscribeRequest(BaseModel):
    """docs/05-api-contract.md 7장 + 추가 필드.

    계약 문서는 endpoint/keys만 보여주지만, 실제 발송 시각 계산
    (`push_sender.send_due_reminders()`)에는 "몇 시에 보낼지"(leave_time)가 필요하다.
    계약 문서 "변경 규칙"이 허용하는 범위(추가는 자유롭다)에서 필드를 더했다 —
    Track C에 공유 필요.
    """

    endpoint: str
    keys: PushKeys
    leave_time: str  # "HH:MM"


class PushUnsubscribeRequest(BaseModel):
    endpoint: str


class VapidPublicKeyResponse(BaseModel):
    public_key: str


# 온보딩 프로필 (9/14 신규, docs/05-api-contract.md 9장).
# 직군/연차는 자유 입력이 아니라 고정된 칩 세트다(Figma "2.0 목적지·푸시 설정" 화면,
# CLAUDE.md 2.4: 연차 직접 입력 배제 — 세그먼트 4개로 충분). Literal로 강제하면 잘못된
# 값이 스키마 단계에서 422로 걸러진다.
JobField = Literal["개발", "기획·PM", "디자인", "마케팅", "영업", "데이터"]
YearsSegment = Literal["1-3", "4-6", "7-10", "10+"]


class ProfileResponse(_FromAttributes):
    job_field: JobField | None
    job_detail: str | None
    years_segment: YearsSegment | None


class ProfileUpdateRequest(BaseModel):
    job_field: JobField
    # 세부 직무는 직군에 따라 선택지가 달라지고(Figma엔 "개발" 하위만 구체적으로
    # 나열돼 있음), 아직 모든 직군의 하위 칩 세트가 확정되지 않아 자유 문자열로 둔다.
    job_detail: str | None = None
    years_segment: YearsSegment


class MeResponse(BaseModel):
    """GET /api/auth/me — 프론트가 "로그인 상태인가"를 판단하는 유일한 창구(9/14 신규).

    401이면 로그아웃 상태 — 프론트 `getMe()`는 그 경우 예외 대신 null을 반환하도록
    감싼다(로그아웃은 에러가 아니라 정상적인 한 가지 상태이므로).
    """

    id: int
    nickname: str | None
    profile_image_url: str | None
