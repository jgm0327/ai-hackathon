"""Track A 담당: parse_note()에 대한 스냅샷 테스트.

_call_llm()을 모킹해서 실제 API 호출 없이 파싱 로직(JSON 파싱, 재시도)을 검증한다.
"""
import json

import pytest
from unittest.mock import patch

from src.parsing.parser import ParsedEntry, parse_note

MOCK_RESPONSES = {
    "결제 터진 거 막음": '{"refined_sentence": "결제 시스템 장애를 신속히 감지하고 대응함", "skill_tags": ["장애대응", "결제시스템"], "confidence": 0.85}',
    "오늘 좀 바빴음": '{"refined_sentence": "특정 업무 내용을 확인할 수 없음", "skill_tags": [], "confidence": 0.1}',
    "결제 버그 고치고 나서 API 문서도 정리하고 회의도 들어감": '{"refined_sentence": "결제 모듈의 소프트웨어 결함을 식별하고 수정함", "skill_tags": ["버그수정", "결제시스템"], "confidence": 0.7}',
}


def test_parse_note_basic():
    with patch("src.parsing.parser._call_llm", return_value=MOCK_RESPONSES["결제 터진 거 막음"]):
        result = parse_note("결제 터진 거 막음")
        assert isinstance(result, ParsedEntry)
        assert "장애대응" in result.skill_tags
        assert result.confidence > 0.5


def test_parse_note_ambiguous_low_confidence():
    with patch("src.parsing.parser._call_llm", return_value=MOCK_RESPONSES["오늘 좀 바빴음"]):
        result = parse_note("오늘 좀 바빴음")
        assert result.confidence <= 0.5
        assert result.skill_tags == []


def test_parse_note_multi_event_picks_core_event():
    """여러 사건이 섞인 입력은 가장 핵심적인 사건 하나만 정제해야 한다."""
    raw_text = "결제 버그 고치고 나서 API 문서도 정리하고 회의도 들어감"
    with patch("src.parsing.parser._call_llm", return_value=MOCK_RESPONSES[raw_text]):
        result = parse_note(raw_text)
        assert "결제" in result.refined_sentence
        assert "버그수정" in result.skill_tags
        # 부수적으로 언급된 사건("문서 정리", "회의")은 핵심 태그로 뽑히지 않아야 한다.
        assert "문서정리" not in result.skill_tags


def test_parse_note_retries_once_on_invalid_json_then_succeeds():
    """첫 응답이 JSON 파싱에 실패하면 1회 재시도하고, 재시도가 성공하면 정상 반환한다."""
    responses = ["이건 JSON이 아님", MOCK_RESPONSES["결제 터진 거 막음"]]
    with patch("src.parsing.parser._call_llm", side_effect=responses) as mock_llm:
        result = parse_note("결제 터진 거 막음")
        assert mock_llm.call_count == 2
        assert result.skill_tags == ["장애대응", "결제시스템"]


def test_parse_note_raises_after_two_consecutive_failures():
    """JSON 파싱이 2회 연속 실패하면(최초 시도 + 재시도 1회) 예외를 발생시킨다."""
    with patch("src.parsing.parser._call_llm", return_value="이건 JSON이 아님") as mock_llm:
        with pytest.raises(json.JSONDecodeError):
            parse_note("결제 터진 거 막음")
        assert mock_llm.call_count == 2
