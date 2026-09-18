"""POST/GET/PATCH/DELETE /api/cards — CLAUDE.md 2.1: 매일 쓰는 경로, 가볍게 유지.

JD 매칭을 여기서 하지 않는다(run_pipeline이 이미 그렇게 되어 있음). 응답은
3~10초 걸릴 수 있으니 프론트는 스켈레톤을 띄운다(docs/05-api-contract.md 1장).

**구현 노트 (9/14, 카카오 로그인 Phase B)**: 전 엔드포인트가 `Depends(get_current_user)`로
로그인 유저를 받아 그 id로 storage를 스코핑한다 — 다른 유저의 카드는 존재 자체가
안 보인다(db.get_card/delete_card가 user_id로 필터링).

**구현 노트 (9/14, 카테고리 직접 수정 / 9/15, 문장 직접 수정 추가)**: PATCH는
`skill_tags`/`refined_sentence`만 받는다(둘 다 optional, 최소 하나) — 매일 쓰는
저장 경로(POST)는 여전히 LLM+캐노니컬라이제이션이 자동으로 뽑고, 사람이 손대는
건 저장 후 가끔(`/stack`에서)뿐이다. 2.1(매일 경로에 선택지 금지)을 지키는 설계.

**구현 노트 (9/15, 변환 실패 폴백)**: POST가 `run_pipeline()`에서 LLM 파싱 실패를
전파받으면 예전엔 카드가 통째로 안 저장됐다(CLAUDE.md P0 "저장소 없으면 제품이
없다"와 충돌). 이제 `run_pipeline()` 자체가 파싱 실패 시 원문을 그대로 폴백
저장하고 `refinement_failed` 플래그를 반환하므로, 이 라우터는 그 플래그를
응답에 얹기만 한다. `POST /cards/{id}/refine`으로 나중에 다시 정리를 시도할 수 있다.
"""
from fastapi import APIRouter, Depends, HTTPException

from src.agent.card_clustering import suggest_clusters
from src.agent.pipeline import add_metric_answer, retry_refinement, run_pipeline
from src.agent.tag_suggester import suggest_tags_for_cards
from src.api.rate_limit import limit_heavy, limit_light
from src.api.schemas import (
    BundleIntoProjectRequest,
    CardClusterSuggestion,
    CardCreateRequest,
    CardListResponse,
    CardResponse,
    CardTagsUpdateRequest,
    CardTagSuggestion,
    CardTranslateRequest,
    CardTranslateResponse,
    MetricAnswerRequest,
    MetricQuestionRequest,
    MetricQuestionResponse,
    ProjectResponse,
    SkillCategoryCount,
    SkillSummaryResponse,
    TagSuggestionsResponse,
    UnclassifiedSuggestionsResponse,
)
from src.parsing.parser import detect_missing_metric, translate_for_target_job
from src.auth.deps import get_current_user
from src.storage import db

router = APIRouter(tags=["cards"])


@router.post("/cards", response_model=CardResponse, status_code=201, dependencies=[Depends(limit_light)])
def create_card(
    payload: CardCreateRequest, current_user: db.User = Depends(get_current_user)
) -> CardResponse:
    # 공백만 있는 입력도 LLM을 부를 이유가 없다 — Pydantic의 min_length는 공백도
    # 글자로 세므로 여기서 한 번 더 거른다(notion.py의 user_token 검증과 같은 패턴).
    if not payload.raw_text.strip():
        raise HTTPException(status_code=422, detail="내용을 입력해 주세요.")
    result = run_pipeline(current_user.id, payload.raw_text, payload.metric_answer)
    card = db.get_card(current_user.id, result["card_id"])
    response = CardResponse.model_validate(card)
    response.refinement_failed = result["refinement_failed"]
    response.case_summary = result["parsed"].case_summary
    return response


