"""Track A 담당: build_resume()에 대한 테스트.

_call_llm()을 모킹해서 실제 API 호출 없이 병합/환각방지 로직을 검증한다.
tasks/track-a-prompt-engine.md의 필수 테스트 표를 그대로 따른다.

**구현 노트 (9/14, ID 기반 매칭으로 전환)**: 모킹된 LLM 응답은 이제 `source_dates`
대신 `source_indices`(프롬프트의 [번호], 카드 순번과 동일한 1-based 정수)를 쓴다.
`source_dates`는 더 이상 LLM 응답에 안 실어도 된다 — 검증된 index로부터 백엔드가
계산하기 때문.
"""
import json

import pytest
from unittest.mock import patch

from src.parsing import resume
from src.parsing.resume import EnhancedItem, StarItem, build_resume, enhance_resume_items
from src.storage.db import Card


def _card(id, created_at, refined_sentence, skill_tags=None, raw_text="", project_id=1) -> Card:
    return Card(
        id=id,
        project_id=project_id,
        raw_text=raw_text or refined_sentence,
        refined_sentence=refined_sentence,
        skill_tags=skill_tags or [],
        confidence=0.9,
        created_at=created_at,
    )


def _llm_json(items: list[dict]) -> str:
    return json.dumps({"items": items}, ensure_ascii=False)


def test_build_resume_empty_cards_returns_empty_list():
    assert build_resume([]) == []


def test_build_resume_merges_time_gap_pair():
    """조치(02.14)와 결과(03.02)가 시간이 떨어져 있어도 하나의 항목으로 병합돼야 한다."""
    cards = [
        _card(1, "2023-02-14", "결제 API 응답 지연을 해소하기 위해 Redis 캐싱 레이어를 도입함",
              ["Redis", "성능최적화", "결제시스템"]),
        _card(2, "2023-03-02", "Redis 캐싱 적용 이후 결제 오류율을 0.8%에서 0.3%로 개선함",
              ["성능최적화", "결제시스템", "모니터링"]),
    ]
    mock_response = _llm_json([{
        "title": "결제 API 성능 개선",
        "period": "02.14 - 03.02",
        "situation": "결제 API 응답 지연 문제가 있었습니다.",
        "task": "응답 지연을 해소해야 했습니다.",
        "action": "Redis 캐싱 레이어를 도입했습니다.",
        "result": "결제 오류율을 0.8%에서 0.3%로 개선했습니다.",
        "source_indices": [1, 2],
    }])
    with patch("src.parsing.resume._call_llm", return_value=mock_response) as mock_llm:
        result = build_resume(cards)
        assert mock_llm.call_count == 1
        assert len(result) == 1
        assert result[0].source_dates == ["02.14", "03.02"]
        assert result[0].source_card_ids == [1, 2]
        assert "0.3%" in result[0].result


def test_build_resume_merges_despite_vocabulary_mismatch():
    """어휘가 겹치지 않아도 같은 작업 흐름이면 병합돼야 한다."""
    cards = [
        _card(1, "2023-02-14", "결제 API 응답 지연을 해소하기 위해 Redis 캐싱 레이어를 도입함"),
        _card(2, "2023-02-17", "쿠폰 중복 적용 버그를 식별하고 긴급 수정 사항을 배포함"),
        _card(3, "2023-03-02", "결제 오류율을 0.8%에서 0.3%로 개선함"),
    ]
    mock_response = _llm_json([{
        "title": "결제 API 성능 및 안정성 개선",
        "period": "02.14 - 03.02",
        "situation": "결제 시스템 안정성이 저하된 상황이었습니다.",
        "task": "응답 지연과 오류를 해소해야 했습니다.",
        "action": "Redis 캐싱을 도입하고 쿠폰 버그를 수정했습니다.",
        "result": "결제 오류율을 0.8%에서 0.3%로 개선했습니다.",
        "source_indices": [1, 2, 3],
    }])
    with patch("src.parsing.resume._call_llm", return_value=mock_response):
        result = build_resume(cards)
        assert len(result) == 1
        assert set(result[0].source_dates) == {"02.14", "02.17", "03.02"}
        assert set(result[0].source_card_ids) == {1, 2, 3}


