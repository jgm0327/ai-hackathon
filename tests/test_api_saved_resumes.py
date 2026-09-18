"""Figma 4.3 "내 경력기술서 (저장본)" + 3.1-n "지금 채우기" — 9/18 신규.

저장본은 `resume_drafts`(작업 중 초안, 프로젝트당 1개 덮어쓰기)와 **별개 저장소**다.
그 구분이 실제로 지켜지는지가 여기서 검증할 핵심이다.
"""
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.parsing.parser import ParsedEntry
from src.storage import db

MOCK_LLM_RESPONSE = json.dumps(
    {
        "refined_sentence": "주간 회의에 참석해 일정을 공유했습니다.",
        "skill_tags": ["협업"],
        "confidence": 0.8,
        "case_summary": "",
    },
    ensure_ascii=False,
)
FILLED_LLM_RESPONSE = json.dumps(
    {
        "refined_sentence": "주간 회의에서 8명의 팀원과 일정을 공유했습니다.",
        "skill_tags": ["협업"],
        "confidence": 0.85,
        "case_summary": "",
    },
    ensure_ascii=False,
)


@pytest.fixture(autouse=True)
def _no_op_canonicalize(monkeypatch):
    monkeypatch.setattr("src.agent.pipeline.canonicalize_tags", lambda tags: tags)
    yield


@pytest.fixture
def client():
    return TestClient(app)


