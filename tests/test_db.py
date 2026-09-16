"""Track B 담당: src/storage/db.py의 CRUD + is_current 유일성 + 시드 로더 테스트.

각 테스트는 격리된 임시 SQLite 파일을 쓴다(모듈 전역 settings를 monkeypatch).

**구현 노트 (9/14, 카카오 로그인 Phase B)**: 모든 storage 함수가 이제 `user_id`를
맨 앞 인자로 받으므로, 각 테스트가 쓸 유저 하나를 `user_id` 픽스처로 먼저 만들어둔다.
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


@pytest.fixture
def user_id() -> int:
    """이 테스트에서 쓸 로그인 유저 하나를 만들어 id를 반환한다."""
    return db.upsert_user(kakao_id="test-kakao-id", nickname="테스터", profile_image_url=None, now="2026-01-01T00:00:00")


def _make_parsed(raw_text="결제 버그 고침", skill_tags=None, confidence=0.9) -> ParsedEntry:
    return ParsedEntry(
        raw_text=raw_text,
        refined_sentence=f"[정제됨] {raw_text}",
        skill_tags=skill_tags or ["결제시스템"],
        confidence=confidence,
    )


def test_save_and_list_cards_roundtrip(user_id):
    parsed = _make_parsed()
    card_id = db.save_card(user_id, None, parsed, "2023-02-14")

    cards = db.list_cards(user_id)
    assert len(cards) == 1
    card = cards[0]
    assert card.id == card_id
    assert card.project_id is None
    assert card.raw_text == parsed.raw_text
    assert card.refined_sentence == parsed.refined_sentence
    assert card.skill_tags == parsed.skill_tags
    assert card.confidence == parsed.confidence
    assert card.created_at == "2023-02-14"
    assert card.created_time is None  # created_time을 안 넘기면 null (하위 호환)


def test_save_card_stores_created_time(user_id):
    """9/16 신규 — 홈 화면 "오늘 남긴 것" 목록용 시각."""
    card_id = db.save_card(user_id, None, _make_parsed(), "2023-02-14", "09:40")

    card = db.get_card(user_id, card_id)
    assert card.created_time == "09:40"
    assert card.created_at == "2023-02-14"  # 날짜 필드는 그대로 영향 없음


def test_get_card_returns_matching_card(user_id):
    parsed = _make_parsed()
    card_id = db.save_card(user_id, None, parsed, "2023-02-14")

    card = db.get_card(user_id, card_id)
    assert card is not None
    assert card.id == card_id
    assert card.refined_sentence == parsed.refined_sentence


def test_get_card_returns_none_for_missing_id(user_id):
    assert db.get_card(user_id, 9999) is None


def test_get_card_returns_none_for_another_users_card(user_id):
    """소유권 강제 — 다른 유저의 카드는 id를 알아도 조회되면 안 된다."""
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    card_id = db.save_card(other_user_id, None, _make_parsed(), "2023-02-14")

    assert db.get_card(user_id, card_id) is None


def test_list_cards_returns_oldest_first(user_id):
    db.save_card(user_id, None, _make_parsed("두 번째"), "2023-02-17")
    db.save_card(user_id, None, _make_parsed("첫 번째"), "2023-02-14")

    cards = db.list_cards(user_id)
    assert [c.raw_text for c in cards] == ["첫 번째", "두 번째"]


def test_list_cards_filtered_by_project(user_id):
    project_a = db.create_project(user_id, "A은행 차세대", "2023-02-01")
    project_b = db.create_project(user_id, "B카드 시스템", "2022-05-01")

    db.save_card(user_id, project_a, _make_parsed("A 프로젝트 카드"), "2023-02-14")
    db.save_card(user_id, project_b, _make_parsed("B 프로젝트 카드"), "2022-11-04")

    cards_a = db.list_cards(user_id, project_id=project_a)
    assert len(cards_a) == 1
    assert cards_a[0].raw_text == "A 프로젝트 카드"


def test_create_project_sets_current_automatically(user_id):
    project_id = db.create_project(user_id, "A은행 차세대", "2023-02-01")

    current = db.get_current_project(user_id)
    assert current is not None
    assert current.id == project_id
    assert current.is_current is True


def test_creating_new_project_unsets_previous_current(user_id):
    first = db.create_project(user_id, "B카드 시스템", "2022-05-01")
    second = db.create_project(user_id, "A은행 차세대", "2023-02-01")

    projects = {p.id: p for p in db.list_projects(user_id)}
    assert projects[first].is_current is False
    assert projects[second].is_current is True


def test_set_current_project_switches_current_flag(user_id):
    first = db.create_project(user_id, "B카드 시스템", "2022-05-01")
    second = db.create_project(user_id, "A은행 차세대", "2023-02-01")

    db.set_current_project(user_id, first)

    projects = {p.id: p for p in db.list_projects(user_id)}
    assert projects[first].is_current is True
    assert projects[second].is_current is False
    # 유일성: 한 번에 딱 하나만 is_current여야 한다.
    assert sum(p.is_current for p in projects.values()) == 1


def test_get_current_project_returns_none_without_projects(user_id):
    assert db.get_current_project(user_id) is None


def test_set_current_project_does_not_affect_other_users(user_id):
    """다른 유저의 is_current는 이 유저의 프로젝트 전환에 영향받으면 안 된다."""
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    other_project = db.create_project(other_user_id, "다른유저 프로젝트", "2023-01-01")

    db.create_project(user_id, "내 프로젝트", "2023-02-01")

    other_current = db.get_current_project(other_user_id)
    assert other_current is not None
    assert other_current.id == other_project


def test_delete_card_removes_it(user_id):
    card_id = db.save_card(user_id, None, _make_parsed(), "2023-02-14")
    other_id = db.save_card(user_id, None, _make_parsed("다른 카드"), "2023-02-15")

    db.delete_card(user_id, card_id)

    remaining = db.list_cards(user_id)
    assert [c.id for c in remaining] == [other_id]


def test_delete_card_missing_id_is_noop(user_id):
    db.delete_card(user_id, 9999)  # 예외 없이 조용히 무시돼야 한다
    assert db.list_cards(user_id) == []


def test_delete_card_does_not_remove_another_users_card(user_id):
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    other_card_id = db.save_card(other_user_id, None, _make_parsed(), "2023-02-14")

    db.delete_card(user_id, other_card_id)  # 내 카드가 아니므로 조용히 무시

    assert db.list_cards(other_user_id) != []


def test_update_project_renames_name(user_id):
    project_id = db.create_project(user_id, "A은행 차세대", "2023-02-01")

    db.update_project(user_id, project_id, name="A은행 차세대 2차")

    updated = next(p for p in db.list_projects(user_id) if p.id == project_id)
    assert updated.name == "A은행 차세대 2차"


def test_update_project_sets_ended_at(user_id):
    project_id = db.create_project(user_id, "A은행 차세대", "2023-02-01")

    db.update_project(user_id, project_id, ended_at="2023-11-30")

    updated = next(p for p in db.list_projects(user_id) if p.id == project_id)
    assert updated.ended_at == "2023-11-30"


def test_update_project_is_current_unsets_previous_current(user_id):
    first = db.create_project(user_id, "B카드 시스템", "2022-05-01")
    second = db.create_project(user_id, "A은행 차세대", "2023-02-01")

    db.update_project(user_id, first, is_current=True)

    projects = {p.id: p for p in db.list_projects(user_id)}
    assert projects[first].is_current is True
    assert projects[second].is_current is False


def test_update_project_rejects_unknown_field(user_id):
    project_id = db.create_project(user_id, "A은행 차세대", "2023-02-01")

    with pytest.raises(ValueError):
        db.update_project(user_id, project_id, unknown_field="x")


def test_load_seed_cards_creates_projects_and_cards(user_id, tmp_path):
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

    db.load_seed_cards(user_id, str(seed_path))

    projects = db.list_projects(user_id)
    assert len(projects) == 2
    a_bank = next(p for p in projects if p.name == "A은행 차세대")
    b_card = next(p for p in projects if p.name == "B카드 시스템 구축")

    # JSON에 나열된 순서상 마지막(A은행)이 자동으로 현재 프로젝트가 된다.
    assert a_bank.is_current is True
    assert b_card.is_current is False
    assert b_card.ended_at == "2023-01-31"

    a_cards = db.list_cards(user_id, project_id=a_bank.id)
    assert len(a_cards) == 2
    # 시간차 페어(02.14 조치 + 03.02 결과)가 같은 프로젝트 안에 둘 다 존재해야 한다.
    assert {c.created_at for c in a_cards} == {"2023-02-14", "2023-03-02"}


def test_get_profile_defaults_to_all_none_when_never_onboarded(user_id):
    profile = db.get_profile(user_id)
    assert profile == db.Profile(job_field=None, job_detail=None, years_segment=None)


def test_save_and_get_profile_roundtrip(user_id):
    db.save_profile(user_id, job_field="개발", job_detail="백엔드", years_segment="4-6")
    profile = db.get_profile(user_id)
    assert profile == db.Profile(job_field="개발", job_detail="백엔드", years_segment="4-6")


def test_save_profile_overwrites_previous_value_singleton(user_id):
    db.save_profile(user_id, job_field="개발", job_detail="백엔드", years_segment="1-3")
    db.save_profile(user_id, job_field="디자인", job_detail=None, years_segment="7-10")

    profile = db.get_profile(user_id)
    assert profile == db.Profile(job_field="디자인", job_detail=None, years_segment="7-10")


def test_save_profile_does_not_affect_another_users_profile(user_id):
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    db.save_profile(other_user_id, job_field="디자인", job_detail=None, years_segment="10+")

    db.save_profile(user_id, job_field="개발", job_detail="백엔드", years_segment="1-3")

    other_profile = db.get_profile(other_user_id)
    assert other_profile == db.Profile(job_field="디자인", job_detail=None, years_segment="10+")


def test_update_card_tags_overwrites_skill_tags(user_id):
    """9/14 신규 — 카테고리(스킬 태그) 직접 수정."""
    card_id = db.save_card(user_id, None, _make_parsed(skill_tags=["Redis"]), "2023-02-14")

    updated = db.update_card_tags(user_id, card_id, ["결제시스템", "성능최적화"])

    assert updated is not None
    assert updated.skill_tags == ["결제시스템", "성능최적화"]
    assert db.get_card(user_id, card_id).skill_tags == ["결제시스템", "성능최적화"]


def test_update_card_tags_returns_none_for_missing_card(user_id):
    assert db.update_card_tags(user_id, 9999, ["x"]) is None


def test_update_card_tags_does_not_affect_another_users_card(user_id):
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    other_card_id = db.save_card(other_user_id, None, _make_parsed(skill_tags=["Redis"]), "2023-02-14")

    result = db.update_card_tags(user_id, other_card_id, ["가로채기"])

    assert result is None
    assert db.get_card(other_user_id, other_card_id).skill_tags == ["Redis"]


def test_update_card_sentence_only_leaves_tags_untouched(user_id):
    """9/15 신규 — 문장 직접 수정. skill_tags를 안 넘기면 그대로 유지된다."""
    card_id = db.save_card(user_id, None, _make_parsed(skill_tags=["Redis"]), "2023-02-14")

    updated = db.update_card(user_id, card_id, refined_sentence="사람이 직접 고친 문장")

    assert updated.refined_sentence == "사람이 직접 고친 문장"
    assert updated.skill_tags == ["Redis"]


def test_update_card_tags_only_leaves_sentence_untouched(user_id):
    card_id = db.save_card(user_id, None, _make_parsed(), "2023-02-14")
    original_sentence = db.get_card(user_id, card_id).refined_sentence

    updated = db.update_card(user_id, card_id, skill_tags=["새태그"])

    assert updated.refined_sentence == original_sentence
    assert updated.skill_tags == ["새태그"]


def test_update_card_both_fields_and_confidence(user_id):
    """confidence는 PATCH API에는 안 노출되지만(재정리 전용), 함수 자체는 지원한다."""
    card_id = db.save_card(user_id, None, _make_parsed(confidence=0.0), "2023-02-14")

    updated = db.update_card(
        user_id, card_id, skill_tags=["A"], refined_sentence="새 문장", confidence=0.95
    )

    assert updated.skill_tags == ["A"]
    assert updated.refined_sentence == "새 문장"
    assert updated.confidence == 0.95


def test_update_card_with_nothing_changes_nothing(user_id):
    card_id = db.save_card(user_id, None, _make_parsed(), "2023-02-14")
    before = db.get_card(user_id, card_id)

    updated = db.update_card(user_id, card_id)

    assert updated == before


# --- 경력기술서 초안 저장 (9/14 신규) ---


def test_get_resume_draft_returns_none_when_never_saved(user_id):
    project_id = db.create_project(user_id, "A은행 차세대", "2023-02-01")
    assert db.get_resume_draft(user_id, project_id) is None


def test_save_and_get_resume_draft_roundtrip(user_id):
    project_id = db.create_project(user_id, "A은행 차세대", "2023-02-01")

    saved = db.save_resume_draft(user_id, project_id, "# 결제 API 성능 개선\n...", "2026-09-14T00:00:00")

    assert saved is not None
    assert saved.content == "# 결제 API 성능 개선\n..."
    fetched = db.get_resume_draft(user_id, project_id)
    assert fetched is not None
    assert fetched.content == "# 결제 API 성능 개선\n..."
    assert fetched.updated_at == "2026-09-14T00:00:00"


def test_save_resume_draft_overwrites_previous_content_singleton_per_project(user_id):
    """프로젝트당 초안은 1개만 유지된다(upsert) — 여러 버전을 쌓지 않는다."""
    project_id = db.create_project(user_id, "A은행 차세대", "2023-02-01")

    db.save_resume_draft(user_id, project_id, "초안 v1", "2026-09-14T00:00:00")
    db.save_resume_draft(user_id, project_id, "초안 v2", "2026-09-14T00:01:00")

    fetched = db.get_resume_draft(user_id, project_id)
    assert fetched.content == "초안 v2"
    assert fetched.updated_at == "2026-09-14T00:01:00"


def test_save_resume_draft_rejects_project_not_owned_by_user(user_id):
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    other_project_id = db.create_project(other_user_id, "다른유저 프로젝트", "2023-01-01")

    result = db.save_resume_draft(user_id, other_project_id, "가로채기 시도", "2026-09-14T00:00:00")

    assert result is None
    assert db.get_resume_draft(other_user_id, other_project_id) is None


def test_get_resume_draft_does_not_leak_another_users_draft(user_id):
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    other_project_id = db.create_project(other_user_id, "다른유저 프로젝트", "2023-01-01")
    db.save_resume_draft(other_user_id, other_project_id, "다른 유저 초안", "2026-09-14T00:00:00")

    assert db.get_resume_draft(user_id, other_project_id) is None


# --- get_project (9/14 신규) ---


def test_get_project_returns_matching_project(user_id):
    project_id = db.create_project(user_id, "A은행 차세대", "2023-02-01")

    project = db.get_project(user_id, project_id)

    assert project is not None
    assert project.id == project_id
    assert project.name == "A은행 차세대"


def test_get_project_returns_none_for_missing_or_other_users_project(user_id):
    assert db.get_project(user_id, 9999) is None

    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    other_project_id = db.create_project(other_user_id, "다른유저 프로젝트", "2023-01-01")
    assert db.get_project(user_id, other_project_id) is None


# --- 4.1.1 AI 프로젝트 자동 제안: list_unassigned_cards / bulk_assign_cards_to_project (9/14 신규) ---


def test_list_unassigned_cards_returns_only_null_project_cards(user_id):
    project_id = db.create_project(user_id, "A은행 차세대", "2023-02-01")
    assigned_id = db.save_card(user_id, project_id, _make_parsed("배정된 카드"), "2023-02-14")
    unassigned_id = db.save_card(user_id, None, _make_parsed("미분류 카드"), "2023-02-15")

    result = db.list_unassigned_cards(user_id)

    result_ids = {c.id for c in result}
    assert unassigned_id in result_ids
    assert assigned_id not in result_ids


def test_list_unassigned_cards_does_not_leak_another_users_cards(user_id):
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    db.save_card(other_user_id, None, _make_parsed("다른 유저 미분류 카드"), "2023-02-14")

    assert db.list_unassigned_cards(user_id) == []


def test_bulk_assign_cards_to_project_moves_cards(user_id):
    target_project_id = db.create_project(user_id, "새 프로젝트", "2023-02-01")
    card_id_1 = db.save_card(user_id, None, _make_parsed("미분류1"), "2023-02-14")
    card_id_2 = db.save_card(user_id, None, _make_parsed("미분류2"), "2023-02-15")

    updated_count = db.bulk_assign_cards_to_project(user_id, [card_id_1, card_id_2], target_project_id)

    assert updated_count == 2
    assert db.get_card(user_id, card_id_1).project_id == target_project_id
    assert db.get_card(user_id, card_id_2).project_id == target_project_id
    assert db.list_unassigned_cards(user_id) == []


def test_bulk_assign_cards_to_project_ignores_another_users_cards(user_id):
    other_user_id = db.upsert_user("other-kakao-id", "다른유저", None, "2026-01-01T00:00:00")
    other_card_id = db.save_card(other_user_id, None, _make_parsed("가로채기 대상"), "2023-02-14")
    target_project_id = db.create_project(user_id, "새 프로젝트", "2023-02-01")

    updated_count = db.bulk_assign_cards_to_project(user_id, [other_card_id], target_project_id)

    assert updated_count == 0
    assert db.get_card(other_user_id, other_card_id).project_id is None


def test_bulk_assign_cards_to_project_empty_list_is_noop(user_id):
    project_id = db.create_project(user_id, "새 프로젝트", "2023-02-01")
    assert db.bulk_assign_cards_to_project(user_id, [], project_id) == 0


# --- get_skill_category_counts() — 홈 화면 "무엇이 쌓였나요" 버블 (9/16 신규) ---


def test_skill_category_counts_uses_first_tag_as_representative(user_id):
    """카드 한 장은 태그가 여러 개여도 대표 태그(skill_tags[0]) 하나로만 집계된다."""
    project_id = db.create_project(user_id, "프로젝트", "2023-02-01")
    db.save_card(user_id, project_id, _make_parsed("a", skill_tags=["Redis", "성능최적화"]), "2023-02-14")
    db.save_card(user_id, project_id, _make_parsed("b", skill_tags=["Redis"]), "2023-02-15")
    db.save_card(user_id, project_id, _make_parsed("c", skill_tags=["결제시스템"]), "2023-02-16")

    result = db.get_skill_category_counts(user_id, project_id)

    assert dict(result) == {"Redis": 2, "결제시스템": 1}
    assert sum(count for _, count in result) == 3  # 전체 카드 수와 항상 일치


def test_skill_category_counts_buckets_tagless_cards_as_uncategorized(user_id):
    project_id = db.create_project(user_id, "프로젝트", "2023-02-01")
    # _make_parsed(skill_tags=[])는 헬퍼 내부의 `skill_tags or [...]` 기본값 처리 때문에
    # 빈 리스트가 그대로 안 넘어간다 — 진짜 빈 태그를 재현하려면 직접 구성해야 한다.
    tagless = ParsedEntry(raw_text="무모호", refined_sentence="[정제됨] 무모호", skill_tags=[], confidence=0.1)
    db.save_card(user_id, project_id, tagless, "2023-02-14")

    result = db.get_skill_category_counts(user_id, project_id)

    assert result == [("미분류", 1)]


def test_skill_category_counts_overflow_beyond_top_n_merges_into_uncategorized(user_id):
    """top_n을 넘는 카테고리는 상위 N개만 이름이 남고 나머지는 전부 "미분류"로 합쳐진다."""
    project_id = db.create_project(user_id, "프로젝트", "2023-02-01")
    # 5개 서로 다른 태그, 각각 카드 수를 다르게 줘서 순위가 명확하게 갈리게 한다.
    for tag, count in [("A", 5), ("B", 4), ("C", 3), ("D", 2), ("E", 1)]:
        for i in range(count):
            db.save_card(user_id, project_id, _make_parsed(f"{tag}-{i}", skill_tags=[tag]), "2023-02-14")

    result = db.get_skill_category_counts(user_id, project_id, top_n=4)

    assert result == [("A", 5), ("B", 4), ("C", 3), ("D", 2), ("미분류", 1)]
    assert sum(count for _, count in result) == 15


def test_skill_category_counts_no_uncategorized_bucket_when_nothing_overflows(user_id):
    """상위 top_n 안에 전부 들어가고 태그 없는 카드도 없으면 "미분류" 자체가 안 나온다."""
    project_id = db.create_project(user_id, "프로젝트", "2023-02-01")
    db.save_card(user_id, project_id, _make_parsed(skill_tags=["Redis"]), "2023-02-14")

    result = db.get_skill_category_counts(user_id, project_id, top_n=4)

    assert result == [("Redis", 1)]


def test_skill_category_counts_scoped_to_project(user_id):
    project_a = db.create_project(user_id, "A", "2023-02-01")
    project_b = db.create_project(user_id, "B", "2023-02-01")
    db.save_card(user_id, project_a, _make_parsed(skill_tags=["Redis"]), "2023-02-14")
    db.save_card(user_id, project_b, _make_parsed(skill_tags=["결제시스템"]), "2023-02-14")

    result = db.get_skill_category_counts(user_id, project_a)

    assert result == [("Redis", 1)]