@router.post(
    "/cards/metric-question",
    response_model=MetricQuestionResponse,
    dependencies=[Depends(limit_light)],
)
def metric_question_endpoint(
    payload: MetricQuestionRequest, current_user: db.User = Depends(get_current_user)
) -> MetricQuestionResponse:
    """"변환 전 추가 질문" (Figma "02 · 변환 결과" 3.1-q, 9/18 신규).

    CLAUDE.md 2.2가 정한 "숫자가 없으면 ... 유저에게 되묻는다(건너뛰기 가능)" 경로다.
    카드를 만들지 않고 **질문만** 돌려준다 — 저장은 뒤이은 POST /api/cards가 한다.

    2.1("평소 입력 비용 0")과의 균형은 프롬프트가 맡는다: 수치가 정말로 빠진 기록에만
    질문이 나오고 나머지는 빈 문자열로 와서 프론트가 화면을 건너뛴다. 판정 자체가
    실패해도 빈 값이 오므로(`detect_missing_metric`) 입력 흐름이 막히지 않는다.
    """
    if not payload.raw_text.strip():
        raise HTTPException(status_code=422, detail="내용을 입력해 주세요.")
    result = detect_missing_metric(payload.raw_text)
    return MetricQuestionResponse(question=result.question, placeholder=result.placeholder)


@router.post(
    "/cards/{card_id}/translate",
    response_model=CardTranslateResponse,
    dependencies=[Depends(limit_heavy)],
)
def translate_card_endpoint(
    card_id: int,
    payload: CardTranslateRequest,
    current_user: db.User = Depends(get_current_user),
) -> CardTranslateResponse:
    """"직무 전환 번역" (Figma 3.1-b / 3.1-c, 9/18 신규).

    같은 기록을 **목표 직무** 관점으로 다시 읽어준다. 번역 결과는 **저장하지 않는다** —
    카드 하나가 여러 목표 직무로 각각 다르게 읽힐 수 있고, 그걸 다 저장하기 시작하면
    관리 UI가 필요해진다(CLAUDE.md 3장이 AI 그룹핑을 저장하지 않는 것과 같은 이유).
    유저가 이 문장을 남기고 싶으면 복사하거나 "문장 고치기"로 직접 적용하면 된다.

    `current_job`은 프로필에서 읽는다 — 유저에게 다시 묻지 않는다(2.1). 프로필이
    비어 있으면 "현재 직무"라는 일반 표현을 쓴다(없는 직무를 지어내지 않는다).
    """
    card = db.get_card(current_user.id, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="카드를 찾을 수 없습니다")
    profile = db.get_profile(current_user.id)
    current_job = profile.job_detail or profile.job_field or "현재 직무"
    try:
        result = translate_for_target_job(
            card.raw_text, card.refined_sentence, current_job, payload.target_job
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail="지금은 다른 직무 관점으로 읽어드리기 어려워요."
        ) from exc
    return CardTranslateResponse(
        related=result.related,
        headline=result.headline,
        translated_sentence=result.translated_sentence,
        suggestion=result.suggestion,
    )


@router.post(
    "/cards/{card_id}/metric-answer",
    response_model=CardResponse,
    dependencies=[Depends(limit_light)],
)
def add_metric_answer_endpoint(
    card_id: int,
    payload: MetricAnswerRequest,
    current_user: db.User = Depends(get_current_user),
) -> CardResponse:
    """"3.1-n 결과 · 수치 없음"의 [지금 채우기] (9/18 신규).

    3.1-q가 **변환 전에** 묻는 경로라면 이건 **변환 후에** 채우는 경로다. 답한 값은
    `raw_text` 뒤에 한 줄로 붙고 문장이 다시 만들어진다 — 별도 컬럼에 두면 나중에
    "다시 만들기"로 재파싱할 때 그 숫자만 조용히 빠진다.

    유저가 타이핑한 값만 들어가므로 CLAUDE.md 2.2(숫자 생성 금지)에 어긋나지 않는다.
    """
    card = add_metric_answer(current_user.id, card_id, payload.answer)
    if card is None:
        raise HTTPException(status_code=404, detail="카드를 찾을 수 없습니다")
    return CardResponse.model_validate(card)


@router.post("/cards/{card_id}/refine", response_model=CardResponse, dependencies=[Depends(limit_light)])
def refine_card_endpoint(
    card_id: int, current_user: db.User = Depends(get_current_user)
) -> CardResponse:
    """폴백 저장된(원문 그대로인) 카드를 다시 AI로 정리해본다 (9/15 신규).

    실패하면 그대로 예외가 전파돼 500이 된다 — 폴백 저장이 이미 끝난 상태라
    재시도가 또 실패해도 데이터 유실은 없다(그대로 남아있음).
    """
    card = retry_refinement(current_user.id, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="카드를 찾을 수 없습니다")
    return CardResponse.model_validate(card)


