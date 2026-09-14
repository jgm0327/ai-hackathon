"""Pydantic 응답/요청 스키마 — Track B(FastAPI) 담당.

docs/05-api-contract.md 1~3, 8절의 필드명/모양을 그대로 따른다. 필드 이름은
내부 dataclass(Card, Project, StarItem)와 1:1로 맞춰뒀으므로 `model_validate()`로
(from_attributes=True) dataclass 인스턴스를 바로 변환할 수 있다.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict


class _FromAttributes(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CardCreateRequest(BaseModel):
    raw_text: str


class CardTagsUpdateRequest(BaseModel):
    """PATCH /api/cards/{id} — 카테고리(스킬 태그) 직접 수정 (9/14 신규).

    이름/문장 등 다른 필드는 안 받는다 — 태그 수정만 지원(가끔 손보는 용도, CLAUDE.md 2.4
    정신: 폴더 CRUD처럼 여기도 최소 기능만).
    """

    skill_tags: list[str]


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


class CardListResponse(BaseModel):
    cards: list[CardResponse]


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
