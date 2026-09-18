"""Pydantic 응답/요청 스키마 — Track B(FastAPI) 담당.

docs/05-api-contract.md 1~3, 8절의 필드명/모양을 그대로 따른다. 필드 이름은
내부 dataclass(Card, Project, StarItem)와 1:1로 맞춰뒀으므로 `model_validate()`로
(from_attributes=True) dataclass 인스턴스를 바로 변환할 수 있다.
"""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _FromAttributes(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# 입력 길이 상한 (9/17 신규)
#
# LLM에 그대로 실려 가는 필드는 길이를 안 막으면 그대로 API 청구서가 된다 —
# 예를 들어 raw_text에 소설 한 권을 붙여넣으면 그게 전부 프롬프트로 간다.
# 여기 값들은 "정상 사용이면 절대 안 닿는데 악용/실수는 막는" 선으로 잡았다.
# 상한을 넘으면 Pydantic이 422로 자동 거절하므로 LLM 호출 자체가 일어나지 않는다.
# ---------------------------------------------------------------------------
MAX_RAW_TEXT = 2_000  # 퇴근 전 한 줄 메모 (CLAUDE.md 1장 "3초 만에 끝내기")
MAX_SENTENCE = 2_000  # 정제 문장 / STAR 각 필드
MAX_TITLE = 200
MAX_JD_TEXT = 20_000  # 채용공고 본문 — 긴 공고도 통과하되 문서 통째 붙여넣기는 차단
MAX_EXISTING_ITEM = 1_000  # 기존 경력기술서 문장 1건
MAX_DRAFT_CONTENT = 100_000  # 초안 저장/Word 내보내기 — LLM을 안 타므로 넉넉히
MAX_TAGS = 20
MAX_TAG = 50
MAX_TOKEN = 500  # 노션 통합 토큰 등 외부 자격증명 문자열
MAX_QUESTION = 500
MAX_ANSWER = 1_000

# 리스트 안의 문자열 하나하나에도 상한을 건다 — 개수만 막으면 "10개 × 각 1MB"가 뚫린다.
_Tag = Annotated[str, Field(max_length=MAX_TAG)]
_ExistingItem = Annotated[str, Field(max_length=MAX_EXISTING_ITEM)]


class CardCreateRequest(BaseModel):
    # min_length=1 (9/17): 빈 메모도 그대로 parse_note()까지 가서 LLM을 한 번 부르고
    # 내용 없는 카드를 만든다(실측 확인). 정리할 내용이 없으면 부를 이유도 없다.
    # 공백만 있는 경우는 라우터가 따로 거른다 — Pydantic은 공백도 글자로 세기 때문.
    raw_text: str = Field(min_length=1, max_length=MAX_RAW_TEXT)
    # 9/18 신규 — Figma 3.1-q "변환 전 추가 질문"에 유저가 직접 답한 수치.
    # 안 보내면(건너뛰기) 예전과 완전히 같은 동작이다. 이 값은 지어낸 게 아니라
    # 유저가 타이핑한 값이므로 문장에 넣어도 CLAUDE.md 2.2에 어긋나지 않는다.
    metric_answer: str | None = Field(default=None, max_length=MAX_ANSWER)


class MetricQuestionRequest(BaseModel):
    """POST /api/cards/metric-question — 변환 전에 "숫자가 빠졌는지"만 물어본다.

    카드를 만들지 않는다. 저장은 뒤이은 POST /api/cards가 한다 — 유저가 질문 화면에서
    뒤로 나가버려도 반쯤 저장된 카드가 남지 않게 하기 위해서다.
    """

    raw_text: str = Field(min_length=1, max_length=MAX_RAW_TEXT)


class MetricQuestionResponse(BaseModel):
    """`question`이 빈 문자열이면 물어볼 게 없다는 뜻 — 프론트는 화면을 건너뛴다."""

    question: str = ""
    placeholder: str = ""


class MetricAnswerRequest(BaseModel):
    """POST /api/cards/{id}/metric-answer — Figma 3.1-n "지금 채우기" (9/18 신규)."""

    answer: str = Field(min_length=1, max_length=MAX_ANSWER)


class CardTranslateRequest(BaseModel):
    """POST /api/cards/{id}/translate — Figma 3.1-b / 3.1-c "직무 전환 번역".

    `target_job`은 온보딩 2/4에서 고른 목표 직무 중 하나다. 프론트가 그중 하나를
    실어 보낸다(서버가 고르지 않는다 — 여러 개를 오가는 건 유저의 선택이다).
    """

    target_job: str = Field(min_length=1, max_length=MAX_TITLE)


class CardTranslateResponse(BaseModel):
    related: bool
    headline: str
    translated_sentence: str
    #  related=False일 때만 채워진다 (3.1-c "다음 기록 제안").
    suggestion: str = ""


class CardTagsUpdateRequest(BaseModel):
    """PATCH /api/cards/{id} — 카테고리(스킬 태그)/문장 직접 수정 (9/14 태그, 9/15 문장 추가).

    가끔(연 몇 회, `/stack`에서) 손보는 용도라 두 필드 다 optional — 최소 하나는
    와야 하고(라우터가 체크, 둘 다 없으면 400), 넘어온 것만 바뀐다.
    """

    skill_tags: list[_Tag] | None = Field(default=None, max_length=MAX_TAGS)
    refined_sentence: str | None = Field(default=None, max_length=MAX_SENTENCE)
    # 9/18 신규 — Figma 3.1-d "AI 문장으로 되돌리기". true면 refined_sentence를
    # 무시하고 카드에 보관된 ai_sentence로 되돌린다(되돌릴 원본이 없으면 400).
    revert_to_ai: bool = False


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
    # 9/18 신규 — Figma 3.1-d "문장 수정" 시트가 "AI 문장으로 되돌리기"를 띄울지
    # 판단하는 값. `sentence_edited`가 true고 `ai_sentence`가 있을 때만 띄운다.
    # 마이그레이션 이전 카드는 ai_sentence가 null이라 자연스럽게 안 뜬다.
    ai_sentence: str | None = None
    sentence_edited: bool = False
    # 9/18 신규 — 첨부 사진 장수 (Figma 4.1-b 타임라인의 "사진 2", 4.1-j의 44px
    # 썸네일 유무). 목록 응답에서 카드마다 사진을 따로 조회하지 않게 라우터가 한 번에
    # 세어 채운다. 사진 자체는 `GET /api/cards/{id}/photos`로 받는다.
    photo_count: int = 0


class CardListResponse(BaseModel):
    cards: list[CardResponse]


# 기록 첨부 사진 (9/18 신규, Figma "03 · 커리어 스택" 4.1-b "첨부한 사진").
# `stored_name`(디스크 파일명)은 **응답에 싣지 않는다** — 클라이언트는 `id`로만
# 접근하면 되고, 내부 파일명을 노출하면 경로를 추측당할 여지만 생긴다.
class CardPhotoResponse(_FromAttributes):
    id: int
    card_id: int
    original_name: str
    mime_type: str
    byte_size: int
    created_at: str


class CardPhotoListResponse(BaseModel):
    photos: list[CardPhotoResponse]


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


# "4.1-i 분류 수정 (반자동 · 미분류 처리)" (9/18 신규). 역량 태그가 없는 기록에
# **이미 있는 역량 중** 가까운 것을 후보로 붙여 준다 — 없는 역량을 지어내지 않는다.
class CardTagSuggestion(BaseModel):
    card_id: int
    card: CardResponse
    suggested_tags: list[str]


class TagSuggestionsResponse(BaseModel):
    suggestions: list[CardTagSuggestion]
    # 화면의 "다른 역량에서 고르기"가 띄울 전체 역량 목록(이 유저가 실제로 가진 것).
    known_tags: list[str]


class BundleIntoProjectRequest(BaseModel):
    card_ids: list[int] = Field(max_length=500)
    name: str = Field(max_length=MAX_TITLE)
    started_at: str = Field(max_length=32)


class ProjectCreateRequest(BaseModel):
    name: str = Field(max_length=MAX_TITLE)
    started_at: str = Field(max_length=32)


class ProjectPatchRequest(BaseModel):
    """부분 업데이트. 계약 문서(2장)가 보여주는 3개 필드만 노출한다."""

    name: str | None = Field(default=None, max_length=MAX_TITLE)
    ended_at: str | None = Field(default=None, max_length=32)
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
    # 9/18까지 이 엔드포인트는 프로젝트 하나만 받았다. Figma 4.2.1 "범위 선택"이
    # 여러 프로젝트 + 미분류 기록을 한 문서(= "마스터 경력기술서")로 묶으라고 해서
    # 스코프를 넓혔다. 기존 호출부 하위 호환을 위해 `project_id`는 그대로 두고
    # (단독으로 넘어오면 예전과 100% 같은 동작), 아래 두 필드를 선택으로 추가한다.
    project_id: int | None = None
    project_ids: list[int] | None = Field(default=None, max_length=50)
    include_unassigned: bool = False
    jd_text: str | None = Field(default=None, max_length=MAX_JD_TEXT)
    # 9/18 신규 — Figma 4.1-j "이 역량으로 문장 만들기". 주면 대표 태그가 이 역량인
    # 카드만 묶는다. 프로젝트별로 나눠 부르는 구조는 그대로라 프로젝트 경계는 유지된다.
    skill_tag: str | None = Field(default=None, max_length=MAX_TITLE)


# Figma 4.3 "내 경력기술서 (저장본)" (9/18 신규). `resume_drafts`(작업 중 초안)와는
# 다른 개념이다 — 이건 이름 붙여 남겨둔 완성본이고 여러 개 가질 수 있다.
class SavedResumeCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=MAX_TITLE)
    content: str = Field(max_length=MAX_DRAFT_CONTENT)
    # 목록에 그대로 찍히는 숫자라 저장 시점에 실제로 센 값을 받는다 — 나중에 본문에서
    # 역산하면 저장 당시와 달라질 수 있고, 그건 없는 숫자를 만드는 셈이다(2.2).
    item_count: int = Field(default=0, ge=0, le=1000)
    card_count: int = Field(default=0, ge=0, le=100000)
    jd_based: bool = False