@router.get("/cards", response_model=CardListResponse)
def list_cards_endpoint(
    project_id: int | None = None, current_user: db.User = Depends(get_current_user)
) -> CardListResponse:
    # list_cards()는 내부 계약상 오래된 순(build_resume에 넘길 때 시간순이 필요)이라
    # API 계약(최신순)에 맞추기 위해 여기서만 뒤집는다.
    cards = list(reversed(db.list_cards(current_user.id, project_id)))
    return CardListResponse(cards=_with_photo_counts(current_user.id, cards))


def _with_photo_counts(user_id: int, cards: list[db.Card]) -> list[CardResponse]:
    """카드 목록에 첨부 사진 장수를 채워 넣는다 (9/18 신규).

    카드마다 따로 세면 목록 하나에 쿼리가 N번 나간다 — `count_card_photos()`가 한 번에
    세어 주는 dict를 받아서 붙인다. 사진이 한 장도 없는 계정에서도 쿼리는 한 번이다.
    """
    counts = db.count_card_photos(user_id, [c.id for c in cards])
    responses = []
    for card in cards:
        response = CardResponse.model_validate(card)
        response.photo_count = counts.get(card.id, 0)
        responses.append(response)
    return responses


@router.get("/cards/skill-summary", response_model=SkillSummaryResponse)
def get_skill_summary(
    project_id: int | None = None, top_n: int = 4, current_user: db.User = Depends(get_current_user)
) -> SkillSummaryResponse:
    """홈 화면(Figma 100:692) "무엇이 쌓였나요" 버블 차트 (9/16 신규).

    `top_n` 기본값은 홈 화면 버블(최대 5개)용이다. `/stack`의 "역량 리스트"
    (Figma 100:692 "4.1-h")는 버블처럼 개수 제한이 없는 막대 리스트라 큰 값(예:
    50)을 넘겨서 사실상 전부 펼쳐 받는다 — `db.get_skill_category_counts()`가
    이미 카드를 대표 태그 기준으로 집계해서 반환하므로 여기서는 그대로 스키마에
    얹기만 한다.

    **`project_id`는 9/18부터 생략 가능하다** — 생략하면 프로젝트에 관계없이 그 유저의
    카드 전부를 집계한다(`GET /cards`가 이미 그렇게 동작한다). 프로젝트를 한 번도
    만들지 않은 계정은 카드가 전부 `project_id = NULL`로 쌓이는데, 그 상태에서 홈이
    집계를 못 받아 "기록 0 / 역량 0"을 보여주고 있었다(9/18 사용자 신고 —
    `/stack`은 필터 없이 불러서 같은 카드가 거기서만 보였다).
    """
    cards = db.list_cards(current_user.id, project_id)
    categories = db.get_skill_category_counts(current_user.id, project_id, top_n=top_n)
    return SkillSummaryResponse(
        total_cards=len(cards),
        categories=[SkillCategoryCount(tag=tag, count=count) for tag, count in categories],
    )


@router.delete("/cards/{card_id}", status_code=204)
def delete_card_endpoint(card_id: int, current_user: db.User = Depends(get_current_user)) -> None:
    db.delete_card(current_user.id, card_id)  # 다른 유저 소유이거나 없어도 멱등하게 무시됨


@router.patch("/cards/{card_id}", response_model=CardResponse)
def update_card_tags_endpoint(
    card_id: int,
    payload: CardTagsUpdateRequest,
    current_user: db.User = Depends(get_current_user),
) -> CardResponse:
    if payload.revert_to_ai:
        # "AI 문장으로 되돌리기" (Figma 3.1-d, 9/18) — 되돌릴 원본이 없으면(마이그레이션
        # 이전 카드) 아무것도 하지 않는다. 프론트는 원본이 있을 때만 버튼을 띄우므로
        # 여기 오는 건 경합이나 직접 호출뿐이다.
        existing = db.get_card(current_user.id, card_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="카드를 찾을 수 없습니다")
        if not existing.ai_sentence:
            raise HTTPException(status_code=400, detail="되돌릴 AI 문장이 없습니다")
        card = db.update_card(
            current_user.id,
            card_id,
            skill_tags=payload.skill_tags,
            refined_sentence=existing.ai_sentence,
            sentence_edited=False,
        )
        return CardResponse.model_validate(card)

    if payload.skill_tags is None and payload.refined_sentence is None:
        raise HTTPException(status_code=400, detail="skill_tags 또는 refined_sentence 중 하나는 있어야 합니다")
    card = db.update_card(
        current_user.id,
        card_id,
        skill_tags=payload.skill_tags,
        refined_sentence=payload.refined_sentence,
        # 문장을 손으로 고친 순간부터 "다시 만들기"가 그 문장을 덮어쓰지 않는다
        # (Figma 3.1-d "직접 고친 문장은 다시 변환해도 유지돼요"). 태그만 고치는
        # 요청은 이 플래그를 건드리지 않는다.
        sentence_edited=True if payload.refined_sentence is not None else None,
    )
    if card is None:
        raise HTTPException(status_code=404, detail="카드를 찾을 수 없습니다")
    return CardResponse.model_validate(card)