def test_build_resume_no_number_leaves_result_empty():
    """기록에 숫자가 없으면 result를 빈 문자열로 남기고, 절대 지어내지 않는다."""
    cards = [_card(1, "2023-04-01", "신규 입사자 온보딩 문서를 작성함", ["문서작성", "온보딩"])]
    mock_response = _llm_json([{
        "title": "신규 입사자 온보딩 문서화",
        "period": "04.01",
        "situation": "체계적인 안내 자료가 부족한 상황이었습니다.",
        "task": "온보딩 과정을 표준화할 문서가 필요했습니다.",
        "action": "신규 입사자 온보딩 문서를 작성했습니다.",
        "result": "",
        "source_indices": [1],
    }])
    with patch("src.parsing.resume._call_llm", return_value=mock_response):
        result = build_resume(cards)
        assert result[0].result == ""


def test_build_resume_unrelated_cards_produce_separate_items():
    """서로 무관한 기록은 억지로 묶지 않고 별개의 항목으로 나온다."""
    cards = [
        _card(1, "2023-02-14", "결제 API에 Redis 캐싱 도입"),
        _card(2, "2023-05-01", "사내 CI 파이프라인을 개선함"),
    ]
    mock_response = _llm_json([
        {
            "title": "결제 API 성능 개선", "period": "02.14",
            "situation": "s", "task": "t", "action": "a", "result": "",
            "source_indices": [1],
        },
        {
            "title": "CI 파이프라인 개선", "period": "05.01",
            "situation": "s", "task": "t", "action": "a", "result": "",
            "source_indices": [2],
        },
    ])
    with patch("src.parsing.resume._call_llm", return_value=mock_response):
        result = build_resume(cards)
        assert len(result) == 2


def test_build_resume_splits_same_date_unrelated_cards_by_index():
    """9/14 실측 버그 재현 — 같은 날짜 카드 3장(2장 관련 + 1장 무관)이 LLM이 index로
    정확히 2개 항목으로 나눠 답했을 때, source_card_ids가 절대 안 섞여야 한다.

    날짜만으로 매칭했다면 전부 "09.14"라 하나로 뭉쳐졌을 상황 — ID 기반 매칭이 그
    구조적 버그를 실제로 고쳤는지 확인하는 핵심 테스트.
    """
    cards = [
        _card(10, "2026-09-14", "Redis를 활용하여 실시간 이체 시스템의 처리 속도를 향상시켰다",
              ["캐싱기술", "성능최적화"]),
        _card(11, "2026-09-14", "아웃박스 알림 상태를 저장하여 데이터 정합성을 유지함",
              ["데이터관리", "정합성유지"]),
        _card(12, "2026-09-14", "Redis를 이체 기능에 통합해 오류 감소율 90%, 성능 10배 개선",
              ["성능최적화", "오류관리"]),
    ]
    mock_response = _llm_json([
        {
            "title": "실시간 이체 시스템 성능 개선", "period": "09.14",
            "situation": "s", "task": "t", "action": "a",
            "result": "오류 감소율 90%, 성능 10배 개선",
            "source_indices": [1, 3],
        },
        {
            "title": "알림 데이터 정합성 개선", "period": "09.14",
            "situation": "s", "task": "t", "action": "a", "result": "",
            "source_indices": [2],
        },
    ])
    with patch("src.parsing.resume._call_llm", return_value=mock_response):
        result = build_resume(cards)

        assert len(result) == 2
        assert result[0].source_card_ids == [10, 12]
        assert result[1].source_card_ids == [11]
        # 두 그룹의 카드가 겹치면 안 된다 — 날짜만으로 매칭했다면 실패했을 조건.
        assert set(result[0].source_card_ids).isdisjoint(result[1].source_card_ids)


def test_build_resume_filters_hallucinated_source_indices():
    """LLM이 입력에 없는 번호를 지어내도 최종 결과에는 절대 남지 않는다."""
    cards = [_card(1, "2023-02-14", "결제 API에 Redis 캐싱 도입")]
    mock_response = _llm_json([{
        "title": "결제 API 성능 개선", "period": "02.14",
        "situation": "s", "task": "t", "action": "a", "result": "",
        "source_indices": [1, 99],  # 99는 카드가 1장뿐이라 존재하지 않는 지어낸 번호
    }])
    with patch("src.parsing.resume._call_llm", return_value=mock_response):
        result = build_resume(cards)
        assert result[0].source_dates == ["02.14"]
        assert result[0].source_card_ids == [1]