def _payload(**overrides) -> dict:
    base = {
        "title": "무신사 · 프로덕트 마케터",
        "content": "# 경력기술서\n\n내용",
        "item_count": 3,
        "card_count": 13,
        "jd_based": True,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 4.3 저장본
# ---------------------------------------------------------------------------


def test_saved_resumes_require_login(client):
    assert client.get("/api/resume/saved").status_code == 401
    assert client.post("/api/resume/saved", json=_payload()).status_code == 401


def test_create_and_list_saved_resume(client, current_user_id):
    created = client.post("/api/resume/saved", json=_payload())
    assert created.status_code == 201
    body = created.json()
    assert body["title"] == "무신사 · 프로덕트 마케터"
    assert body["item_count"] == 3
    assert body["card_count"] == 13
    assert body["jd_based"] is True

    listed = client.get("/api/resume/saved").json()["resumes"]
    assert [r["id"] for r in listed] == [body["id"]]
    # 목록엔 본문을 싣지 않는다 — 저장본이 여럿이면 응답이 통째로 무거워진다.
    assert "content" not in listed[0]


def test_saved_resume_detail_includes_content(client, current_user_id):
    saved_id = client.post("/api/resume/saved", json=_payload()).json()["id"]
    body = client.get(f"/api/resume/saved/{saved_id}").json()
    assert body["content"] == "# 경력기술서\n\n내용"


def test_saved_resumes_are_kept_side_by_side(client, current_user_id):
    """공고마다 다르게 쓴 버전을 나란히 두는 게 이 기능의 존재 이유다 — 덮어쓰지 않는다."""
    client.post("/api/resume/saved", json=_payload(title="무신사 · 프로덕트 마케터"))
    client.post("/api/resume/saved", json=_payload(title="마스터 버전", jd_based=False))

    listed = client.get("/api/resume/saved").json()["resumes"]
    assert {r["title"] for r in listed} == {"무신사 · 프로덕트 마케터", "마스터 버전"}


def test_saved_resume_is_separate_from_working_draft(client, current_user_id):
    """`resume_drafts`(작업 중 초안)와 서로 영향을 주지 않아야 한다."""
    project_id = db.create_project(current_user_id, "A은행", "2026-02-01")
    client.put("/api/resume/draft", json={"project_id": project_id, "content": "작업 중 초안"})
    client.post("/api/resume/saved", json=_payload(content="저장본 본문"))

    draft = client.get(f"/api/resume/draft?project_id={project_id}").json()
    assert draft["content"] == "작업 중 초안"
    saved = client.get("/api/resume/saved").json()["resumes"]
    assert len(saved) == 1


def test_draft_count_reports_saved_resumes(client, current_user_id):
    """Figma 4.1-h "내 경력기술서  N개"는 4.3 목록과 같은 수를 보여야 한다."""
    assert client.get("/api/resume/draft-count").json()["count"] == 0
    client.post("/api/resume/saved", json=_payload())
    client.post("/api/resume/saved", json=_payload(title="마스터 버전"))
    assert client.get("/api/resume/draft-count").json()["count"] == 2


def test_delete_saved_resume(client, current_user_id):
    saved_id = client.post("/api/resume/saved", json=_payload()).json()["id"]
    assert client.delete(f"/api/resume/saved/{saved_id}").status_code == 204
    assert client.get("/api/resume/saved").json()["resumes"] == []


def test_delete_saved_resume_is_idempotent(client, current_user_id):
    assert client.delete("/api/resume/saved/9999").status_code == 204


def test_unknown_saved_resume_returns_404(client, current_user_id):
    assert client.get("/api/resume/saved/9999").status_code == 404


def test_other_users_saved_resume_is_not_visible(client, current_user_id):
    saved_id = client.post("/api/resume/saved", json=_payload()).json()["id"]
    other = db.upsert_user("other-kakao", "남", None, "2026-09-18T00:00:00+09:00")
    assert db.get_saved_resume(other, saved_id) is None
    assert db.list_saved_resumes(other) == []


# ---------------------------------------------------------------------------
# 3.1-n 지금 채우기
# ---------------------------------------------------------------------------


def _create_card(client) -> dict:
    with patch("src.parsing.parser._call_llm", return_value=MOCK_LLM_RESPONSE):
        return client.post("/api/cards", json={"raw_text": "주간 회의 들어감"}).json()


def test_metric_answer_appends_to_raw_text_and_rebuilds_sentence(client, current_user_id):
    """답한 값은 원문에 붙는다 — 나중에 재파싱해도 그 숫자가 살아남아야 한다."""
    card = _create_card(client)
    with patch("src.parsing.parser._call_llm", return_value=FILLED_LLM_RESPONSE):
        body = client.post(
            f"/api/cards/{card['id']}/metric-answer", json={"answer": "참석자 8명"}
        ).json()

    assert "참석자 8명" in body["raw_text"]
    assert body["refined_sentence"] == "주간 회의에서 8명의 팀원과 일정을 공유했습니다."


def test_metric_answer_keeps_manually_edited_sentence(client, current_user_id):
    """3.1-d "직접 고친 문장은 다시 변환해도 유지돼요"는 이 경로에도 적용된다."""
    card = _create_card(client)
    client.patch(f"/api/cards/{card['id']}", json={"refined_sentence": "내가 고친 문장"})

    with patch("src.parsing.parser._call_llm", return_value=FILLED_LLM_RESPONSE):
        body = client.post(
            f"/api/cards/{card['id']}/metric-answer", json={"answer": "참석자 8명"}
        ).json()

    assert body["refined_sentence"] == "내가 고친 문장"
    assert body["ai_sentence"] == "주간 회의에서 8명의 팀원과 일정을 공유했습니다."


def test_metric_answer_on_unknown_card_returns_404(client, current_user_id):
    response = client.post("/api/cards/9999/metric-answer", json={"answer": "3.2%p"})
    assert response.status_code == 404


def test_metric_answer_rejects_empty_answer(client, current_user_id):
    card = _create_card(client)
    response = client.post(f"/api/cards/{card['id']}/metric-answer", json={"answer": ""})
    assert response.status_code == 422


def test_metric_answer_does_not_call_llm_for_blank_answer(current_user_id):
    """공백만 온 경우 — 라우터가 422로 막지만, 파이프라인 자체도 LLM을 안 부른다."""
    from src.agent.pipeline import add_metric_answer

    card_id = db.save_card(
        current_user_id,
        None,
        ParsedEntry(raw_text="회의", refined_sentence="회의에 참석함", skill_tags=[], confidence=0.8),
        "2026-09-18",
    )
    with patch("src.parsing.parser._call_llm") as mock_llm:
        card = add_metric_answer(current_user_id, card_id, "   ")

    mock_llm.assert_not_called()
    assert card.refined_sentence == "회의에 참석함"
