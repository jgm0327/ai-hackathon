"""Track B 담당: POST/GET/DELETE /api/cards 테스트.

DB 격리와 로그인 유저 오버라이드는 tests/conftest.py의 `_isolated_db`(autouse)/
`current_user_id` 픽스처가 담당한다(9/14 카카오 로그인 Phase B).
"""
import json
import re
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.parsing.parser import ParsedEntry
from src.storage import db

MOCK_LLM_RESPONSE = json.dumps(
    {
        "refined_sentence": "결제 API 응답 지연을 해소하기 위해 Redis 캐싱 레이어를 도입했습니다.",
        "skill_tags": ["Redis", "성능최적화", "결제시스템"],
        "confidence": 0.91,
        "case_summary": "오늘 기록은 결제 API 성능 개선 케이스입니다.",
    },
    ensure_ascii=False,
)


@pytest.fixture(autouse=True)
def _no_op_canonicalize(monkeypatch):
    """태그 캐노니컬라이제이션(임베딩/Chroma)은 test_tag_canonicalizer.py가 검증한다.

    여기서는 API 레이어만 격리해서 보고 싶으므로 항등 함수로 대체한다 — 안 그러면
    이 테스트들이 실제 임베딩 provider(로컬 Ollama 등)에 의존하게 된다.
    """
    monkeypatch.setattr("src.agent.pipeline.canonicalize_tags", lambda tags: tags)
    yield


@pytest.fixture
def client():
    return TestClient(app)


def test_create_card_requires_login(client):
    """로그인 없이(세션 쿠키 없이) 호출하면 401 — current_user_id 픽스처를 안 썼을 때."""
    response = client.post("/api/cards", json={"raw_text": "결제 API 느려서 레디스 캐시 붙임"})
    assert response.status_code == 401


def test_create_card_returns_201_with_parsed_fields(client, current_user_id):
    with patch("src.parsing.parser._call_llm", return_value=MOCK_LLM_RESPONSE):
        response = client.post("/api/cards", json={"raw_text": "결제 API 느려서 레디스 캐시 붙임"})

    assert response.status_code == 201
    body = response.json()
    assert body["raw_text"] == "결제 API 느려서 레디스 캐시 붙임"
    assert body["refined_sentence"] == "결제 API 응답 지연을 해소하기 위해 Redis 캐싱 레이어를 도입했습니다."
    assert body["skill_tags"] == ["Redis", "성능최적화", "결제시스템"]
    assert body["confidence"] == 0.91
    assert body["project_id"] is None
    assert "id" in body
    assert "created_at" in body
    # 9/16 신규 — 결과 출력 모달(Figma 41:139) 문구.
    assert body["case_summary"] == "오늘 기록은 결제 API 성능 개선 케이스입니다."
    # 9/16 신규 — 홈 화면(Figma 100:692) "오늘 남긴 것" 목록용 "HH:MM" 시각.
    assert re.fullmatch(r"\d{2}:\d{2}", body["created_time"])


def test_create_card_auto_assigns_current_project(client, current_user_id):
    project_id = db.create_project(current_user_id, "A은행 차세대", "2023-02-01")

    with patch("src.parsing.parser._call_llm", return_value=MOCK_LLM_RESPONSE):
        response = client.post("/api/cards", json={"raw_text": "레디스 캐시 붙임"})

    assert response.json()["project_id"] == project_id


def test_list_cards_empty(client, current_user_id):
    response = client.get("/api/cards")
    assert response.status_code == 200
    assert response.json() == {"cards": []}


def test_list_cards_returns_newest_first(client, current_user_id):
    with patch("src.parsing.parser._call_llm", return_value=MOCK_LLM_RESPONSE):
        client.post("/api/cards", json={"raw_text": "첫 번째"})
        client.post("/api/cards", json={"raw_text": "두 번째"})

    response = client.get("/api/cards")
    cards = response.json()["cards"]
    assert [c["raw_text"] for c in cards] == ["두 번째", "첫 번째"]