class SavedResumeResponse(_FromAttributes):
    id: int
    title: str
    item_count: int
    card_count: int
    jd_based: bool
    created_at: str
    updated_at: str


class SavedResumeDetailResponse(SavedResumeResponse):
    """목록엔 본문을 싣지 않는다 — 저장본이 여럿이면 응답이 통째로 무거워진다."""

    content: str


class SavedResumeListResponse(BaseModel):
    resumes: list[SavedResumeResponse]


# Figma 4.1-h "내 경력기술서  3개" (9/18 신규) — 저장본 개수.
class ResumeDraftCountResponse(BaseModel):
    count: int


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
    # 9/18 신규 — 마스터 경력기술서(여러 프로젝트를 한 문서로)에서 이 항목이 어느
    # 프로젝트 카드로 만들어졌는지. 단일 프로젝트 초안에서는 null이고, 그때 프론트는
    # 프로젝트 헤드(Figma 41:254 "project head")를 그리지 않는다.
    project_id: int | None = None
    project_name: str | None = None


class ResumeResponse(BaseModel):
    items: list[StarItemResponse]


# 경력기술서 초안 저장 (9/14 신규, docs/05-api-contract.md 3장). AI가 만든 STAR
# 구조 자체가 아니라, 유저가 그걸 가져다 직접 고친 자유 텍스트(마크다운)를 저장한다
# — CLAUDE.md 3장이 막는 "AI 그룹핑을 정식 데이터로 저장"과는 다른 문제라서
# 별도로 허용됨(src/storage/db.py의 ResumeDraft 참고).
class ResumeDraftResponse(BaseModel):
    # 9/18 — 마스터 초안(여러 프로젝트를 한 문서로)은 프로젝트에 귀속되지 않아 null.
    project_id: int | None
    # 저장된 초안이 없으면(또는 project_id가 이 유저 소유가 아니면) 둘 다 None.
    content: str | None
    updated_at: str | None


