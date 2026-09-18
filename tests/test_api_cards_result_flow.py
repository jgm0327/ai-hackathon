"""Figma "02 · 변환 결과" 섹션(`286:7123`)이 들여온 카드 API 동작 — 9/18 신규.

세 가지를 다룬다:
  - 3.1-q "변환 전 추가 질문" — `POST /api/cards/metric-question` + `metric_answer`
  - 3.1-d "결과 문장 직접 수정" — 직접 고친 문장 유지 / AI 문장으로 되돌리기
  - 3.1-b·3.1-c "직무 전환 번역" — `POST /api/cards/{id}/translate`

기본 카드 CRUD는 `test_api_cards.py`가 담당한다. DB 격리와 로그인 유저 오버라이드는
`tests/conftest.py`의 `_isolated_db`(autouse)/`current_user_id` 픽스처가 맡는다.
"""
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.storage import db

MOCK_LLM_RESPONSE = json.dumps(
    {
        "refined_sentence": "결제 API 응답 지연을 해소하기 위해 Redis 캐싱 레이어를 도입했습니다.",
        "skill_tags": ["Redis", "성능최적화"],
        "confidence": 0.91,
        "case_summary": "오늘 기록은 결제 API 성능 개선 케이스입니다.",
    },
    ensure_ascii=False,
)
REFINED_AGAIN_RESPONSE = json.dumps(
    {
        "refined_sentence": "AI가 새로 만든 문장",
        "skill_tags": ["Redis"],
        "confidence": 0.8,
        "case_summary": "",
    },
    ensure_ascii=False,
)

METRIC_QUESTION_RESPONSE = json.dumps(
    {"question": "전환율이 얼마나 올랐나요?", "placeholder": "예: 3.2%p, 12% → 15.2%"},
    ensure_ascii=False,
)
NO_METRIC_QUESTION_RESPONSE = json.dumps({"question": None, "placeholder": None})

TRANSLATION_RESPONSE = json.dumps(
    {
        "related": True,
        "headline": "오늘 하신 캐싱 작업은 UX 성능 개선으로 읽힙니다.",
        "translated_sentence": "체감 응답 속도를 개선하기 위해 캐싱 레이어를 도입했습니다.",
        "suggestion": "",
    },
    ensure_ascii=False,
)
UNRELATED_TRANSLATION_RESPONSE = json.dumps(
    {
        "related": False,
        "headline": "오늘 하신 일정 정리는 UX/UI 경험으로 읽기는 어려워요.",
        "translated_sentence": "인스타 발행 일정을 정리하고 담당자를 배정했습니다.",
        "suggestion": "리서치나 구조 설계, 실험을 기록하면 UX/UI와 가까워져요",
    },
    ensure_ascii=False,
)


@pytest.fixture(autouse=True)
def _no_op_canonicalize(monkeypatch):
    """태그 캐노니컬라이제이션(임베딩/Chroma)은 `test_tag_canonicalizer.py`가 검증한다."""
    monkeypatch.setattr("src.agent.pipeline.canonicalize_tags", lambda tags: tags)
    yield


@pytest.fixture
def client():
    return TestClient(app)


def _create_card(client) -> dict:
    with patch("src.parsing.parser._call_llm", return_value=MOCK_LLM_RESPONSE):
        return client.post(
            "/api/cards", json={"raw_text": "결제 API 느려서 레디스 캐시 붙임"}
        ).json()


# ---------------------------------------------------------------------------
# 3.1-q 변환 전 추가 질문
# ---------------------------------------------------------------------------


def test_metric_question_requires_login(client):
    response = client.post("/api/cards/metric-question", json={"raw_text": "배너 테스트"})
    assert response.status_code == 401


def test_metric_question_returns_question_when_number_is_missing(client, current_user_id):
    with patch("src.parsing.parser._call_llm_with", return_value=METRIC_QUESTION_RESPONSE):
        response = client.post(
            "/api/cards/metric-question", json={"raw_text": "배너 A/B 테스트 돌림"}
        )

    assert response.status_code == 200
    assert response.json() == {
        "question": "전환율이 얼마나 올랐나요?",
        "placeholder": "예: 3.2%p, 12% → 15.2%",
    }


