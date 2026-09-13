"""Track B 담당: 파이프라인 개편(9/13 피벗) 테스트.

- run_pipeline(): 현재 프로젝트 자동 배정 + 카드 저장, JD 매칭은 더 이상 하지 않음
- build_career_doc(): 프로젝트 카드를 모아 build_resume() 호출

DB는 test_db.py와 동일하게 격리된 임시 SQLite 파일을 쓰고,
LLM 호출부(parse_note, build_resume)는 모킹한다.
"""
from unittest.mock import patch

import pytest

from src.agent.pipeline import build_career_doc, run_pipeline, run_pipeline_batch
from src.parsing.parser import ParsedEntry
from src.parsing.resume import StarItem
from src.storage import db


@pytest.fixture(autouse=True)
def _isolated_db(monkeypatch, tmp_path):
    class _FakeSettings:
        db_path = str(tmp_path / "test.db")

    monkeypatch.setattr(db, "settings", _FakeSettings())
    yield


def _make_parsed(raw_text="결제 버그 고침") -> ParsedEntry:
    return ParsedEntry(
        raw_text=raw_text,
        refined_sentence=f"[정제됨] {raw_text}",
        skill_tags=["결제시스템"],
        confidence=0.9,
    )


def test_run_pipeline_saves_card_with_null_project_when_no_current_project():
    with patch("src.agent.pipeline.parse_note", return_value=_make_parsed()):
        result = run_pipeline("결제 버그 고침")

    assert "matched_jds" not in result
    assert result["parsed"].refined_sentence == "[정제됨] 결제 버그 고침"
    cards = db.list_cards()
    assert len(cards) == 1
    assert cards[0].id == result["card_id"]
    assert cards[0].project_id is None


def test_run_pipeline_auto_assigns_new_card_to_current_project():
    project_id = db.create_project("A은행 차세대", "2023-02-01")

    with patch("src.agent.pipeline.parse_note", return_value=_make_parsed()):
        run_pipeline("결제 버그 고침")

    cards = db.list_cards(project_id)
    assert len(cards) == 1
    assert cards[0].project_id == project_id


def test_run_pipeline_does_not_call_match_jds():
    """일상 입력 경로에서 벡터 쿼리(match_jds)가 아예 호출되지 않아야 한다 (2.1 원칙)."""
    with patch("src.agent.pipeline.parse_note", return_value=_make_parsed()):
        with patch("src.agent.vectorstore.match_jds") as mock_match:
            run_pipeline("결제 버그 고침")
            mock_match.assert_not_called()


def test_run_pipeline_batch_saves_all_cards():
    with patch("src.agent.pipeline.parse_note", side_effect=[_make_parsed("a"), _make_parsed("b")]):
        results = run_pipeline_batch(["a", "b"])

    assert len(results) == 2
    assert len(db.list_cards()) == 2


def test_build_career_doc_uses_project_cards():
    project_id = db.create_project("A은행 차세대", "2023-02-01")
    with patch("src.agent.pipeline.parse_note", return_value=_make_parsed()):
        run_pipeline("레디스 캐싱 도입")

    fake_item = StarItem(
        title="t", period="p", situation="s", task="t", action="a", result="",
        source_dates=["02.14"],
    )
    with patch("src.agent.pipeline.build_resume", return_value=[fake_item]) as mock_build:
        items = build_career_doc(project_id)

    assert items == [fake_item]
    called_cards = mock_build.call_args[0][0]
    assert len(called_cards) == 1
    assert called_cards[0].project_id == project_id


def test_build_career_doc_passes_jd_text_through():
    project_id = db.create_project("A은행 차세대", "2023-02-01")
    with patch("src.agent.pipeline.build_resume", return_value=[]) as mock_build:
        build_career_doc(project_id, jd_text="백엔드 성능 최적화 경험자 우대")

    assert mock_build.call_args.kwargs.get("jd_text") == "백엔드 성능 최적화 경험자 우대"
