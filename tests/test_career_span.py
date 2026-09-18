"""총 경력 계산 테스트 (9/18 신규 — Figma "00 · 온보딩" 3/4 "어디서 얼마나 일하셨어요?").

핵심은 **겹치는 기간을 두 번 세지 않는 것**이다. 경력기술서는 면접에서 검증당하는
문서라 부풀려진 연차가 나가면 안 된다(CLAUDE.md 2.2).
"""
from unittest.mock import patch

import pytest

from src.career_span import format_span, to_years_segment, total_months


@pytest.fixture(autouse=True)
def _fixed_today():
    """"재직 중"(종료 None) 계산이 오늘 날짜에 의존하므로 고정한다."""
    from datetime import datetime

    with patch("src.career_span.now_local", return_value=datetime(2026, 9, 18)):
        yield


def test_single_closed_period_counts_both_end_months():
    # 2024.03 ~ 2024.03 은 1개월 (같은 달에 입/퇴사)
    assert total_months([("2024-03", "2024-03")]) == 1
    # 2024.01 ~ 2024.12 는 12개월
    assert total_months([("2024-01", "2024-12")]) == 12


def test_open_period_runs_to_today():
    # 2024.03 ~ 오늘(2026.09) = 2024.03~2026.09 포함 = 31개월
    assert total_months([("2024-03", None)]) == 31


def test_dotted_format_is_accepted():
    """Figma 목업이 "2024.03"으로 쓰고, 프론트도 그 표기를 그대로 보낼 수 있다."""
    assert total_months([("2024.03", "2024.12")]) == total_months([("2024-03", "2024-12")])


def test_overlapping_periods_are_counted_once():
    """2020.01~2021.06(18개월)과 2020.07~2021.12(18개월)은 1년이 겹친다.

    그냥 더하면 36개월이지만 실제로 일한 기간은 2020.01~2021.12로 24개월이다.
    """
    assert total_months([("2020-01", "2021-06")]) == 18
    assert total_months([("2020-07", "2021-12")]) == 18
    assert total_months([("2020-01", "2021-06"), ("2020-07", "2021-12")]) == 24


def test_adjacent_periods_merge_without_gap():
    """3월 퇴사 → 4월 입사는 공백 없이 이어진 경력이다."""
    assert total_months([("2020-01", "2020-03"), ("2020-04", "2020-06")]) == 6


def test_gap_between_periods_is_not_counted():
    # 2020.01~2020.03(3) + 2021.01~2021.03(3) = 6, 사이 공백 9개월은 안 센다
    assert total_months([("2020-01", "2020-03"), ("2021-01", "2021-03")]) == 6


def test_malformed_and_reversed_periods_are_dropped():
    assert total_months([("", None)]) == 0
    assert total_months([("2024-13", "2024-14")]) == 0
    assert total_months([("2024-12", "2024-01")]) == 0  # 끝이 시작보다 앞
    assert total_months([("잘못된값", "2024-01")]) == 0


def test_empty_input():
    assert total_months([]) == 0


@pytest.mark.parametrize(
    "months, expected",
    [
        (0, None),
        (1, "1-3"),
        (47, "1-3"),  # 3년 11개월
        (48, "4-6"),  # 4년
        (83, "4-6"),
        (84, "7-10"),  # 7년
        (119, "7-10"),
        (120, "10+"),  # 10년
        (300, "10+"),
    ],
)
def test_years_segment_mapping(months, expected):
    assert to_years_segment(months) == expected


@pytest.mark.parametrize(
    "months, expected",
    [(0, "0개월"), (3, "3개월"), (12, "1년"), (75, "6년 3개월")],
)
def test_format_span(months, expected):
    assert format_span(months) == expected
