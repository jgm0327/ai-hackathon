"""Figma "03 · 커리어 스택 · Tab B"(`294:9924`)가 들여온 백엔드 동작 — 9/18 신규.

두 가지를 다룬다:
  - 4.1-i "분류 수정" — `GET /api/cards/tag-suggestions` (임베딩 기반, LLM 아님)
  - 4.1-j "이 역량으로 문장 만들기" — `POST /api/resume`의 `skill_tag`

사진은 `test_api_photos.py`가 담당한다.
"""
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.agent.pipeline import cards_with_skill_tag
from src.api.main import app
from src.storage import db


@pytest.fixture
def client():
    return TestClient(app)


def _save_card(user_id: int, sentence: str, tags: list[str], created_at: str) -> int:
    """LLM/임베딩을 타지 않고 카드를 직접 넣는다 — 여기서 검증할 건 API 쪽이다."""
    from src.parsing.parser import ParsedEntry

    return db.save_card(
        user_id,
        None,
        ParsedEntry(raw_text=sentence, refined_sentence=sentence, skill_tags=tags, confidence=0.9),
        created_at,
    )


# ---------------------------------------------------------------------------
# 4.1-i 분류 수정 — 역량 추천
# ---------------------------------------------------------------------------


def test_tag_suggestions_requires_login(client):
    assert client.get("/api/cards/tag-suggestions").status_code == 401


def test_tag_suggestions_only_covers_cards_without_tags(client, current_user_id):
    tagged = _save_card(current_user_id, "캠페인 성과를 정리했습니다", ["캠페인 운영"], "2026-09-10")
    untagged = _save_card(current_user_id, "블로그 유입 키워드를 다시 짰습니다", [], "2026-09-11")

    with patch(
        "src.agent.tag_suggester.vectorstore._get_embedding_function",
        return_value=lambda docs: [[float(len(d)), 1.0] for d in docs],
    ):
        body = client.get("/api/cards/tag-suggestions").json()

    assert [s["card_id"] for s in body["suggestions"]] == [untagged]
    assert tagged not in [s["card_id"] for s in body["suggestions"]]


def test_tag_suggestions_only_offers_existing_tags(client, current_user_id):
    """없는 역량을 지어내지 않는다 — 후보는 이 유저가 이미 가진 역량뿐이다."""
    _save_card(current_user_id, "캠페인 성과 정리", ["캠페인 운영"], "2026-09-10")
    _save_card(current_user_id, "콘텐츠 일정 정리", ["콘텐츠 기획"], "2026-09-10")
    _save_card(current_user_id, "블로그 유입 키워드 재정리", [], "2026-09-11")

    with patch(
        "src.agent.tag_suggester.vectorstore._get_embedding_function",
        return_value=lambda docs: [[float(len(d)), 1.0] for d in docs],
    ):
        body = client.get("/api/cards/tag-suggestions").json()

    assert set(body["known_tags"]) == {"캠페인 운영", "콘텐츠 기획"}
    for suggestion in body["suggestions"]:
        assert set(suggestion["suggested_tags"]) <= set(body["known_tags"])


def test_tag_suggestions_are_empty_when_no_tags_exist_yet(client, current_user_id):
    """역량이 하나도 없는 계정에선 추천할 것이 없다 — 화면은 "직접 추가"만 남는다."""
    _save_card(current_user_id, "블로그 유입 키워드 재정리", [], "2026-09-11")

    body = client.get("/api/cards/tag-suggestions").json()
    assert body["suggestions"] == []
    assert body["known_tags"] == []


def test_tag_suggestions_return_502_when_embedding_fails(client, current_user_id):
    _save_card(current_user_id, "캠페인 성과 정리", ["캠페인 운영"], "2026-09-10")
    _save_card(current_user_id, "블로그 유입 키워드 재정리", [], "2026-09-11")

    with patch(
        "src.agent.tag_suggester.vectorstore._get_embedding_function",
        side_effect=RuntimeError("boom"),
    ):
        assert client.get("/api/cards/tag-suggestions").status_code == 502


def test_tag_suggestions_include_the_card_itself(client, current_user_id):
    """화면(4.1-i)이 원문과 날짜를 같이 보여주므로 카드 전체가 실려 와야 한다."""
    _save_card(current_user_id, "캠페인 성과 정리", ["캠페인 운영"], "2026-09-10")
    _save_card(current_user_id, "블로그 유입 키워드 재정리", [], "2026-09-11")

    with patch(
        "src.agent.tag_suggester.vectorstore._get_embedding_function",
        return_value=lambda docs: [[float(len(d)), 1.0] for d in docs],
    ):
        body = client.get("/api/cards/tag-suggestions").json()

    assert body["suggestions"][0]["card"]["refined_sentence"] == "블로그 유입 키워드 재정리"


