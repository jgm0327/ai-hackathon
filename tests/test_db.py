"""Track B 담당: src/storage/db.py의 CRUD + is_current 유일성 + 시드 로더 테스트.

각 테스트는 격리된 임시 SQLite 파일을 쓴다(모듈 전역 settings를 monkeypatch).
"""
import json

import pytest

from src.parsing.parser import ParsedEntry
from src.storage import db


@pytest.fixture(autouse=True)
def _isolated_db(monkeypatch, tmp_path):
    """테스트마다 독립된 DB 파일을 쓰게 해서 서로 영향을 주지 않게 한다."""

    class _FakeSettings:
        db_path = str(tmp_path / "test.db")

    monkeypatch.setattr(db, "settings", _FakeSettings())
    yield


def _make_parsed(raw_text="결제 버그 고침", skill_tags=None, confidence=0.9) -> ParsedEntry:
    return ParsedEntry(
        raw_text=raw_text,
        refined_sentence=f"[정제됨] {raw_text}",
        skill_tags=skill_tags or ["결제시스템"],
        confidence=confidence,
    )


def test_save_and_list_cards_roundtrip():
    parsed = _make_parsed()
    card_id = db.save_card(None, parsed, "2023-02-14")

    cards = db.list_cards()
    assert len(cards) == 1
    card = cards[0]
    assert card.id == card_id
    assert card.project_id is None
    assert card.raw_text == parsed.raw_text
    assert card.refined_sentence == parsed.refined_sentence
    assert card.skill_tags == parsed.skill_tags
    assert card.confidence == parsed.confidence
    assert card.created_at == "2023-02-14"


def test_get_card_returns_matching_card():
    parsed = _make_parsed()
    card_id = db.save_card(None, parsed, "2023-02-14")

    card = db.get_card(card_id)
    assert card is not None
    assert card.id == card_id
    assert card.refined_sentence == parsed.refined_sentence


def test_get_card_returns_none_for_missing_id():
    assert db.get_card(9999) is None


def test_list_cards_returns_oldest_first():
    db.save_card(None, _make_parsed("두 번째"), "2023-02-17")
    db.save_card(None, _make_parsed("첫 번째"), "2023-02-14")

    cards = db.list_cards()
    assert [c.raw_text for c in cards] == ["첫 번째", "두 번째"]


def test_list_cards_filtered_by_project():
    project_a = db.create_project("A은행 차세대", "2023-02-01")
    project_b = db.create_project("B카드 시스템", "2022-05-01")

    db.save_card(project_a, _make_parsed("A 프로젝트 카드"), "2023-02-14")
    db.save_card(project_b, _make_parsed("B 프로젝트 카드"), "2022-11-04")

    cards_a = db.list_cards(project_id=project_a)
    assert len(cards_a) == 1
    assert cards_a[0].raw_text == "A 프로젝트 카드"


def test_create_project_sets_current_automatically():
    project_id = db.create_project("A은행 차세대", "2023-02-01")

    current = db.get_current_project()
    assert current is not None
    assert current.id == project_id
    assert current.is_current is True


def test_creating_new_project_unsets_previous_current():
    first = db.create_project("B카드 시스템", "2022-05-01")
    second = db.create_project("A은행 차세대", "2023-02-01")

    projects = {p.id: p for p in db.list_projects()}
    assert projects[first].is_current is False
    assert projects[second].is_current is True


def test_set_current_project_switches_current_flag():
    first = db.create_project("B카드 시스템", "2022-05-01")
    second = db.create_project("A은행 차세대", "2023-02-01")

    db.set_current_project(first)

    projects = {p.id: p for p in db.list_projects()}
    assert projects[first].is_current is True
    assert projects[second].is_current is False
    # 유일성: 한 번에 딱 하나만 is_current여야 한다.
    assert sum(p.is_current for p in projects.values()) == 1


def test_get_current_project_returns_none_without_projects():
    assert db.get_current_project() is None


def test_delete_card_removes_it():
    card_id = db.save_card(None, _make_parsed(), "2023-02-14")
    other_id = db.save_card(None, _make_parsed("다른 카드"), "2023-02-15")

    db.delete_card(card_id)

    remaining = db.list_cards()
    assert [c.id for c in remaining] == [other_id]


