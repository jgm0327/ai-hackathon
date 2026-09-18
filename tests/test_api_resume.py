"""Track B 담당: POST /api/resume 테스트 ★ 핵심 경로.

build_resume()의 LLM 호출부를 모킹해서 실제 API 호출 없이 build_career_doc() ->
build_resume() 오케스트레이션과 응답 스키마 변환을 검증한다.

DB 격리와 로그인 유저 오버라이드는 tests/conftest.py가 담당한다(9/14 카카오 로그인 Phase B).
"""
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.parsing.parser import ParsedEntry
from src.storage import db


@pytest.fixture
def client():
    return TestClient(app)


def _seed_cards(user_id: int, project_id: int) -> None:
    db.save_card(
        user_id,
        project_id,
        ParsedEntry(
            raw_text="레디스 캐시 붙임",
            refined_sentence="결제 API 응답 지연을 해소하기 위해 Redis 캐싱 레이어를 도입함",
            skill_tags=["Redis", "성능최적화", "결제시스템"],
            confidence=0.9,
        ),
        "2023-02-14",
    )
    db.save_card(
        user_id,
        project_id,
        ParsedEntry(
            raw_text="오류율 0.8% -> 0.3%",
            refined_sentence="Redis 캐싱 적용 이후 결제 오류율을 0.8%에서 0.3%로 개선함",
            skill_tags=["성능최적화", "결제시스템"],
            confidence=0.92,
        ),
        "2023-03-02",
    )


_MOCK_LLM_RESPONSE = json.dumps(
    {
        "items": [
            {
                "title": "결제 API 성능 개선",
                "period": "02.14 - 03.02",
                "situation": "결제 API 응답 지연으로 사용자 이탈이 발생하는 상황이었습니다.",
                "task": "응답 시간을 개선하고 결제 도메인 안정성을 확보해야 했습니다.",
                "action": "Redis 캐싱 레이어를 도입했습니다.",
                "result": "결제 오류율을 0.8%에서 0.3%로 낮췄습니다.",
                "source_indices": [1, 2],
            }
        ]
    },
    ensure_ascii=False,
)


def test_create_resume_requires_login(client):
    response = client.post("/api/resume", json={"project_id": 1})
    assert response.status_code == 401


def test_create_resume_merges_time_gap_pair(client, current_user_id):
    project_id = db.create_project(current_user_id, "A은행 차세대", "2023-02-01")
    _seed_cards(current_user_id, project_id)

    with patch("src.parsing.resume._call_llm", return_value=_MOCK_LLM_RESPONSE):
        response = client.post("/api/resume", json={"project_id": project_id})

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["title"] == "결제 API 성능 개선"
    assert item["result"] == "결제 오류율을 0.8%에서 0.3%로 낮췄습니다."
    assert item["source_dates"] == ["02.14", "03.02"]
    # list_cards()는 시간순(오래된 순)이라 source_indices [1, 2]는 02.14 카드, 03.02 카드 순.
    seeded = db.list_cards(current_user_id, project_id)
    assert item["source_card_ids"] == [seeded[0].id, seeded[1].id]


def test_create_resume_with_jd_text_passes_through(client, current_user_id):
    project_id = db.create_project(current_user_id, "A은행 차세대", "2023-02-01")
    _seed_cards(current_user_id, project_id)

    with patch("src.parsing.resume._call_llm", return_value=_MOCK_LLM_RESPONSE) as mock_llm:
        response = client.post(
            "/api/resume",
            json={"project_id": project_id, "jd_text": "백엔드 성능 최적화 경험자 우대"},
        )

    assert response.status_code == 200
    # jd_text가 프롬프트에 실제로 포함되어 LLM 호출부까지 전달됐는지 확인
    called_prompt = mock_llm.call_args[0][0]
    assert "백엔드 성능 최적화 경험자 우대" in called_prompt