class ResumeDraftSaveRequest(BaseModel):
    # null이면 마스터 초안(master_resume_drafts, 유저당 1개)에 저장한다.
    project_id: int | None = None
    content: str = Field(max_length=MAX_DRAFT_CONTENT)


# "기존 경력기술서 붙여넣기 → Before/After 대조" (9/15 신규, docs/05-api-contract.md
# 3장). 완전히 선택 사항 — 위 STAR 생성/초안 저장 경로와 독립적으로 동작한다.
class ResumeEnhanceRequest(BaseModel):
    # 9/18 — ResumeRequest와 같은 범위 필드. 붙여넣기/JD 매칭도 "지금 보고 있는
    # 경력기술서"와 같은 범위의 카드를 근거로 써야 대조 결과가 어긋나지 않는다.
    project_id: int | None = None
    project_ids: list[int] | None = Field(default=None, max_length=50)
    include_unassigned: bool = False
    existing_items: list[_ExistingItem] = Field(max_length=10)


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
    project_id: int | None = None
    project_ids: list[int] | None = Field(default=None, max_length=50)
    include_unassigned: bool = False
    jd_text: str = Field(max_length=MAX_JD_TEXT)


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
    title: str = Field(max_length=MAX_TITLE)
    period: str = Field(max_length=64)
    situation: str = Field(max_length=MAX_SENTENCE)
    task: str = Field(max_length=MAX_SENTENCE)
    action: str = Field(max_length=MAX_SENTENCE)
    result: str = Field(max_length=MAX_SENTENCE)
    source_dates: list[Annotated[str, Field(max_length=32)]] = Field(default=[], max_length=200)
    source_card_ids: list[int] = Field(default=[], max_length=200)
    # 9/18 신규 — StarItemResponse와 대칭. 역질문/답변 반영은 이 값을 읽지 않지만,
    # 프론트가 받은 항목을 그대로 돌려보내므로 왕복 중에 유실되지 않게 받아준다.
    project_id: int | None = None
    project_name: str | None = Field(default=None, max_length=MAX_TITLE)