def test_delete_card_missing_id_is_noop():
    db.delete_card(9999)  # 예외 없이 조용히 무시돼야 한다
    assert db.list_cards() == []


def test_update_project_renames_name():
    project_id = db.create_project("A은행 차세대", "2023-02-01")

    db.update_project(project_id, name="A은행 차세대 2차")

    updated = next(p for p in db.list_projects() if p.id == project_id)
    assert updated.name == "A은행 차세대 2차"


def test_update_project_sets_ended_at():
    project_id = db.create_project("A은행 차세대", "2023-02-01")

    db.update_project(project_id, ended_at="2023-11-30")

    updated = next(p for p in db.list_projects() if p.id == project_id)
    assert updated.ended_at == "2023-11-30"


def test_update_project_is_current_unsets_previous_current():
    first = db.create_project("B카드 시스템", "2022-05-01")
    second = db.create_project("A은행 차세대", "2023-02-01")

    db.update_project(first, is_current=True)

    projects = {p.id: p for p in db.list_projects()}
    assert projects[first].is_current is True
    assert projects[second].is_current is False


def test_update_project_rejects_unknown_field():
    project_id = db.create_project("A은행 차세대", "2023-02-01")

    with pytest.raises(ValueError):
        db.update_project(project_id, unknown_field="x")


def test_load_seed_cards_creates_projects_and_cards(tmp_path):
    seed_path = tmp_path / "seed.json"
    seed_path.write_text(
        json.dumps(
            {
                "projects": [
                    {
                        "name": "B카드 시스템 구축",
                        "started_at": "2022-05-01",
                        "ended_at": "2023-01-31",
                        "cards": [
                            {
                                "created_at": "2022-11-04",
                                "raw_text": "정산 배치 병렬화",
                                "refined_sentence": "정산 배치를 병렬화함",
                                "skill_tags": ["배치처리"],
                                "confidence": 0.88,
                            }
                        ],
                    },
                    {
                        "name": "A은행 차세대",
                        "started_at": "2023-02-01",
                        "cards": [
                            {
                                "created_at": "2023-02-14",
                                "raw_text": "레디스 캐시 붙임",
                                "refined_sentence": "Redis 캐싱 레이어를 도입함",
                                "skill_tags": ["Redis", "성능최적화"],
                                "confidence": 0.9,
                            },
                            {
                                "created_at": "2023-03-02",
                                "raw_text": "오류율 0.8% -> 0.3%",
                                "refined_sentence": "결제 오류율을 0.8%에서 0.3%로 개선함",
                                "skill_tags": ["성능최적화"],
                                "confidence": 0.92,
                            },
                        ],
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    db.load_seed_cards(str(seed_path))

    projects = db.list_projects()
    assert len(projects) == 2
    a_bank = next(p for p in projects if p.name == "A은행 차세대")
    b_card = next(p for p in projects if p.name == "B카드 시스템 구축")

    # JSON에 나열된 순서상 마지막(A은행)이 자동으로 현재 프로젝트가 된다.
    assert a_bank.is_current is True
    assert b_card.is_current is False
    assert b_card.ended_at == "2023-01-31"

    a_cards = db.list_cards(project_id=a_bank.id)
    assert len(a_cards) == 2
    # 시간차 페어(02.14 조치 + 03.02 결과)가 같은 프로젝트 안에 둘 다 존재해야 한다.
    assert {c.created_at for c in a_cards} == {"2023-02-14", "2023-03-02"}


def test_get_profile_defaults_to_all_none_when_never_onboarded():
    profile = db.get_profile()
    assert profile == db.Profile(job_field=None, job_detail=None, years_segment=None)


def test_save_and_get_profile_roundtrip():
    db.save_profile(job_field="개발", job_detail="백엔드", years_segment="4-6")
    profile = db.get_profile()
    assert profile == db.Profile(job_field="개발", job_detail="백엔드", years_segment="4-6")


def test_save_profile_overwrites_previous_value_singleton():
    db.save_profile(job_field="개발", job_detail="백엔드", years_segment="1-3")
    db.save_profile(job_field="디자인", job_detail=None, years_segment="7-10")

    profile = db.get_profile()
    assert profile == db.Profile(job_field="디자인", job_detail=None, years_segment="7-10")
