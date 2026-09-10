"""Track A 담당: parse_note()에 대한 스냅샷 테스트.

_call_llm()을 모킹해서 실제 API 호출 없이 파싱 로직(JSON 파싱, 재시도)을 검증한다.
"""
from unittest.mock import patch

from src.parsing.parser import ParsedEntry, parse_note

MOCK_RESPONSES = {
    "결제 터진 거 막음": '{"refined_sentence": "결제 시스템 장애를 신속히 감지하고 대응함", "skill_tags": ["장애대응", "결제시스템"], "confidence": 0.85}',
    "오늘 좀 바빴음": '{"refined_sentence": "특정 업무 내용을 확인할 수 없음", "skill_tags": [], "confidence": 0.1}',
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


# TODO(Track A): 아래 케이스 추가
# - 다중 사건이 섞인 입력
# - JSON 파싱 실패 후 재시도 성공 케이스
# - JSON 파싱 2회 연속 실패 시 예외 발생 케이스
