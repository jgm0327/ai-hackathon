"""Track B 담당: 파이프라인 개편(9/13 피벗) 테스트.

- run_pipeline(): 현재 프로젝트 자동 배정 + 카드 저장, JD 매칭은 더 이상 하지 않음
- build_career_doc(): 프로젝트 카드를 모아 build_resume() 호출

DB는 test_db.py와 동일하게 격리된 임시 SQLite 파일을 쓰고,
LLM 호출부(parse_note, build_resume)는 모킹한다.

**구현 노트 (9/14, 카카오 로그인 Phase B)**: `run_pipeline`/`run_pipeline_batch`/
`build_career_doc` 전부 `user_id`를 맨 앞 인자로 받는다.
"""
from dataclasses import replace
from unittest.mock import patch

import pytest

from src.agent.pipeline import (
    build_career_doc,
    collect_scoped_cards,
    retry_refinement,
    run_pipeline,
    run_pipeline_batch,
)
from src.parsing.parser import ParsedEntry
from src.parsing.resume import StarItem
from src.storage import db


@pytest.fixture(autouse=True)
def _isolated_db(monkeypatch, tmp_path):
    class _FakeSettings:
        db_path = str(tmp_path / "test.db")

    monkeypatch.setattr(db, "settings", _FakeSettings())
    yield


@pytest.fixture(autouse=True)
def _no_op_canonicalize(monkeypatch):
    """태그 캐노니컬라이제이션 자체(임베딩/Chroma)는 test_tag_canonicalizer.py가 검증한다.

    여기서는 파이프라인 오케스트레이션 로직만 격리해서 보고 싶으므로 항등 함수로
    대체한다 — 실제 임베딩 함수를 그대로 쓰면 매 테스트가 Chroma 기본 임베딩(다운로드
    필요)에 의존하게 돼서 test_vectorstore.py와 동일한 이유로 모킹한다.
    """
    monkeypatch.setattr("src.agent.pipeline.canonicalize_tags", lambda tags: tags)
    yield


@pytest.fixture
def user_id() -> int:
    return db.upsert_user(kakao_id="test-kakao-id", nickname="테스터", profile_image_url=None, now="2026-01-01T00:00:00")


def _make_parsed(raw_text="결제 버그 고침") -> ParsedEntry:
    return ParsedEntry(
        raw_text=raw_text,
        refined_sentence=f"[정제됨] {raw_text}",
        skill_tags=["결제시스템"],
        confidence=0.9,
    )


def test_run_pipeline_saves_card_with_null_project_when_no_current_project(user_id):
    with patch("src.agent.pipeline.parse_note", return_value=_make_parsed()):
        result = run_pipeline(user_id, "결제 버그 고침")

    assert "matched_jds" not in result
    assert result["parsed"].refined_sentence == "[정제됨] 결제 버그 고침"
    cards = db.list_cards(user_id)
    assert len(cards) == 1
    assert cards[0].id == result["card_id"]
    assert cards[0].project_id is None


def test_run_pipeline_auto_assigns_new_card_to_current_project(user_id):
    project_id = db.create_project(user_id, "A은행 차세대", "2023-02-01")

    with patch("src.agent.pipeline.parse_note", return_value=_make_parsed()):
        run_pipeline(user_id, "결제 버그 고침")

    cards = db.list_cards(user_id, project_id)
    assert len(cards) == 1
    assert cards[0].project_id == project_id


def test_run_pipeline_canonicalizes_tags_before_saving(user_id):
    """save_card()로 넘기는 skill_tags는 parse_note() 원본이 아니라 canonicalize_tags()
    결과여야 한다 — 태그 표기 통일(9/14 신규)이 실제로 저장 경로에 걸려 있는지 확인."""
    with patch("src.agent.pipeline.parse_note", return_value=_make_parsed()):
        with patch(
            "src.agent.pipeline.canonicalize_tags", return_value=["결제/정산"]
        ) as mock_canonicalize:
            result = run_pipeline(user_id, "결제 버그 고침")

    mock_canonicalize.assert_called_once_with(["결제시스템"])
    assert result["parsed"].skill_tags == ["결제/정산"]
    assert db.list_cards(user_id)[0].skill_tags == ["결제/정산"]


def test_run_pipeline_does_not_call_match_jds(user_id):
    """일상 입력 경로에서 벡터 쿼리(match_jds)가 아예 호출되지 않아야 한다 (2.1 원칙)."""
    with patch("src.agent.pipeline.parse_note", return_value=_make_parsed()):
        with patch("src.agent.vectorstore.match_jds") as mock_match:
            run_pipeline(user_id, "결제 버그 고침")
            mock_match.assert_not_called()


