"""Pydantic 응답/요청 스키마 — Track B(FastAPI) 담당.

docs/05-api-contract.md 1~3, 8절의 필드명/모양을 그대로 따른다. 필드 이름은
내부 dataclass(Card, Project, StarItem)와 1:1로 맞춰뒀으므로 `model_validate()`로
(from_attributes=True) dataclass 인스턴스를 바로 변환할 수 있다.
"""
from pydantic import BaseModel, ConfigDict


class _FromAttributes(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CardCreateRequest(BaseModel):
    raw_text: str


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