def test_list_cards_filters_by_project_id(client, current_user_id):
    project_a = db.create_project(current_user_id, "A은행 차세대", "2023-02-01")
    project_b = db.create_project(current_user_id, "B카드 시스템", "2022-05-01")

    with patch("src.parsing.parser._call_llm", return_value=MOCK_LLM_RESPONSE):
        db.set_current_project(current_user_id, project_a)
        client.post("/api/cards", json={"raw_text": "A 카드"})
        db.set_current_project(current_user_id, project_b)
        client.post("/api/cards", json={"raw_text": "B 카드"})

    response = client.get(f"/api/cards?project_id={project_a}")
    cards = response.json()["cards"]
    assert len(cards) == 1
    assert cards[0]["raw_text"] == "A 카드"


def test_list_cards_never_returns_another_users_cards(client, current_user_id):
    """소유권 강제 — 다른 유저 카드가 이 유저의 목록에 섞이면 안 된다."""
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    db.save_card(
        other_user_id,
        None,
        ParsedEntry(raw_text="다른 유저 카드", refined_sentence="다른 유저 카드", skill_tags=[], confidence=0.5),
        "2023-02-14",
    )

    response = client.get("/api/cards")
    assert response.json() == {"cards": []}


def test_delete_card_returns_204_and_removes_it(client, current_user_id):
    with patch("src.parsing.parser._call_llm", return_value=MOCK_LLM_RESPONSE):
        created = client.post("/api/cards", json={"raw_text": "삭제될 카드"}).json()

    response = client.delete(f"/api/cards/{created['id']}")
    assert response.status_code == 204
    assert client.get("/api/cards").json()["cards"] == []


def test_delete_missing_card_still_returns_204(client, current_user_id):
    response = client.delete("/api/cards/9999")
    assert response.status_code == 204


def test_patch_card_tags_updates_skill_tags(client, current_user_id):
    """9/14 신규 — 카테고리(스킬 태그) 직접 수정. /stack에서 가끔 손으로 고치는 경로."""
    with patch("src.parsing.parser._call_llm", return_value=MOCK_LLM_RESPONSE):
        created = client.post("/api/cards", json={"raw_text": "결제 API 느려서 레디스 캐시 붙임"}).json()

    response = client.patch(f"/api/cards/{created['id']}", json={"skill_tags": ["결제/정산"]})

    assert response.status_code == 200
    assert response.json()["skill_tags"] == ["결제/정산"]
    # 재조회해도 반영돼야 한다.
    cards = client.get("/api/cards").json()["cards"]
    assert cards[0]["skill_tags"] == ["결제/정산"]


def test_patch_missing_card_tags_returns_404(client, current_user_id):
    response = client.patch("/api/cards/9999", json={"skill_tags": ["x"]})
    assert response.status_code == 404


def test_patch_card_sentence_only_leaves_tags_untouched(client, current_user_id):
    """9/15 신규 — 문장 직접 수정. skill_tags를 안 보내면 그대로 유지된다."""
    with patch("src.parsing.parser._call_llm", return_value=MOCK_LLM_RESPONSE):
        created = client.post("/api/cards", json={"raw_text": "결제 API 느려서 레디스 캐시 붙임"}).json()

    response = client.patch(f"/api/cards/{created['id']}", json={"refined_sentence": "사람이 직접 고친 문장"})

    assert response.status_code == 200
    assert response.json()["refined_sentence"] == "사람이 직접 고친 문장"
    assert response.json()["skill_tags"] == created["skill_tags"]


def test_patch_card_with_empty_body_returns_400(client, current_user_id):
    with patch("src.parsing.parser._call_llm", return_value=MOCK_LLM_RESPONSE):
        created = client.post("/api/cards", json={"raw_text": "결제 API 느려서 레디스 캐시 붙임"}).json()

    response = client.patch(f"/api/cards/{created['id']}", json={})

    assert response.status_code == 400


def test_create_card_llm_failure_falls_back_to_raw_text(client, current_user_id):
    """9/15 신규 — LLM 파싱이 실패해도 카드는 원문 그대로 저장돼야 한다(CLAUDE.md
    P0 "저장소 없으면 제품이 없다")."""
    with patch("src.parsing.parser._call_llm", side_effect=RuntimeError("LLM 타임아웃")):
        response = client.post("/api/cards", json={"raw_text": "결제 API 느려서 레디스 캐시 붙임"})

    assert response.status_code == 201
    body = response.json()
    assert body["refinement_failed"] is True
    assert body["raw_text"] == "결제 API 느려서 레디스 캐시 붙임"
    assert body["refined_sentence"] == "결제 API 느려서 레디스 캐시 붙임"
    assert body["skill_tags"] == []
    # 재조회해도 폴백 저장된 카드가 실제로 남아있어야 한다.
    cards = client.get("/api/cards").json()["cards"]
    assert len(cards) == 1