def test_run_pipeline_batch_saves_all_cards(user_id):
    with patch("src.agent.pipeline.parse_note", side_effect=[_make_parsed("a"), _make_parsed("b")]):
        results = run_pipeline_batch(user_id, ["a", "b"])

    assert len(results) == 2
    assert len(db.list_cards(user_id)) == 2


def test_run_pipeline_scopes_cards_to_the_given_user(user_id):
    """다른 유저로 저장한 카드가 이 유저의 목록에 섞이면 안 된다."""
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    with patch("src.agent.pipeline.parse_note", return_value=_make_parsed()):
        run_pipeline(other_user_id, "다른 유저 카드")

    assert db.list_cards(user_id) == []
    assert len(db.list_cards(other_user_id)) == 1


def test_build_career_doc_uses_project_cards(user_id):
    project_id = db.create_project(user_id, "A은행 차세대", "2023-02-01")
    with patch("src.agent.pipeline.parse_note", return_value=_make_parsed()):
        run_pipeline(user_id, "레디스 캐싱 도입")

    fake_item = StarItem(
        title="t", period="p", situation="s", task="t", action="a", result="",
        source_dates=["02.14"],
    )
    with patch("src.agent.pipeline.build_resume", return_value=[fake_item]) as mock_build:
        items = build_career_doc(user_id, project_id)

    # 9/18부터 항목에 출처 프로젝트가 찍힌다(마스터 경력기술서의 프로젝트 헤드용).
    # 나머지 필드는 build_resume()이 준 그대로여야 한다.
    assert len(items) == 1
    assert items[0].project_id == project_id
    assert items[0].project_name == "A은행 차세대"
    assert replace(items[0], project_id=None, project_name=None) == fake_item
    called_cards = mock_build.call_args[0][0]
    assert len(called_cards) == 1
    assert called_cards[0].project_id == project_id


# --- 마스터 경력기술서 범위 선택 (9/18 신규, Figma 4.2.1) ---


def test_build_career_doc_keeps_projects_separate(user_id):
    """프로젝트 경계를 넘어 카드를 한 덩어리로 합치면 안 된다 (CLAUDE.md 3장).

    A은행의 "결제 API 개선"과 B카드의 "결제 API 개선"이 한 번의 build_resume()
    호출로 들어가면 하나로 묶여 경력이 반으로 줄어든다. 프로젝트마다 따로 불러야 한다.
    """
    a_id = db.create_project(user_id, "A은행 차세대", "2023-02-01")
    with patch("src.agent.pipeline.parse_note", return_value=_make_parsed()):
        run_pipeline(user_id, "A은행 결제 API 개선")
    b_id = db.create_project(user_id, "B카드 정산", "2024-02-01")
    with patch("src.agent.pipeline.parse_note", return_value=_make_parsed()):
        run_pipeline(user_id, "B카드 결제 API 개선")

    fake_item = StarItem(title="t", period="p", situation="s", task="t", action="a", result="")
    with patch("src.agent.pipeline.build_resume", return_value=[fake_item]) as mock_build:
        items = build_career_doc(user_id, project_ids=[b_id, a_id])

    assert mock_build.call_count == 2
    # 요청이 준 순서를 그대로 보존한다 (프론트가 최신 프로젝트부터 보낸다).
    assert [i.project_name for i in items] == ["B카드 정산", "A은행 차세대"]
    for call in mock_build.call_args_list:
        assert len(call[0][0]) == 1  # 프로젝트당 자기 카드 1장씩만


def test_build_career_doc_includes_unassigned_as_its_own_section(user_id):
    with patch("src.agent.pipeline.parse_note", return_value=_make_parsed()):
        run_pipeline(user_id, "프로젝트 없는 기록")  # 현재 프로젝트가 없으므로 미분류

    fake_item = StarItem(title="t", period="p", situation="s", task="t", action="a", result="")
    with patch("src.agent.pipeline.build_resume", return_value=[fake_item]):
        items = build_career_doc(user_id, project_ids=[], include_unassigned=True)

    assert [i.project_name for i in items] == ["미분류 기록"]
    assert items[0].project_id is None


def test_build_career_doc_ignores_other_users_projects(user_id):
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    other_project_id = db.create_project(other_user_id, "남의 프로젝트", "2023-02-01")

    with patch("src.agent.pipeline.build_resume", return_value=[]) as mock_build:
        items = build_career_doc(user_id, project_ids=[other_project_id])

    assert items == []
    assert mock_build.call_count == 0