def test_build_resume_jd_text_changes_prompt():
    """jd_text가 주어지면 프롬프트에 포함돼 LLM 호출 내용이 달라진다."""
    cards = [_card(1, "2023-02-14", "결제 API에 Redis 캐싱 도입")]
    mock_response = _llm_json([{
        "title": "결제 API 성능 개선", "period": "02.14",
        "situation": "s", "task": "t", "action": "a", "result": "",
        "source_indices": [1],
    }])
    with patch("src.parsing.resume._call_llm", return_value=mock_response) as mock_llm:
        build_resume(cards, jd_text="백엔드 성능 최적화 경험자 우대")
        called_prompt = mock_llm.call_args[0][0]
        assert "백엔드 성능 최적화 경험자 우대" in called_prompt

    with patch("src.parsing.resume._call_llm", return_value=mock_response) as mock_llm:
        build_resume(cards)
        called_prompt = mock_llm.call_args[0][0]
        assert "채용 공고" not in called_prompt


def test_build_resume_retries_once_on_invalid_json_then_succeeds():
    cards = [_card(1, "2023-02-14", "결제 API에 Redis 캐싱 도입")]
    valid_response = _llm_json([{
        "title": "결제 API 성능 개선", "period": "02.14",
        "situation": "s", "task": "t", "action": "a", "result": "",
        "source_indices": [1],
    }])
    with patch("src.parsing.resume._call_llm", side_effect=["이건 JSON이 아님", valid_response]) as mock_llm:
        result = build_resume(cards)
        assert mock_llm.call_count == 2
        assert len(result) == 1


def test_build_resume_raises_after_two_consecutive_failures():
    cards = [_card(1, "2023-02-14", "결제 API에 Redis 캐싱 도입")]
    with patch("src.parsing.resume._call_llm", return_value="이건 JSON이 아님") as mock_llm:
        with pytest.raises(json.JSONDecodeError):
            build_resume(cards)
        assert mock_llm.call_count == 2


def test_build_resume_strips_markdown_code_fence():
    """LLM이 JSON을 ```json ... ``` 코드 펜스로 감싸서 반환해도 정상 파싱해야 한다.

    9/14 실측 재현: /resume에서 "경력기술서 만들기"를 눌렀을 때 Claude가 실제로 이
    형태로 응답해서 json.loads()가 죽고 POST /api/resume이 500이 되는 걸 확인했다
    (src/parsing/parser.py의 _strip_code_fence를 여기서도 재사용해서 고침).
    """
    cards = [_card(1, "2023-02-14", "결제 API에 Redis 캐싱 도입")]
    valid_response = _llm_json([{
        "title": "결제 API 성능 개선", "period": "02.14",
        "situation": "s", "task": "t", "action": "a", "result": "",
        "source_indices": [1],
    }])
    fenced = "```json\n" + valid_response + "\n```"
    with patch("src.parsing.resume._call_llm", return_value=fenced) as mock_llm:
        result = build_resume(cards)
        assert mock_llm.call_count == 1  # 재시도 없이 첫 시도에 바로 성공해야 함
        assert len(result) == 1
        assert result[0].source_card_ids == [1]


# --- enhance_resume_items() — "기존 경력기술서 붙여넣기 → Before/After 대조" (9/15 신규) ---


def _enhance_llm_json(items: list[dict]) -> str:
    return json.dumps({"items": items}, ensure_ascii=False)


def test_enhance_resume_items_empty_existing_items_returns_empty_list():
    cards = [_card(1, "2023-02-14", "결제 API에 Redis 캐싱 도입")]
    assert enhance_resume_items([], cards) == []
    assert enhance_resume_items(["   "], cards) == []  # 공백만 있는 줄은 제거됨


def test_enhance_resume_items_no_cards_returns_original_unchanged():
    result = enhance_resume_items(["결제 API 성능 개선 담당"], [])
    assert result == [EnhancedItem(original="결제 API 성능 개선 담당", enhanced="결제 API 성능 개선 담당")]