def test_create_card_success_has_refinement_failed_false(client, current_user_id):
    with patch("src.parsing.parser._call_llm", return_value=MOCK_LLM_RESPONSE):
        response = client.post("/api/cards", json={"raw_text": "결제 API 느려서 레디스 캐시 붙임"})

    assert response.json()["refinement_failed"] is False


def test_refine_card_endpoint_updates_fallback_card(client, current_user_id):
    """9/15 신규 — 폴백 저장된 카드를 다시 정리."""
    with patch("src.parsing.parser._call_llm", side_effect=RuntimeError("LLM 타임아웃")):
        created = client.post("/api/cards", json={"raw_text": "결제 API 느려서 레디스 캐시 붙임"}).json()
    assert created["refinement_failed"] is True

    with patch("src.parsing.parser._call_llm", return_value=MOCK_LLM_RESPONSE):
        response = client.post(f"/api/cards/{created['id']}/refine")

    assert response.status_code == 200
    body = response.json()
    assert body["refined_sentence"] == "결제 API 응답 지연을 해소하기 위해 Redis 캐싱 레이어를 도입했습니다."
    assert body["skill_tags"] == ["Redis", "성능최적화", "결제시스템"]


def test_refine_missing_card_returns_404(client, current_user_id):
    response = client.post("/api/cards/9999/refine")
    assert response.status_code == 404


def test_refine_another_users_card_returns_404(client, current_user_id):
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    other_card_id = db.save_card(
        other_user_id, None,
        ParsedEntry(raw_text="다른 유저 카드", refined_sentence="다른 유저 카드", skill_tags=[], confidence=0.0),
        "2023-02-14",
    )

    response = client.post(f"/api/cards/{other_card_id}/refine")

    assert response.status_code == 404


def test_patch_another_users_card_tags_returns_404(client, current_user_id):
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    other_card_id = db.save_card(
        other_user_id, None,
        ParsedEntry(raw_text="다른 유저 카드", refined_sentence="다른 유저 카드",
                    skill_tags=["Redis"], confidence=0.5),
        "2023-02-14",
    )

    response = client.patch(f"/api/cards/{other_card_id}", json={"skill_tags": ["가로채기"]})

    assert response.status_code == 404
    assert db.get_card(other_user_id, other_card_id).skill_tags == ["Redis"]


# --- GET /api/cards/unclassified/suggestions, POST /api/cards/bundle-into-project (9/14 신규) ---


def _unassigned_card(user_id: int, sentence: str, created_at="2023-02-14") -> int:
    return db.save_card(
        user_id, None,
        ParsedEntry(raw_text=sentence, refined_sentence=sentence, skill_tags=[], confidence=0.9),
        created_at,
    )


def test_get_unclassified_suggestions_requires_login(client):
    response = client.get("/api/cards/unclassified/suggestions")
    assert response.status_code == 401


def test_get_unclassified_suggestions_returns_empty_when_no_unassigned_cards(client, current_user_id):
    response = client.get("/api/cards/unclassified/suggestions")
    assert response.status_code == 200
    assert response.json() == {"clusters": []}


def test_get_unclassified_suggestions_never_includes_already_assigned_cards(client, current_user_id):
    """이미 프로젝트가 배정된 카드는 후보로도 안 뜬다 (CLAUDE.md 3장 안전장치)."""
    project_id = db.create_project(current_user_id, "A은행 차세대", "2023-02-01")
    db.save_card(
        current_user_id, project_id,
        ParsedEntry(raw_text="배정된 카드", refined_sentence="배정된 카드", skill_tags=[], confidence=0.9),
        "2023-02-14",
    )

    with patch(
        "src.agent.vectorstore._get_embedding_function",
        return_value=lambda input: [[1.0, 0.0, 0.0] for _ in input],
    ):
        response = client.get("/api/cards/unclassified/suggestions")

    assert response.json() == {"clusters": []}


