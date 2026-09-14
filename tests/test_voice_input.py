"""Track F 담당: handle_pending_voice_entry()의 디코딩/파이프라인 연결 테스트.

SpeechRecognition 자체는 브라우저 JS라 단위 테스트 대상이 아니고, 여기서는
쿼리 파라미터 디코딩 → run_pipeline() 호출 → 정리(pop) 로직만 검증한다.
"""
import base64
from unittest.mock import MagicMock, patch

import pytest

from src.frontend.components import voice_input


class _FakeQueryParams(dict):
    """st.query_params 흉내 — .get()/.pop()만 있으면 충분하다."""

    def pop(self, key, default=None):
        return dict.pop(self, key, default)


@pytest.fixture
def fake_st(monkeypatch):
    fake = MagicMock()
    fake.query_params = _FakeQueryParams()
    fake.spinner.return_value.__enter__ = MagicMock(return_value=None)
    fake.spinner.return_value.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr(voice_input, "st", fake)
    return fake


def _encode(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def test_returns_none_when_no_voice_text_param(fake_st):
    assert voice_input.handle_pending_voice_entry() is None


def test_decodes_and_calls_run_pipeline(fake_st):
    fake_st.query_params["voice_text"] = _encode("결제 버그 고치고 옴")
    fake_result = {"parsed": "x", "matched_jds": []}

    with patch.object(voice_input, "run_pipeline", return_value=fake_result) as mock_pipeline:
        result = voice_input.handle_pending_voice_entry()

    mock_pipeline.assert_called_once_with("결제 버그 고치고 옴")
    assert result == fake_result
    assert "voice_text" not in fake_st.query_params  # 재처리 방지를 위해 정리돼야 함


def test_empty_text_returns_none_without_calling_pipeline(fake_st):
    fake_st.query_params["voice_text"] = _encode("   ")

    with patch.object(voice_input, "run_pipeline") as mock_pipeline:
        result = voice_input.handle_pending_voice_entry()

    mock_pipeline.assert_not_called()
    assert result is None


def test_invalid_base64_handled_gracefully(fake_st):
    fake_st.query_params["voice_text"] = "not-valid-base64-!!!"

    with patch.object(voice_input, "run_pipeline") as mock_pipeline:
        result = voice_input.handle_pending_voice_entry()

    mock_pipeline.assert_not_called()
    assert result is None
    assert "voice_text" not in fake_st.query_params
