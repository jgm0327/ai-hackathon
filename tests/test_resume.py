"""Track A 담당: build_resume()에 대한 테스트.

_call_llm()을 모킹해서 실제 API 호출 없이 병합/환각방지 로직을 검증한다.
tasks/track-a-prompt-engine.md의 필수 테스트 표를 그대로 따른다.
"""
import json

import pytest
from unittest.mock import patch

from src.parsing.resume import StarItem, build_resume
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
        "source_dates": ["02.14", "03.02"],
    }])
    with patch("src.parsing.resume._call_llm", return_value=mock_response) as mock_llm:
        result = build_resume(cards)
        assert mock_llm.call_count == 1
        assert len(result) == 1
        assert result[0].source_dates == ["02.14", "03.02"]
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
        "source_dates": ["02.14", "02.17", "03.02"],
    }])
    with patch("src.parsing.resume._call_llm", return_value=mock_response):
        result = build_resume(cards)
        assert len(result) == 1
        assert set(result[0].source_dates) == {"02.14", "02.17", "03.02"}


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
        "source_dates": ["04.01"],
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
            "source_dates": ["02.14"],
        },
        {
            "title": "CI 파이프라인 개선", "period": "05.01",
            "situation": "s", "task": "t", "action": "a", "result": "",
            "source_dates": ["05.01"],
        },
    ])
    with patch("src.parsing.resume._call_llm", return_value=mock_response):
        result = build_resume(cards)
        assert len(result) == 2


def test_build_resume_filters_hallucinated_source_dates():
    """LLM이 입력에 없는 날짜를 지어내도 최종 source_dates에는 절대 남지 않는다."""
    cards = [_card(1, "2023-02-14", "결제 API에 Redis 캐싱 도입")]
    mock_response = _llm_json([{
        "title": "결제 API 성능 개선", "period": "02.14",
        "situation": "s", "task": "t", "action": "a", "result": "",
        "source_dates": ["02.14", "99.99"],  # 99.99는 입력에 없는 지어낸 날짜
    }])
    with patch("src.parsing.resume._call_llm", return_value=mock_response):
        result = build_resume(cards)
        assert result[0].source_dates == ["02.14"]
        assert "99.99" not in result[0].source_dates


def test_build_resume_jd_text_changes_prompt():
    """jd_text가 주어지면 프롬프트에 포함돼 LLM 호출 내용이 달라진다."""
    cards = [_card(1, "2023-02-14", "결제 API에 Redis 캐싱 도입")]
    mock_response = _llm_json([{
        "title": "결제 API 성능 개선", "period": "02.14",
        "situation": "s", "task": "t", "action": "a", "result": "",
        "source_dates": ["02.14"],
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
        "source_dates": ["02.14"],
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