class StarQuestionsRequest(BaseModel):
    item: StarItemPayload


class StarQuestionsResponse(BaseModel):
    questions: list[str]


class QaPair(BaseModel):
    question: str = Field(max_length=MAX_QUESTION)
    answer: str = Field(max_length=MAX_ANSWER)


class StarApplyAnswersRequest(BaseModel):
    item: StarItemPayload
    answers: list[QaPair] = Field(max_length=3)


class StarApplyAnswersResponse(BaseModel):
    updated_item: StarItemResponse
    changed_field: str


# Word(.docx) 내보내기 (9/16 신규). 프론트가 이미 "마크다운 복사"에 쓰는 텍스트를
# 그대로 보낸다 — 백엔드는 STAR 구조를 다시 조합하지 않는다.
class ResumeExportRequest(BaseModel):
    content: str = Field(max_length=MAX_DRAFT_CONTENT)


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


class NotionConnectionResponse(BaseModel):
    """노션 연결 상태 (9/18 신규).

    **`access_token`을 절대 싣지 않는다.** 서드파티 자격증명이라 서버 밖으로 나갈
    이유가 없다 — 화면엔 "어디에 연결됐는지"만 있으면 된다.

    `oauth_available`이 false면 `NOTION_OAUTH_CLIENT_ID`가 아직 없다는 뜻이라,
    프론트는 OAuth 버튼 대신 통합 토큰 입력을 보여준다.
    """

    connected: bool
    workspace_name: str | None = None
    oauth_available: bool = False