def test_create_resume_empty_project_returns_empty_items(client, current_user_id):
    project_id = db.create_project(current_user_id, "빈 프로젝트", "2023-02-01")

    response = client.post("/api/resume", json={"project_id": project_id})

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_create_resume_never_fabricates_missing_result(client, current_user_id):
    """CLAUDE.md 2.2: 기록에 숫자가 없으면 result는 빈 문자열이어야 한다."""
    project_id = db.create_project(current_user_id, "온보딩", "2023-04-01")
    db.save_card(
        current_user_id,
        project_id,
        ParsedEntry(
            raw_text="신규 입사자 온보딩 문서 작성",
            refined_sentence="신규 입사자 온보딩 문서를 작성함",
            skill_tags=["문서작성"],
            confidence=0.8,
        ),
        "2023-04-01",
    )
    mock_response = json.dumps(
        {
            "items": [
                {
                    "title": "온보딩 문서화",
                    "period": "04.01",
                    "situation": "s",
                    "task": "t",
                    "action": "a",
                    "result": "",
                    "source_indices": [1],
                }
            ]
        },
        ensure_ascii=False,
    )

    with patch("src.parsing.resume._call_llm", return_value=mock_response):
        response = client.post("/api/resume", json={"project_id": project_id})

    assert response.json()["items"][0]["result"] == ""


def test_create_resume_ignores_another_users_project_cards(client, current_user_id):
    """소유권 강제 — 다른 유저의 project_id를 넣어도 그 사람 카드가 새어나오면 안 된다."""
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    other_project_id = db.create_project(other_user_id, "다른 유저 프로젝트", "2023-02-01")
    _seed_cards(other_user_id, other_project_id)

    with patch("src.parsing.resume._call_llm", return_value=_MOCK_LLM_RESPONSE) as mock_llm:
        response = client.post("/api/resume", json={"project_id": other_project_id})

    assert response.status_code == 200
    assert response.json() == {"items": []}
    mock_llm.assert_not_called()  # 카드가 안 보이니 build_resume 자체가 호출되면 안 됨


# --- GET/PUT /api/resume/draft (9/14 신규) ---


def test_get_resume_draft_requires_login(client):
    response = client.get("/api/resume/draft", params={"project_id": 1})
    assert response.status_code == 401


def test_put_resume_draft_requires_login(client):
    response = client.put("/api/resume/draft", json={"project_id": 1, "content": "x"})
    assert response.status_code == 401


def test_get_resume_draft_returns_null_when_never_saved(client, current_user_id):
    project_id = db.create_project(current_user_id, "A은행 차세대", "2023-02-01")

    response = client.get("/api/resume/draft", params={"project_id": project_id})

    assert response.status_code == 200
    assert response.json() == {"project_id": project_id, "content": None, "updated_at": None}


def test_put_then_get_resume_draft_roundtrip(client, current_user_id):
    project_id = db.create_project(current_user_id, "A은행 차세대", "2023-02-01")

    put_response = client.put(
        "/api/resume/draft",
        json={"project_id": project_id, "content": "# 결제 API 성능 개선\n직접 고친 내용"},
    )
    assert put_response.status_code == 200
    body = put_response.json()
    assert body["content"] == "# 결제 API 성능 개선\n직접 고친 내용"
    assert body["updated_at"]  # 타임스탬프가 채워져 있어야 함

    get_response = client.get("/api/resume/draft", params={"project_id": project_id})
    assert get_response.json()["content"] == "# 결제 API 성능 개선\n직접 고친 내용"


def test_put_resume_draft_overwrites_previous_save(client, current_user_id):
    project_id = db.create_project(current_user_id, "A은행 차세대", "2023-02-01")

    client.put("/api/resume/draft", json={"project_id": project_id, "content": "v1"})
    client.put("/api/resume/draft", json={"project_id": project_id, "content": "v2"})

    response = client.get("/api/resume/draft", params={"project_id": project_id})
    assert response.json()["content"] == "v2"


def test_put_resume_draft_rejects_project_not_owned_by_user(client, current_user_id):
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    other_project_id = db.create_project(other_user_id, "다른 유저 프로젝트", "2023-02-01")

    response = client.put(
        "/api/resume/draft", json={"project_id": other_project_id, "content": "가로채기 시도"}
    )

    assert response.status_code == 404
    assert db.get_resume_draft(other_user_id, other_project_id) is None


# --- POST /api/resume/enhance (9/15 신규) ---