def test_get_unclassified_suggestions_returns_clusters_with_full_card_info(client, current_user_id):
    id_a = _unassigned_card(current_user_id, "결제 API 캐싱 도입")
    id_b = _unassigned_card(current_user_id, "결제 API 캐싱 도입 후속")

    with patch(
        "src.agent.vectorstore._get_embedding_function",
        return_value=lambda input: [[1.0, 0.0, 0.0] for _ in input],  # 전부 동일 벡터 -> 무조건 유사
    ):
        response = client.get("/api/cards/unclassified/suggestions")

    assert response.status_code == 200
    clusters = response.json()["clusters"]
    assert len(clusters) == 1
    assert set(clusters[0]["card_ids"]) == {id_a, id_b}
    assert {c["refined_sentence"] for c in clusters[0]["cards"]} == {
        "결제 API 캐싱 도입",
        "결제 API 캐싱 도입 후속",
    }


def test_bundle_cards_into_project_requires_login(client):
    response = client.post(
        "/api/cards/bundle-into-project",
        json={"card_ids": [1], "name": "새 프로젝트", "started_at": "2023-02-01"},
    )
    assert response.status_code == 401


def test_bundle_cards_into_project_creates_project_and_moves_cards(client, current_user_id):
    id_a = _unassigned_card(current_user_id, "결제 API 캐싱 도입")
    id_b = _unassigned_card(current_user_id, "결제 API 캐싱 도입 후속")

    response = client.post(
        "/api/cards/bundle-into-project",
        json={"card_ids": [id_a, id_b], "name": "결제 API 개선 프로젝트", "started_at": "2023-02-14"},
    )

    assert response.status_code == 201
    project = response.json()
    assert project["name"] == "결제 API 개선 프로젝트"

    cards = client.get(f"/api/cards?project_id={project['id']}").json()["cards"]
    assert {c["id"] for c in cards} == {id_a, id_b}
    # 사용자가 직접 입력한 이름 그대로 저장됐다 — AI가 이름을 짓지 않는다(CLAUDE.md 2.2).
    assert db.list_unassigned_cards(current_user_id) == []


def test_bundle_cards_into_project_ignores_another_users_card_ids(client, current_user_id):
    """다른 유저 card_id를 섞어 보내도 그 카드만 조용히 무시되고, 내 카드는 정상 처리된다."""
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    other_card_id = _unassigned_card(other_user_id, "다른 유저 카드")
    my_card_id = _unassigned_card(current_user_id, "내 카드")

    response = client.post(
        "/api/cards/bundle-into-project",
        json={"card_ids": [my_card_id, other_card_id], "name": "새 프로젝트", "started_at": "2023-02-14"},
    )

    assert response.status_code == 201
    project_id = response.json()["id"]
    assert db.get_card(current_user_id, my_card_id).project_id == project_id
    assert db.get_card(other_user_id, other_card_id).project_id is None


# --- GET /api/cards/skill-summary (9/16 신규, Figma 100:692 홈 화면 버블 차트) ---


def test_skill_summary_requires_login(client):
    response = client.get("/api/cards/skill-summary", params={"project_id": 1})
    assert response.status_code == 401


def test_skill_summary_aggregates_by_representative_tag(client, current_user_id):
    project_id = db.create_project(current_user_id, "A은행 차세대", "2023-02-01")
    db.save_card(
        current_user_id,
        project_id,
        ParsedEntry(raw_text="a", refined_sentence="a", skill_tags=["Redis", "성능최적화"], confidence=0.9),
        "2023-02-14",
    )
    db.save_card(
        current_user_id,
        project_id,
        ParsedEntry(raw_text="b", refined_sentence="b", skill_tags=["Redis"], confidence=0.9),
        "2023-02-15",
    )

    response = client.get("/api/cards/skill-summary", params={"project_id": project_id})

    assert response.status_code == 200
    body = response.json()
    assert body["total_cards"] == 2
    assert body["categories"] == [{"tag": "Redis", "count": 2}]


def test_skill_summary_ignores_another_users_project(client, current_user_id):
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    other_project_id = db.create_project(other_user_id, "다른 유저 프로젝트", "2023-02-01")
    db.save_card(
        other_user_id,
        other_project_id,
        ParsedEntry(raw_text="x", refined_sentence="x", skill_tags=["Redis"], confidence=0.9),
        "2023-02-14",
    )

    response = client.get("/api/cards/skill-summary", params={"project_id": other_project_id})

    assert response.status_code == 200
    assert response.json() == {"total_cards": 0, "categories": []}