def test_metric_question_returns_empty_when_nothing_to_ask(client, current_user_id):
    """빈 문자열 = "물어볼 게 없다" — 프론트가 화면을 건너뛴다 (CLAUDE.md 2.1)."""
    with patch("src.parsing.parser._call_llm_with", return_value=NO_METRIC_QUESTION_RESPONSE):
        response = client.post("/api/cards/metric-question", json={"raw_text": "주간 회의 참석"})

    assert response.status_code == 200
    assert response.json() == {"question": "", "placeholder": ""}


def test_metric_question_swallows_llm_failure(client, current_user_id):
    """판정이 실패해도 입력 흐름이 막히면 안 된다 — 질문 없이 진행할 수 있어야 한다."""
    with patch("src.parsing.parser._call_llm_with", side_effect=RuntimeError("boom")):
        response = client.post("/api/cards/metric-question", json={"raw_text": "배너 테스트"})

    assert response.status_code == 200
    assert response.json()["question"] == ""


def test_metric_question_does_not_create_a_card(client, current_user_id):
    with patch("src.parsing.parser._call_llm_with", return_value=METRIC_QUESTION_RESPONSE):
        client.post("/api/cards/metric-question", json={"raw_text": "배너 A/B 테스트 돌림"})

    assert client.get("/api/cards").json()["cards"] == []


def test_create_card_appends_metric_answer_to_raw_text(client, current_user_id):
    """유저가 **직접 답한** 값만 들어간다 — 서버가 숫자를 만들지 않는다 (CLAUDE.md 2.2)."""
    with patch("src.parsing.parser._call_llm", return_value=MOCK_LLM_RESPONSE) as mock_llm:
        response = client.post(
            "/api/cards",
            json={"raw_text": "배너 A/B 테스트 돌림", "metric_answer": "3.2%p"},
        )

    assert response.status_code == 201
    assert "3.2%p" in response.json()["raw_text"]
    # LLM에도 그 값이 함께 넘어가야 문장에 반영된다.
    assert "3.2%p" in mock_llm.call_args.args[0]


def test_create_card_without_metric_answer_is_unchanged(client, current_user_id):
    with patch("src.parsing.parser._call_llm", return_value=MOCK_LLM_RESPONSE):
        response = client.post("/api/cards", json={"raw_text": "배너 A/B 테스트 돌림"})

    assert response.json()["raw_text"] == "배너 A/B 테스트 돌림"


# ---------------------------------------------------------------------------
# 3.1-d 문장 직접 수정 / AI 문장 되돌리기
# ---------------------------------------------------------------------------


def test_created_card_keeps_ai_sentence_and_is_not_marked_edited(client, current_user_id):
    card = _create_card(client)
    assert card["ai_sentence"] == card["refined_sentence"]
    assert card["sentence_edited"] is False


def test_editing_sentence_marks_card_as_edited_and_keeps_ai_sentence(client, current_user_id):
    card = _create_card(client)
    body = client.patch(
        f"/api/cards/{card['id']}", json={"refined_sentence": "내가 고친 문장"}
    ).json()

    assert body["refined_sentence"] == "내가 고친 문장"
    assert body["sentence_edited"] is True
    assert body["ai_sentence"] == card["refined_sentence"]


def test_editing_only_tags_does_not_mark_sentence_as_edited(client, current_user_id):
    card = _create_card(client)
    body = client.patch(f"/api/cards/{card['id']}", json={"skill_tags": ["Redis"]}).json()
    assert body["sentence_edited"] is False


def test_refine_keeps_manually_edited_sentence(client, current_user_id):
    """Figma 3.1-d "직접 고친 문장은 다시 변환해도 유지돼요"."""
    card = _create_card(client)
    client.patch(f"/api/cards/{card['id']}", json={"refined_sentence": "내가 고친 문장"})

    with patch("src.parsing.parser._call_llm", return_value=REFINED_AGAIN_RESPONSE):
        body = client.post(f"/api/cards/{card['id']}/refine").json()

    assert body["refined_sentence"] == "내가 고친 문장"  # 사람 문장은 그대로
    assert body["ai_sentence"] == "AI가 새로 만든 문장"  # 되돌릴 대상만 최신화