_MOCK_ENHANCE_RESPONSE = json.dumps(
    {
        "items": [
            {
                "item_index": 1,
                "enhanced": "Redis 캐싱 레이어 도입으로 결제 API 응답 지연을 해소하고 오류율을 0.8%에서 0.3%로 개선했습니다.",
                "gap_comment": "왜 Redis를 골랐는지가 없어요.",
                "source_indices": [1, 2],
            }
        ]
    },
    ensure_ascii=False,
)


def test_enhance_resume_requires_login(client):
    response = client.post(
        "/api/resume/enhance", json={"project_id": 1, "existing_items": ["결제 API 성능 개선 담당"]}
    )
    assert response.status_code == 401


def test_enhance_resume_merges_matched_cards(client, current_user_id):
    project_id = db.create_project(current_user_id, "A은행 차세대", "2023-02-01")
    _seed_cards(current_user_id, project_id)

    with patch("src.parsing.resume._call_llm", return_value=_MOCK_ENHANCE_RESPONSE):
        response = client.post(
            "/api/resume/enhance",
            json={"project_id": project_id, "existing_items": ["결제 API 성능 개선 담당"]},
        )

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["original"] == "결제 API 성능 개선 담당"
    assert "0.3%" in items[0]["enhanced"]
    seeded = db.list_cards(current_user_id, project_id)
    assert items[0]["source_card_ids"] == [seeded[0].id, seeded[1].id]


