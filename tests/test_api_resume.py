"""Track B 담당: POST /api/resume 테스트 ★ 핵심 경로.

build_resume()의 LLM 호출부를 모킹해서 실제 API 호출 없이 build_career_doc() ->
build_resume() 오케스트레이션과 응답 스키마 변환을 검증한다.
"""
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.parsing.parser import ParsedEntry
from src.storage import db


@pytest.fixture(autouse=True)
def _isolated_db(monkeypatch, tmp_path):
    class _FakeSettings:
        db_path = str(tmp_path / "test.db")

    monkeypatch.setattr(db, "settings", _FakeSettings())
    yield


@pytest.fixture
def client():
    return TestClient(app)


def _seed_cards(project_id: int) -> None:
    db.save_card(
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
                "source_dates": ["02.14", "03.02"],
            }
        ]
    },
    ensure_ascii=False,
)


def test_create_resume_merges_time_gap_pair(client):
    project_id = db.create_project("A은행 차세대", "2023-02-01")
    _seed_cards(project_id)

    with patch("src.parsing.resume._call_llm", return_value=_MOCK_LLM_RESPONSE):
        response = client.post("/api/resume", json={"project_id": project_id})

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["title"] == "결제 API 성능 개선"
    assert item["result"] == "결제 오류율을 0.8%에서 0.3%로 낮췄습니다."
    assert item["source_dates"] == ["02.14", "03.02"]


def test_create_resume_with_jd_text_passes_through(client):
    project_id = db.create_project("A은행 차세대", "2023-02-01")
    _seed_cards(project_id)

    with patch("src.parsing.resume._call_llm", return_value=_MOCK_LLM_RESPONSE) as mock_llm:
        response = client.post(
            "/api/resume",
            json={"project_id": project_id, "jd_text": "백엔드 성능 최적화 경험자 우대"},
        )

    assert response.status_code == 200
    # jd_text가 프롬프트에 실제로 포함되어 LLM 호출부까지 전달됐는지 확인
    called_prompt = mock_llm.call_args[0][0]
    assert "백엔드 성능 최적화 경험자 우대" in called_prompt


def test_create_resume_empty_project_returns_empty_items(client):
    project_id = db.create_project("빈 프로젝트", "2023-02-01")

    response = client.post("/api/resume", json={"project_id": project_id})

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_create_resume_never_fabricates_missing_result(client):
    """CLAUDE.md 2.2: 기록에 숫자가 없으면 result는 빈 문자열이어야 한다."""
    project_id = db.create_project("온보딩", "2023-04-01")
    db.save_card(
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
                    "source_dates": ["04.01"],
                }
            ]
        },
        ensure_ascii=False,
    )

    with patch("src.parsing.resume._call_llm", return_value=mock_response):
        response = client.post("/api/resume", json={"project_id": project_id})

    assert response.json()["items"][0]["result"] == ""