class NotionPageRequest(BaseModel):
    """노션 요청 공통 — 토큰만 받는다 (9/18 재작성).

    `user_token`은 **OAuth 연결이 없을 때만** 필수다. 연결이 있으면 서버가 보관 중인
    토큰을 쓰고 이 값은 무시된다(`routers/notion.py`의 `_resolve_token`).
    `settings.notion_token`(로컬 개발용 폴백)으로 암묵 폴백하면
    **다른 사용자가 개발자 본인의 노션 데이터를 끌어오는** 사고가 된다
    (docs/03-risk-fallback.md 리스크 6). 빈 문자열 거부는 라우터가 한다 — Pydantic의
    `str`은 빈 문자열을 통과시킨다.

    **토큰을 서버에 저장하지 않는다.** 서드파티 자격증명을 DB에 평문으로 눕히지 않으려고
    요청마다 받는다.
    """

    user_token: str = Field(max_length=MAX_TOKEN)


class NotionPageSummaryResponse(_FromAttributes):
    """페이지 선택 목록 한 줄 (Figma 3.0-b). **본문이 없다** — 목록엔 필요 없고,
    본문을 받으려면 페이지마다 블록 API를 또 불러야 한다."""

    page_id: str
    title: str
    last_edited_time: str


class NotionPageListResponse(BaseModel):
    pages: list[NotionPageSummaryResponse]


class NotionPageContentResponse(BaseModel):
    """고른 페이지 하나의 본문. 저장하지 않고 그대로 프론트 입력창으로 간다."""

    page_id: str
    title: str
    content: str


class PushKeys(BaseModel):
    p256dh: str = Field(max_length=MAX_TOKEN)
    auth: str = Field(max_length=MAX_TOKEN)


class PushSubscribeRequest(BaseModel):
    """docs/05-api-contract.md 7장 + 추가 필드.

    계약 문서는 endpoint/keys만 보여주지만, 실제 발송 시각 계산
    (`push_sender.send_due_reminders()`)에는 "몇 시에 보낼지"(leave_time)가 필요하다.
    계약 문서 "변경 규칙"이 허용하는 범위(추가는 자유롭다)에서 필드를 더했다 —
    Track C에 공유 필요.
    """

    endpoint: str = Field(max_length=2_000)
    keys: PushKeys
    leave_time: str = Field(max_length=16)  # "HH:MM"
    # 9/18 신규 — Figma 온보딩 4/4 "주말에는 쉬어요". 기본값 False라 기존 프론트가
    # 이 필드를 안 보내도 동작이 그대로다.
    skip_weekends: bool = False


class PushUnsubscribeRequest(BaseModel):
    endpoint: str = Field(max_length=2_000)


class VapidPublicKeyResponse(BaseModel):
    public_key: str


# 온보딩 프로필 (9/14 신규, docs/05-api-contract.md 9장).
# 직군/연차는 자유 입력이 아니라 고정된 칩 세트다(Figma "2.0 목적지·푸시 설정" 화면,
# CLAUDE.md 2.4: 연차 직접 입력 배제 — 세그먼트 4개로 충분). Literal로 강제하면 잘못된
# 값이 스키마 단계에서 422로 걸러진다.
# 9/18 — Figma "00 · 온보딩"(268:5731) 재설계로 직군 세트가 바뀌었다.
# 예전: 개발 / 기획·PM / 디자인 / 마케팅 / 영업 / 데이터
# 지금: 마케팅·광고 / 경영·비즈니스 / 디자인 / 개발 / 영업 / 고객서비스·리테일
JobField = Literal["마케팅·광고", "경영·비즈니스", "디자인", "개발", "영업", "고객서비스·리테일"]
YearsSegment = Literal["1-3", "4-6", "7-10", "10+"]


class CompanyPayload(BaseModel):
    """재직 이력 한 건 (9/18 신규, Figma 3/4 "어디서 얼마나 일하셨어요?").

    기간은 월 단위("2024-03" 또는 "2024.03")다 — Figma가 월까지만 받는다.
    `ended_at`이 없으면 재직 중.
    """

    name: str = Field(min_length=1, max_length=100)
    started_at: str = Field(max_length=16)
    ended_at: str | None = Field(default=None, max_length=16)