def test_enhance_resume_no_matching_cards_keeps_original(client, current_user_id):
    project_id = db.create_project(current_user_id, "빈 프로젝트", "2023-02-01")

    response = client.post(
        "/api/resume/enhance",
        json={"project_id": project_id, "existing_items": ["결제 API 성능 개선 담당"]},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["enhanced"] == "결제 API 성능 개선 담당"
    assert item["source_card_ids"] == []


def test_enhance_resume_ignores_another_users_project_cards(client, current_user_id):
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    other_project_id = db.create_project(other_user_id, "다른 유저 프로젝트", "2023-02-01")
    _seed_cards(other_user_id, other_project_id)

    response = client.post(
        "/api/resume/enhance",
        json={"project_id": other_project_id, "existing_items": ["결제 API 성능 개선 담당"]},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["enhanced"] == "결제 API 성능 개선 담당"


def test_enhance_resume_rejects_more_than_ten_items(client, current_user_id):
    project_id = db.create_project(current_user_id, "A은행 차세대", "2023-02-01")

    response = client.post(
        "/api/resume/enhance",
        json={"project_id": project_id, "existing_items": [f"항목 {i}" for i in range(11)]},
    )

    assert response.status_code == 422


def test_get_resume_draft_does_not_leak_another_users_draft(client, current_user_id):
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    other_project_id = db.create_project(other_user_id, "다른 유저 프로젝트", "2023-02-01")
    db.save_resume_draft(other_user_id, other_project_id, "다른 유저 초안", "2026-09-14T00:00:00")

    response = client.get("/api/resume/draft", params={"project_id": other_project_id})

    assert response.status_code == 200
    assert response.json() == {"project_id": other_project_id, "content": None, "updated_at": None}


# --- POST /api/resume/jd-requirements (9/16 신규) ---


_MOCK_JD_REQUIREMENTS_RESPONSE = json.dumps(
    {
        "job_title": "백엔드 엔지니어",
        "company": "A은행",
        "years_label": "경력 3~7년",
        "requirements": [
            {"requirement": "캐싱 시스템 설계 경험", "source_indices": [1, 2]},
            {"requirement": "Kubernetes 운영 경험", "source_indices": []},
        ],
    },
    ensure_ascii=False,
)


def test_jd_requirements_requires_login(client):
    response = client.post(
        "/api/resume/jd-requirements", json={"project_id": 1, "jd_text": "백엔드 채용"}
    )
    assert response.status_code == 401


def test_jd_requirements_matches_cards(client, current_user_id):
    project_id = db.create_project(current_user_id, "A은행 차세대", "2023-02-01")
    _seed_cards(current_user_id, project_id)

    with patch("src.parsing.resume._call_llm", return_value=_MOCK_JD_REQUIREMENTS_RESPONSE):
        response = client.post(
            "/api/resume/jd-requirements",
            json={"project_id": project_id, "jd_text": "백엔드 엔지니어 채용, A은행, 경력 3~7년"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["job_title"] == "백엔드 엔지니어"
    assert len(body["requirements"]) == 2
    seeded = db.list_cards(current_user_id, project_id)
    assert body["requirements"][0]["source_card_ids"] == [seeded[0].id, seeded[1].id]
    assert body["requirements"][1]["source_card_ids"] == []


def test_jd_requirements_ignores_another_users_project_cards(client, current_user_id):
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    other_project_id = db.create_project(other_user_id, "다른 유저 프로젝트", "2023-02-01")
    _seed_cards(other_user_id, other_project_id)

    with patch("src.parsing.resume._call_llm") as mock_llm:
        response = client.post(
            "/api/resume/jd-requirements",
            json={"project_id": other_project_id, "jd_text": "백엔드 채용"},
        )

    assert response.status_code == 200
    assert response.json()["requirements"] == []
    mock_llm.assert_not_called()  # 카드가 안 보이니 매칭 자체가 호출되면 안 됨


# --- POST /api/resume/star-questions, /api/resume/star-apply-answers (9/16 신규) ---


_STAR_ITEM_PAYLOAD = {
    "title": "가입 배너 전환율 개선",
    "period": "02.14",
    "situation": "가입 전환율이 낮았습니다.",
    "task": "전환율을 높여야 했습니다.",
    "action": "가입 배너 문구를 A/B 테스트했습니다.",
    "result": "전환율을 3.2%p 개선했습니다.",
    "source_dates": ["02.14"],
    "source_card_ids": [1],
}


def test_star_questions_requires_login(client):
    response = client.post("/api/resume/star-questions", json={"item": _STAR_ITEM_PAYLOAD})
    assert response.status_code == 401


def test_star_questions_returns_llm_questions(client, current_user_id):
    mock_response = json.dumps(
        {"questions": ["왜 그 문구였나요?", "다른 대안은 없었나요?"]}, ensure_ascii=False
    )
    with patch("src.parsing.resume._call_llm", return_value=mock_response):
        response = client.post("/api/resume/star-questions", json={"item": _STAR_ITEM_PAYLOAD})

    assert response.status_code == 200
    assert response.json()["questions"] == ["왜 그 문구였나요?", "다른 대안은 없었나요?"]


def test_star_apply_answers_updates_item(client, current_user_id):
    mock_response = json.dumps(
        {
            "field": "action",
            "updated_text": "가입 단계 이탈이 문구에 몰려 있다고 판단해 배너 카피부터 A/B 테스트했습니다.",
        },
        ensure_ascii=False,
    )
    with patch("src.parsing.resume._call_llm", return_value=mock_response):
        response = client.post(
            "/api/resume/star-apply-answers",
            json={
                "item": _STAR_ITEM_PAYLOAD,
                "answers": [{"question": "왜 그 문구였나요?", "answer": "이탈이 문구에 몰려 있어서"}],
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["changed_field"] == "action"
    assert "이탈" in body["updated_item"]["action"]
    assert body["updated_item"]["situation"] == _STAR_ITEM_PAYLOAD["situation"]


# --- POST /api/resume/export/docx (9/16 신규) ---


def test_export_docx_requires_login(client):
    response = client.post("/api/resume/export/docx", json={"content": "# 제목"})
    assert response.status_code == 401


def test_export_docx_returns_word_file(client, current_user_id):
    response = client.post(
        "/api/resume/export/docx",
        json={"content": "# 백엔드 · 1-3년차\n\n## 결제 API 성능 개선\n- 상황: s\n"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert "resume.docx" in response.headers["content-disposition"]
    assert len(response.content) > 0


def test_star_apply_answers_rejects_more_than_three_answers(client, current_user_id):
    response = client.post(
        "/api/resume/star-apply-answers",
        json={
            "item": _STAR_ITEM_PAYLOAD,
            "answers": [{"question": f"q{i}", "answer": f"a{i}"} for i in range(4)],
        },
    )
    assert response.status_code == 422


# --- 마스터 경력기술서: 범위 선택 (9/18 신규, Figma 4.2.1 "범위 선택") ---


def test_create_resume_with_multiple_projects_stamps_each_item(client, current_user_id):
    """여러 프로젝트를 한 문서로 만들 때, 각 항목에 출처 프로젝트가 찍혀야 한다.

    프론트가 이 값으로 프로젝트 헤드(Figma 41:254 "project head")를 그린다.
    """
    a_id = db.create_project(current_user_id, "A은행 차세대", "2023-02-01")
    _seed_cards(current_user_id, a_id)
    b_id = db.create_project(current_user_id, "B카드 정산", "2024-02-01")
    _seed_cards(current_user_id, b_id)

    with patch("src.parsing.resume._call_llm", return_value=_MOCK_LLM_RESPONSE):
        response = client.post("/api/resume", json={"project_ids": [b_id, a_id]})

    assert response.status_code == 200
    items = response.json()["items"]
    # 프로젝트마다 따로 묶였으므로 항목이 2개 — 한 덩어리로 합쳐지면 1개가 된다.
    assert [i["project_name"] for i in items] == ["B카드 정산", "A은행 차세대"]
    assert [i["project_id"] for i in items] == [b_id, a_id]


def test_create_resume_can_include_unassigned_cards(client, current_user_id):
    db.save_card(
        current_user_id,
        None,
        ParsedEntry(
            raw_text="회고 정리",
            refined_sentence="스프린트 회고를 정리함",
            skill_tags=["회고"],
            confidence=0.5,
        ),
        "2023-02-20",
    )

    with patch("src.parsing.resume._call_llm", return_value=_MOCK_LLM_RESPONSE):
        response = client.post(
            "/api/resume", json={"project_ids": [], "include_unassigned": True}
        )

    assert response.status_code == 200
    items = response.json()["items"]
    assert [i["project_name"] for i in items] == ["미분류 기록"]
    assert items[0]["project_id"] is None


def test_create_resume_single_project_still_works_with_old_payload(client, current_user_id):
    """기존 계약(`project_id` 하나)이 그대로 동작해야 한다 — 프론트 배포 순서와 무관하게."""
    project_id = db.create_project(current_user_id, "A은행 차세대", "2023-02-01")
    _seed_cards(current_user_id, project_id)

    with patch("src.parsing.resume._call_llm", return_value=_MOCK_LLM_RESPONSE):
        response = client.post("/api/resume", json={"project_id": project_id})

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "결제 API 성능 개선"
    assert items[0]["project_id"] == project_id


# --- 마스터 초안 저장 (project_id 없이) ---


def test_master_draft_roundtrip(client, current_user_id):
    assert client.get("/api/resume/draft").json() == {
        "project_id": None,
        "content": None,
        "updated_at": None,
    }

    saved = client.put("/api/resume/draft", json={"content": "# 마스터 초안"})
    assert saved.status_code == 200
    assert saved.json()["project_id"] is None
    assert saved.json()["content"] == "# 마스터 초안"

    assert client.get("/api/resume/draft").json()["content"] == "# 마스터 초안"


def test_master_draft_is_separate_from_project_draft(client, current_user_id):
    project_id = db.create_project(current_user_id, "A은행 차세대", "2023-02-01")
    client.put("/api/resume/draft", json={"project_id": project_id, "content": "# 프로젝트 초안"})
    client.put("/api/resume/draft", json={"content": "# 마스터 초안"})

    assert client.get(f"/api/resume/draft?project_id={project_id}").json()["content"] == (
        "# 프로젝트 초안"
    )
    assert client.get("/api/resume/draft").json()["content"] == "# 마스터 초안"


def test_master_draft_does_not_leak_between_users(client, current_user_id):
    client.put("/api/resume/draft", json={"content": "# 내 마스터 초안"})

    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    from src.auth.deps import get_current_user

    app.dependency_overrides[get_current_user] = lambda: db.get_user(other_user_id)
    try:
        assert client.get("/api/resume/draft").json()["content"] is None
    finally:
        app.dependency_overrides[get_current_user] = lambda: db.get_user(current_user_id)
