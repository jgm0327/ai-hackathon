"""운영 보호장치 테스트 (9/17 신규) — 입력 길이 상한 / 레이트 리밋 / 본문 크기 제한.

이 셋은 전부 "정상 사용에는 안 보이고 남용에만 걸리는" 장치라, 회귀가 나도 기능
테스트로는 안 잡힌다(오히려 장치가 사라져야 테스트가 더 잘 통과한다). 그래서 별도
파일로 두고 "막혀야 할 게 실제로 막히는지"를 직접 검증한다.

가장 중요한 성질은 **LLM이 호출되기 전에 막히는가**다 — 422/429를 받아도 그 전에
Anthropic을 한 번 부르고 나면 비용은 이미 나간 것이므로, 아래 테스트들은 상태 코드뿐
아니라 `_call_llm`이 호출되지 않았다는 것까지 확인한다.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api import rate_limit
from src.api.main import MAX_REQUEST_BYTES, app
from src.api.schemas import MAX_JD_TEXT, MAX_RAW_TEXT
from src.storage import db


@pytest.fixture
def client():
    return TestClient(app)


# --- 1. 입력 길이 상한 (schemas.py) ---


def test_raw_text_over_limit_rejected_before_llm(client, current_user_id):
    """긴 메모는 422로 끊기고, parse_note()의 LLM 호출까지 가지 않아야 한다."""
    with patch("src.parsing.parser._call_llm") as mock_llm:
        response = client.post("/api/cards", json={"raw_text": "가" * (MAX_RAW_TEXT + 1)})

    assert response.status_code == 422
    mock_llm.assert_not_called()


def test_raw_text_at_limit_is_accepted(client, current_user_id):
    """상한 '이하'는 정상 통과해야 한다 — 경계에서 정상 사용을 막으면 안 된다."""
    with patch("src.parsing.parser._call_llm", return_value='{"refined_sentence": "정리된 문장", "skill_tags": [], "confidence": 0.9, "case_summary": ""}'):
        response = client.post("/api/cards", json={"raw_text": "가" * MAX_RAW_TEXT})

    assert response.status_code == 201


@pytest.mark.parametrize("empty", ["", "   ", "\n\t "])
def test_blank_raw_text_rejected_before_llm(client, current_user_id, empty):
    """빈/공백뿐인 메모는 정리할 내용이 없으니 LLM을 부르지 않는다.

    9/17 실측: 이전엔 `{"raw_text": ""}`가 201로 통과해 LLM을 한 번 부르고 내용
    없는 카드까지 만들었다.
    """
    with patch("src.parsing.parser._call_llm") as mock_llm:
        response = client.post("/api/cards", json={"raw_text": empty})

    assert response.status_code == 422
    mock_llm.assert_not_called()


def test_jd_text_over_limit_rejected_before_llm(client, current_user_id):
    project_id = db.create_project(current_user_id, "A은행", "2023-02-01")

    with patch("src.parsing.resume._call_llm") as mock_llm:
        response = client.post(
            "/api/resume",
            json={"project_id": project_id, "jd_text": "가" * (MAX_JD_TEXT + 1)},
        )

    assert response.status_code == 422
    mock_llm.assert_not_called()


def test_enhance_rejects_overlong_single_item(client, current_user_id):
    """개수(10개)는 지켜도 항목 하나가 과도하게 길면 막아야 한다 —
    개수만 세면 '10개 × 각 1MB'가 그대로 통과한다."""
    project_id = db.create_project(current_user_id, "A은행", "2023-02-01")

    with patch("src.parsing.resume._call_llm") as mock_llm:
        response = client.post(
            "/api/resume/enhance",
            json={"project_id": project_id, "existing_items": ["가" * 5_000]},
        )

    assert response.status_code == 422
    mock_llm.assert_not_called()


def test_star_item_payload_rejects_overlong_field(client, current_user_id):
    """역질문 경로는 StarItem을 통째로 body로 받으므로 각 필드도 막혀 있어야 한다."""
    payload = {
        "title": "제목",
        "period": "02.14",
        "situation": "가" * 10_000,
        "task": "t",
        "action": "a",
        "result": "r",
    }
    with patch("src.parsing.resume._call_llm") as mock_llm:
        response = client.post("/api/resume/star-questions", json={"item": payload})

    assert response.status_code == 422
    mock_llm.assert_not_called()


# --- 2. 노션 (routers/notion.py) ---
#
# 9/18 — "배치 상한" 테스트는 대량 가져오기(`POST /api/notion/sync`)와 함께 사라졌다.
# 상한이 필요했던 이유가 "한 번 눌렀을 때 LLM을 수십 번 부른다"였는데, 이제 노션
# 경로는 LLM을 아예 부르지 않는다(목록 조회 + 페이지 하나 본문 조회뿐). 남은 검증은
# `tests/test_api_notion.py`에 있다.


# --- 3. 레이트 리밋 (rate_limit.py) ---


def test_heavy_endpoint_blocks_after_limit(client, current_user_id):
    """Sonnet 경로는 분당 LIMIT_HEAVY회를 넘으면 429."""
    project_id = db.create_project(current_user_id, "빈 프로젝트", "2023-02-01")

    # 카드가 없으면 build_resume()이 LLM 없이 빈 목록을 반환하므로, 리밋만 순수하게 센다.
    for _ in range(rate_limit.LIMIT_HEAVY):
        assert client.post("/api/resume", json={"project_id": project_id}).status_code == 200

    blocked = client.post("/api/resume", json={"project_id": project_id})
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_rate_limit_is_per_user_not_global(client, current_user_id):
    """한 유저가 리밋에 걸려도 다른 유저는 멀쩡해야 한다."""
    project_id = db.create_project(current_user_id, "빈 프로젝트", "2023-02-01")
    for _ in range(rate_limit.LIMIT_HEAVY):
        client.post("/api/resume", json={"project_id": project_id})
    assert client.post("/api/resume", json={"project_id": project_id}).status_code == 429

    # 다른 유저로 갈아끼운다 (conftest의 override를 이 테스트 안에서만 교체).
    from src.auth.deps import get_current_user

    other_id = db.upsert_user("other-kakao", "다른유저", None, "2026-01-01T00:00:00")
    app.dependency_overrides[get_current_user] = lambda: db.get_user(other_id)
    other_project = db.create_project(other_id, "다른 프로젝트", "2023-02-01")

    assert client.post("/api/resume", json={"project_id": other_project}).status_code == 200


def test_light_and_heavy_buckets_are_independent(client, current_user_id):
    """메모 입력(light)을 많이 썼다고 경력기술서(heavy)가 막히면 안 된다."""
    parsed = '{"refined_sentence": "정리", "skill_tags": [], "confidence": 0.9, "case_summary": ""}'
    with patch("src.parsing.parser._call_llm", return_value=parsed):
        for _ in range(rate_limit.LIMIT_HEAVY + 1):
            client.post("/api/cards", json={"raw_text": "메모"})

    project_id = db.create_project(current_user_id, "빈 프로젝트", "2023-02-01")
    assert client.post("/api/resume", json={"project_id": project_id}).status_code == 200


# --- 4. 본문 크기 제한 (main.py 미들웨어) ---


def test_oversized_body_rejected_with_413(client, current_user_id):
    """Content-Length만 보고 본문을 읽기 전에 끊는다 — Pydantic 검증보다 앞선 방어선."""
    huge = "가" * (MAX_REQUEST_BYTES + 1024)
    response = client.post("/api/cards", json={"raw_text": huge})

    assert response.status_code == 413
    assert response.json()["detail"] == "요청 본문이 너무 큽니다."
