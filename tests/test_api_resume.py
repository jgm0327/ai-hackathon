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