@router.get("/cards/unclassified/suggestions", response_model=UnclassifiedSuggestionsResponse)
def get_unclassified_suggestions(
    current_user: db.User = Depends(get_current_user),
) -> UnclassifiedSuggestionsResponse:
    """"4.1.1 AI 프로젝트 자동 제안" (9/14 신규) — project_id가 없는 카드끼리만
    비교해서 비슷한 것들을 묶어 후보로 제시한다. 이미 프로젝트가 배정된 카드는
    이 엔드포인트 자체가 조회 대상으로도 삼지 않는다(`db.list_unassigned_cards`).
    """
    cards = db.list_unassigned_cards(current_user.id)
    clusters = suggest_clusters(cards)
    cards_by_id = {c.id: c for c in cards}
    return UnclassifiedSuggestionsResponse(
        clusters=[
            CardClusterSuggestion(
                card_ids=cluster.card_ids,
                cards=[CardResponse.model_validate(cards_by_id[cid]) for cid in cluster.card_ids],
            )
            for cluster in clusters
        ]
    )


@router.get("/cards/tag-suggestions", response_model=TagSuggestionsResponse)
def get_tag_suggestions(
    project_id: int | None = None, current_user: db.User = Depends(get_current_user)
) -> TagSuggestionsResponse:
    """"4.1-i 분류 수정 (반자동 · 미분류 처리)" (9/18 신규).

    역량 태그가 **하나도 없는** 기록에, 이 유저가 이미 가진 역량 중 가까운 것 2개를
    후보로 붙여서 돌려준다. CLAUDE.md 2.3이 말하는 임베딩의 자리다("새 카드를 기존
    작업 그룹에 배정 — 보조적, 틀려도 손해 작음"). LLM을 부르지 않는다.

    확정은 이 엔드포인트가 하지 않는다 — 사용자가 화면에서 고른 뒤 기존
    `PATCH /api/cards/{id}`로 태그를 저장한다. AI가 고른 걸 그대로 쓰면 사용자가
    검증하지 않은 분류가 조용히 굳는다.
    """
    cards = [c for c in db.list_cards(current_user.id, project_id) if not c.skill_tags]
    known_tags = db.list_skill_tags(current_user.id)
    try:
        suggestions = suggest_tags_for_cards(cards, known_tags)
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail="지금은 역량을 추천해 드리기 어려워요."
        ) from exc
    by_id = {c.id: c for c in cards}
    return TagSuggestionsResponse(
        suggestions=[
            CardTagSuggestion(
                card_id=s.card_id,
                card=CardResponse.model_validate(by_id[s.card_id]),
                suggested_tags=s.suggested_tags,
            )
            for s in suggestions
        ],
        known_tags=known_tags,
    )


@router.post("/cards/bundle-into-project", response_model=ProjectResponse, status_code=201)
def bundle_cards_into_project(
    payload: BundleIntoProjectRequest, current_user: db.User = Depends(get_current_user)
) -> ProjectResponse:
    """선택된 카드들을 새 프로젝트로 묶는다 (9/14 신규). 프로젝트 이름은 AI가 짓지
    않고 사용자가 이 요청에 직접 실어 보낸다 — `create_project()` 계약 그대로.

    카드 소유권 검증은 `bulk_assign_cards_to_project()`가 `user_id` 조건으로
    자동 처리한다(다른 유저 card_id를 섞어 보내도 그 카드만 조용히 무시됨) — 별도
    사전 검증 없이도 안전하다.
    """
    project_id = db.create_project(current_user.id, payload.name, payload.started_at)
    db.bulk_assign_cards_to_project(current_user.id, payload.card_ids, project_id)
    project = db.get_project(current_user.id, project_id)
    return ProjectResponse.model_validate(project)