def test_collect_scoped_cards_merges_and_sorts_by_date(user_id):
    """JD 매칭/문장 보강은 프로젝트 경계가 필요 없다 — 다만 날짜순은 지켜야 한다
    (build_resume()/match_jd_requirements()의 프롬프트가 날짜순을 전제한다)."""
    a_id = db.create_project(user_id, "A", "2023-02-01")
    db.save_card(user_id, a_id, _make_parsed(), "2023-03-01")
    b_id = db.create_project(user_id, "B", "2023-01-01")
    db.save_card(user_id, b_id, _make_parsed(), "2023-01-15")
    db.save_card(user_id, None, _make_parsed(), "2023-02-15")

    cards = collect_scoped_cards(user_id, project_ids=[a_id, b_id], include_unassigned=True)

    assert [c.created_at for c in cards] == ["2023-01-15", "2023-02-15", "2023-03-01"]


def test_build_career_doc_passes_jd_text_through(user_id):
    project_id = db.create_project(user_id, "A은행 차세대", "2023-02-01")
    with patch("src.agent.pipeline.build_resume", return_value=[]) as mock_build:
        build_career_doc(user_id, project_id, jd_text="백엔드 성능 최적화 경험자 우대")

    assert mock_build.call_args.kwargs.get("jd_text") == "백엔드 성능 최적화 경험자 우대"


# --- 변환 실패 시 원문 저장 폴백 (9/15 신규) ---


def test_run_pipeline_falls_back_to_raw_text_when_parse_note_fails(user_id):
    """parse_note()가 실패해도 카드는 반드시 저장돼야 한다 (CLAUDE.md P0)."""
    with patch("src.agent.pipeline.parse_note", side_effect=RuntimeError("LLM 타임아웃")):
        result = run_pipeline(user_id, "결제 버그 고침")

    assert result["refinement_failed"] is True
    assert result["parsed"].refined_sentence == "결제 버그 고침"
    assert result["parsed"].skill_tags == []
    assert result["parsed"].confidence == 0.0
    cards = db.list_cards(user_id)
    assert len(cards) == 1
    assert cards[0].raw_text == "결제 버그 고침"
    assert cards[0].refined_sentence == "결제 버그 고침"


def test_run_pipeline_success_sets_refinement_failed_false(user_id):
    with patch("src.agent.pipeline.parse_note", return_value=_make_parsed()):
        result = run_pipeline(user_id, "결제 버그 고침")

    assert result["refinement_failed"] is False


def test_retry_refinement_updates_fallback_card_on_success(user_id):
    with patch("src.agent.pipeline.parse_note", side_effect=RuntimeError("boom")):
        result = run_pipeline(user_id, "결제 버그 고침")
    card_id = result["card_id"]

    with patch("src.agent.pipeline.parse_note", return_value=_make_parsed("결제 버그 고침")):
        updated = retry_refinement(user_id, card_id)

    assert updated.refined_sentence == "[정제됨] 결제 버그 고침"
    assert updated.skill_tags == ["결제시스템"]
    assert updated.confidence == 0.9


def test_retry_refinement_returns_none_for_missing_card(user_id):
    assert retry_refinement(user_id, 9999) is None


def test_retry_refinement_returns_none_for_another_users_card(user_id):
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    with patch("src.agent.pipeline.parse_note", side_effect=RuntimeError("boom")):
        result = run_pipeline(other_user_id, "다른 유저 카드")

    assert retry_refinement(user_id, result["card_id"]) is None


def test_retry_refinement_propagates_exception_when_parse_fails_again(user_id):
    """재시도가 또 실패하면 예외를 그대로 전파한다 — 폴백 저장이 이미 끝난 상태라
    호출부가 "다시 실패했다"고만 알리면 되고, 데이터 유실은 없다."""
    with patch("src.agent.pipeline.parse_note", side_effect=RuntimeError("boom")):
        result = run_pipeline(user_id, "결제 버그 고침")
    card_id = result["card_id"]

    with patch("src.agent.pipeline.parse_note", side_effect=RuntimeError("again")):
        with pytest.raises(RuntimeError):
            retry_refinement(user_id, card_id)

    # 재시도 실패해도 폴백 저장된 원문은 그대로 남아있다.
    assert db.get_card(user_id, card_id).raw_text == "결제 버그 고침"