def test_enhance_resume_items_merges_matched_cards():
    cards = [
        _card(12, "2023-02-14", "결제 API 응답 지연을 해소하기 위해 Redis 캐싱 레이어를 도입함",
              ["Redis", "성능최적화"]),
        _card(13, "2023-02-18", "Redis 캐싱 적용 이후 결제 오류율을 0.8%에서 0.3%로 개선함",
              ["성능최적화", "모니터링"]),
    ]
    mock_response = _enhance_llm_json([{
        "item_index": 1,
        "enhanced": "Redis 캐싱 레이어 도입으로 결제 API 응답 지연을 해소하고 오류율을 0.8%에서 0.3%로 개선했습니다.",
        "gap_comment": "왜 Redis를 골랐는지가 없어요.",
        "source_indices": [1, 2],
    }])
    with patch("src.parsing.resume._call_llm", return_value=mock_response) as mock_llm:
        result = enhance_resume_items(["결제 API 성능 개선 담당"], cards)
        # enhance는 별도 시스템 프롬프트를 명시적으로 넘겨야 한다 (build_resume과 공유 X)
        assert mock_llm.call_args[0][1] == resume._ENHANCE_SYSTEM_PROMPT

    assert len(result) == 1
    assert result[0].original == "결제 API 성능 개선 담당"
    assert "0.3%" in result[0].enhanced
    assert result[0].gap_comment == "왜 Redis를 골랐는지가 없어요."
    assert result[0].source_dates == ["02.14", "02.18"]
    assert result[0].source_card_ids == [12, 13]


def test_enhance_resume_items_no_match_keeps_original_and_ignores_llm_text():
    """근거 카드가 없으면 LLM이 뭐라고 답했든 원문 그대로 유지한다 (2.2 원칙)."""
    cards = [_card(1, "2023-05-01", "사내 CI 파이프라인을 개선함")]
    mock_response = _enhance_llm_json([{
        "item_index": 1,
        "enhanced": "이건 근거 없이 지어낸 보강 문장입니다.",
        "gap_comment": "",
        "source_indices": [],
    }])
    with patch("src.parsing.resume._call_llm", return_value=mock_response):
        result = enhance_resume_items(["신규 회원 온보딩 플로우 기획"], cards)

    assert result[0].original == "신규 회원 온보딩 플로우 기획"
    assert result[0].enhanced == "신규 회원 온보딩 플로우 기획"
    assert result[0].source_card_ids == []


def test_enhance_resume_items_filters_hallucinated_source_indices():
    cards = [_card(1, "2023-02-14", "결제 API에 Redis 캐싱 도입")]
    mock_response = _enhance_llm_json([{
        "item_index": 1,
        "enhanced": "보강된 문장",
        "gap_comment": "",
        "source_indices": [1, 99],  # 99는 카드가 1장뿐이라 존재하지 않는 지어낸 번호
    }])
    with patch("src.parsing.resume._call_llm", return_value=mock_response):
        result = enhance_resume_items(["결제 API 성능 개선 담당"], cards)

    assert result[0].source_card_ids == [1]


def test_enhance_resume_items_missing_response_entry_falls_back_to_original():
    """LLM이 특정 item_index에 대해 아예 답하지 않아도 그 문장은 원문 그대로 반환된다."""
    cards = [_card(1, "2023-02-14", "결제 API에 Redis 캐싱 도입")]
    mock_response = _enhance_llm_json([{
        "item_index": 1,
        "enhanced": "보강된 문장",
        "gap_comment": "",
        "source_indices": [1],
    }])
    with patch("src.parsing.resume._call_llm", return_value=mock_response):
        result = enhance_resume_items(
            ["결제 API 성능 개선 담당", "신규 회원 온보딩 플로우 기획"], cards
        )

    assert len(result) == 2
    assert result[1].original == "신규 회원 온보딩 플로우 기획"
    assert result[1].enhanced == "신규 회원 온보딩 플로우 기획"


def test_enhance_resume_items_retries_once_on_invalid_json_then_succeeds():
    cards = [_card(1, "2023-02-14", "결제 API에 Redis 캐싱 도입")]
    valid_response = _enhance_llm_json([{
        "item_index": 1, "enhanced": "보강된 문장", "gap_comment": "", "source_indices": [1],
    }])
    with patch(
        "src.parsing.resume._call_llm", side_effect=["이건 JSON이 아님", valid_response]
    ) as mock_llm:
        result = enhance_resume_items(["결제 API 성능 개선 담당"], cards)
        assert mock_llm.call_count == 2
        assert len(result) == 1


def test_enhance_resume_items_strips_markdown_code_fence():
    cards = [_card(1, "2023-02-14", "결제 API에 Redis 캐싱 도입")]
    valid_response = _enhance_llm_json([{
        "item_index": 1, "enhanced": "보강된 문장", "gap_comment": "", "source_indices": [1],
    }])
    fenced = "```json\n" + valid_response + "\n```"
    with patch("src.parsing.resume._call_llm", return_value=fenced) as mock_llm:
        result = enhance_resume_items(["결제 API 성능 개선 담당"], cards)
        assert mock_llm.call_count == 1
        assert result[0].source_card_ids == [1]