class ProfileResponse(_FromAttributes):
    # ⚠️ 응답 쪽은 Literal이 아니라 str이다. 9/18에 직군 세트가 바뀌었는데, 그 전에
    # 저장된 값("기획·PM", "데이터")을 Literal로 검증하면 **기존 유저의 프로필 조회가
    # 통째로 500난다.** 고정 칩만 허용한다는 원칙(CLAUDE.md 2.4)은 쓰기 경로
    # (ProfileUpdateRequest)에서 계속 강제하고, 읽기는 저장된 값을 그대로 돌려준다.
    job_field: str | None
    job_detail: str | None
    years_segment: YearsSegment | None
    # 9/18 신규 — 2/4 "어디로 가고 싶으세요?"(다중), 3/4 회사·기간.
    target_jobs: list[str] = []
    companies: list[CompanyPayload] = []
    # 3/4 화면이 보여주는 "지금까지 6년 3개월". 회사 목록에서 서버가 계산한 값이라
    # 프론트가 따로 세지 않아도 되고, 저장된 years_segment와 항상 같은 근거를 쓴다.
    total_months: int = 0


class ProfileUpdateRequest(BaseModel):
    job_field: JobField
    # 세부 직무(1/4에서 고른 직무 칩). 직군별 목록이 프론트의 분류표에 있고 서버는
    # 그 표를 들고 있지 않아 자유 문자열로 둔다 — 직군 자체는 위에서 Literal로 막는다.
    job_detail: str | None = Field(default=None, max_length=100)
    # 9/18 — 연차는 더 이상 직접 받지 않는다. 회사 기간에서 서버가 계산한다
    # (Figma "연차는 여기서 자동으로 계산해요"). 회사를 하나도 안 넣고 건너뛴 경우를
    # 위해 값 자체는 optional로 남겨둔다.
    years_segment: YearsSegment | None = None
    target_jobs: list[Annotated[str, Field(max_length=100)]] = Field(default=[], max_length=20)
    # None이면 회사 목록을 건드리지 않는다(직무만 고치러 다시 들어온 경우).
    companies: list[CompanyPayload] | None = Field(default=None, max_length=30)


class MeResponse(BaseModel):
    """GET /api/auth/me — 프론트가 "로그인 상태인가"를 판단하는 유일한 창구(9/14 신규).

    401이면 로그아웃 상태 — 프론트 `getMe()`는 그 경우 예외 대신 null을 반환하도록
    감싼다(로그아웃은 에러가 아니라 정상적인 한 가지 상태이므로).
    """

    id: int
    nickname: str | None
    profile_image_url: str | None


# ---------------------------------------------------------------------------
# 백업 내보내기 / 불러오기 (9/18 신규, Figma "5.0 설정" 41:333 / 41:338)
#
# 불러오기는 LLM을 타지 않고 저장된 값을 그대로 되살린다 — 그래서 요청 쪽에도
# refined_sentence/skill_tags가 그대로 들어온다(POST /api/cards와 다른 점).
# 길이 상한은 카드 생성 경로와 같은 값을 쓴다.
# ---------------------------------------------------------------------------
class BackupProject(_FromAttributes):
    id: int
    name: str = Field(max_length=MAX_TITLE)
    started_at: str = Field(max_length=32)
    ended_at: str | None = Field(default=None, max_length=32)


class BackupCard(_FromAttributes):
    id: int
    project_id: int | None = None
    raw_text: str = Field(max_length=MAX_RAW_TEXT)
    refined_sentence: str = Field(max_length=MAX_SENTENCE)
    skill_tags: list[_Tag] = Field(default=[], max_length=MAX_TAGS)
    confidence: float = 0.0
    created_at: str = Field(max_length=32)
    created_time: str | None = Field(default=None, max_length=16)


class BackupResponse(BaseModel):
    version: int
    exported_at: str
    projects: list[BackupProject]
    cards: list[BackupCard]


class BackupImportRequest(BaseModel):
    # 한 번에 통째로 들어오는 파일이라 개수 상한을 넉넉히 두되 무한은 아니게 막는다.
    projects: list[BackupProject] = Field(default=[], max_length=500)
    cards: list[BackupCard] = Field(default=[], max_length=20_000)


class BackupImportResponse(BaseModel):
    imported_projects: int
    imported_cards: int