def test_refine_replaces_sentence_when_not_edited(client, current_user_id):
    card = _create_card(client)
    with patch("src.parsing.parser._call_llm", return_value=REFINED_AGAIN_RESPONSE):
        body = client.post(f"/api/cards/{card['id']}/refine").json()

    assert body["refined_sentence"] == "AI가 새로 만든 문장"


def test_revert_to_ai_restores_ai_sentence(client, current_user_id):
    card = _create_card(client)
    client.patch(f"/api/cards/{card['id']}", json={"refined_sentence": "내가 고친 문장"})

    body = client.patch(f"/api/cards/{card['id']}", json={"revert_to_ai": True}).json()
    assert body["refined_sentence"] == card["refined_sentence"]
    assert body["sentence_edited"] is False


def test_revert_to_ai_after_refine_gives_the_newest_ai_sentence(client, current_user_id):
    """되돌리기는 **가장 최근** AI 문장으로 간다 — 옛날 문장으로 가면 기대와 어긋난다."""
    card = _create_card(client)
    client.patch(f"/api/cards/{card['id']}", json={"refined_sentence": "내가 고친 문장"})
    with patch("src.parsing.parser._call_llm", return_value=REFINED_AGAIN_RESPONSE):
        client.post(f"/api/cards/{card['id']}/refine")

    body = client.patch(f"/api/cards/{card['id']}", json={"revert_to_ai": True}).json()
    assert body["refined_sentence"] == "AI가 새로 만든 문장"


def test_patch_without_any_field_is_rejected(client, current_user_id):
    card = _create_card(client)
    assert client.patch(f"/api/cards/{card['id']}", json={}).status_code == 400


# ---------------------------------------------------------------------------
# 3.1-b / 3.1-c 직무 전환 번역
# ---------------------------------------------------------------------------


def test_translate_returns_target_job_reading(client, current_user_id):
    card = _create_card(client)
    with patch("src.parsing.parser._call_llm_with", return_value=TRANSLATION_RESPONSE):
        response = client.post(f"/api/cards/{card['id']}/translate", json={"target_job": "UX/UI"})

    assert response.status_code == 200
    body = response.json()
    assert body["related"] is True
    assert body["translated_sentence"] == "체감 응답 속도를 개선하기 위해 캐싱 레이어를 도입했습니다."
    assert body["suggestion"] == ""


def test_translate_reports_no_overlap_with_a_suggestion(client, current_user_id):
    """Figma 3.1-c — 접점이 없으면 억지로 갖다 붙이지 않는다."""
    card = _create_card(client)
    with patch("src.parsing.parser._call_llm_with", return_value=UNRELATED_TRANSLATION_RESPONSE):
        body = client.post(
            f"/api/cards/{card['id']}/translate", json={"target_job": "UX/UI"}
        ).json()

    assert body["related"] is False
    assert body["suggestion"] == "리서치나 구조 설계, 실험을 기록하면 UX/UI와 가까워져요"


def test_translate_does_not_persist_anything(client, current_user_id):
    """번역 결과는 저장하지 않는다 (CLAUDE.md 3장 "AI가 만드는 묶음은 저장 안 함"과 같은 판단)."""
    card = _create_card(client)
    with patch("src.parsing.parser._call_llm_with", return_value=TRANSLATION_RESPONSE):
        client.post(f"/api/cards/{card['id']}/translate", json={"target_job": "UX/UI"})

    stored = db.get_card(current_user_id, card["id"])
    assert stored.refined_sentence == card["refined_sentence"]


def test_translate_returns_404_for_unknown_card(client, current_user_id):
    response = client.post("/api/cards/9999/translate", json={"target_job": "UX/UI"})
    assert response.status_code == 404


def test_translate_returns_502_when_llm_fails(client, current_user_id):
    card = _create_card(client)
    with patch("src.parsing.parser._call_llm_with", side_effect=RuntimeError("boom")):
        response = client.post(f"/api/cards/{card['id']}/translate", json={"target_job": "UX/UI"})

    assert response.status_code == 502