# ---------------------------------------------------------------------------
# 4.1-j 역량 상세 — 역량 기준 카드 선별
# ---------------------------------------------------------------------------


def test_cards_with_skill_tag_matches_representative_tag_only(current_user_id):
    """대표 태그(skill_tags[0])로만 판정한다 — 역량 목록의 개수와 정확히 맞아야 한다."""

    def card(tags):
        return db.Card(
            id=1, project_id=None, raw_text="x", refined_sentence="x",
            skill_tags=tags, confidence=0.9, created_at="2026-09-10",
        )

    cards = [card(["캠페인 운영", "콘텐츠 기획"]), card(["콘텐츠 기획", "캠페인 운영"]), card([])]

    # 두 번째 카드는 "캠페인 운영"을 가지고 있지만 대표 태그가 아니므로 안 잡힌다.
    assert len(cards_with_skill_tag(cards, "캠페인 운영")) == 1
    assert len(cards_with_skill_tag(cards, "콘텐츠 기획")) == 1
    assert len(cards_with_skill_tag(cards, "미분류")) == 1


def test_resume_with_skill_tag_only_uses_that_competency(client, current_user_id):
    """Figma 4.1-j "이 역량으로 문장 만들기"."""
    project_id = db.create_project(current_user_id, "A은행", "2026-02-01")
    db.set_current_project(current_user_id, project_id)
    from src.parsing.parser import ParsedEntry

    for sentence, tags in [
        ("가입 배너 A/B 테스트를 돌렸습니다", ["캠페인 운영"]),
        ("블로그 카테고리를 재편했습니다", ["콘텐츠 기획"]),
    ]:
        db.save_card(
            current_user_id,
            project_id,
            ParsedEntry(raw_text=sentence, refined_sentence=sentence, skill_tags=tags, confidence=0.9),
            "2026-09-10",
        )

    seen: list[list[str]] = []

    def fake_build_resume(cards, jd_text=None):
        seen.append([c.refined_sentence for c in cards])
        return []

    with patch("src.agent.pipeline.build_resume", side_effect=fake_build_resume):
        response = client.post(
            "/api/resume", json={"project_ids": [project_id], "skill_tag": "캠페인 운영"}
        )

    assert response.status_code == 200
    assert seen == [["가입 배너 A/B 테스트를 돌렸습니다"]]


def test_resume_keeps_project_boundaries_with_skill_tag(client, current_user_id):
    """같은 역량이라도 프로젝트가 다르면 따로 묶는다 (CLAUDE.md 3장 / 9/18 사용자 확정)."""
    from src.parsing.parser import ParsedEntry

    a = db.create_project(current_user_id, "A은행", "2026-02-01")
    b = db.create_project(current_user_id, "B카드", "2026-05-01")
    for pid, sentence in [(a, "A은행 결제 API 개선"), (b, "B카드 결제 API 개선")]:
        db.save_card(
            current_user_id,
            pid,
            ParsedEntry(raw_text=sentence, refined_sentence=sentence, skill_tags=["결제"], confidence=0.9),
            "2026-09-10",
        )

    calls: list[list[str]] = []

    def fake_build_resume(cards, jd_text=None):
        calls.append([c.refined_sentence for c in cards])
        return []

    with patch("src.agent.pipeline.build_resume", side_effect=fake_build_resume):
        client.post("/api/resume", json={"project_ids": [a, b], "skill_tag": "결제"})

    # 한 덩어리로 합쳐 부르면 경력이 반으로 줄어든다 — 반드시 프로젝트마다 따로.
    assert calls == [["A은행 결제 API 개선"], ["B카드 결제 API 개선"]]


def test_resume_without_skill_tag_is_unchanged(client, current_user_id):
    from src.parsing.parser import ParsedEntry

    project_id = db.create_project(current_user_id, "A은행", "2026-02-01")
    for sentence, tags in [("문장1", ["캠페인 운영"]), ("문장2", ["콘텐츠 기획"])]:
        db.save_card(
            current_user_id,
            project_id,
            ParsedEntry(raw_text=sentence, refined_sentence=sentence, skill_tags=tags, confidence=0.9),
            "2026-09-10",
        )

    seen: list[list[str]] = []

    def fake_build_resume(cards, jd_text=None):
        seen.append([c.refined_sentence for c in cards])
        return []

    with patch("src.agent.pipeline.build_resume", side_effect=fake_build_resume):
        client.post("/api/resume", json={"project_ids": [project_id]})

    assert seen == [["문장1", "문장2"]]


def test_list_skill_tags_is_ordered_by_usage(current_user_id):
    _save_card(current_user_id, "a", ["캠페인 운영"], "2026-09-10")
    _save_card(current_user_id, "b", ["캠페인 운영", "콘텐츠 기획"], "2026-09-11")

    assert db.list_skill_tags(current_user_id) == ["캠페인 운영", "콘텐츠 기획"]
