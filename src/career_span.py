"""재직 이력에서 총 경력을 계산한다 (9/18 신규).

Figma "00 · 온보딩" 3/4 화면("어디서 얼마나 일하셨어요?")이 연차를 직접 묻지 않고
회사와 기간으로 계산한다 — 화면에도 "연차는 여기서 자동으로 계산해요. 따로 묻지
않을게요"라고 적혀 있다.

**겹치는 기간은 한 번만 센다.** 이직이 겹치거나 겸직한 이력을 그냥 더하면 실제보다
긴 경력이 나오는데, 경력기술서는 면접에서 검증당하는 문서라(CLAUDE.md 2.2) 여기서
부풀려진 숫자가 나가면 안 된다. 그래서 기간을 병합한 뒤 센다.

이 계산은 서버가 한다 — 화면이 보여주는 "6년 3개월"과 저장되는 연차 구간이 갈라지지
않게 하려면 한 곳에서만 정해야 하고, 저장되는 쪽이 그 한 곳이다.
"""
from __future__ import annotations

from src.timeutil import now_local


def _to_month_index(year_month: str) -> int | None:
    """"2024-03" 또는 "2024.03" -> 절대 월 번호. 형식이 아니면 None.

    월 번호로 바꿔두면 연/월 경계를 신경 쓰지 않고 빼기만으로 기간을 잴 수 있다.
    """
    text = year_month.strip().replace(".", "-")
    parts = text.split("-")
    if len(parts) < 2:
        return None
    try:
        year, month = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (1 <= month <= 12) or not (1900 <= year <= 2999):
        return None
    return year * 12 + (month - 1)


def total_months(periods: list[tuple[str, str | None]]) -> int:
    """(시작, 종료) 목록에서 총 재직 개월 수. 종료가 None이면 "지금까지"로 본다.

    시작이 종료보다 뒤인 항목과 형식이 깨진 항목은 조용히 버린다 — 온보딩 입력 중
    잠깐 나오는 중간 상태이지 에러로 막을 일이 아니다.
    """
    today = now_local()
    current = today.year * 12 + (today.month - 1)

    spans: list[tuple[int, int]] = []
    for started_at, ended_at in periods:
        start = _to_month_index(started_at)
        if start is None:
            continue
        end = current if not ended_at else _to_month_index(ended_at)
        if end is None or end < start:
            continue
        spans.append((start, end))

    if not spans:
        return 0

    # 겹치는 구간 병합 — 시작월 기준으로 정렬한 뒤 이어붙인다.
    spans.sort()
    merged: list[list[int]] = [list(spans[0])]
    for start, end in spans[1:]:
        last = merged[-1]
        # 끝난 달의 다음 달부터 시작하면 공백 없이 이어진 것으로 본다(3월 퇴사 → 4월 입사).
        if start <= last[1] + 1:
            last[1] = max(last[1], end)
        else:
            merged.append([start, end])

    # 시작월과 종료월을 둘 다 포함해서 센다 — "2024.03 ~ 2024.03"은 1개월이다.
    return sum(end - start + 1 for start, end in merged)


def to_years_segment(months: int) -> str | None:
    """총 개월 수를 기존 연차 구간("1-3"/"4-6"/"7-10"/"10+")으로 바꾼다.

    구간 자체는 그대로 둔다 — `Profile.years_segment`를 읽는 곳(경력기술서 제목 등)이
    이미 이 네 값을 전제하고 있어서, 표현을 바꾸면 그쪽까지 번진다. 새 온보딩은 사람에게
    "6년 3개월"을 보여주고, 저장은 이 구간으로 한다.
    """
    if months <= 0:
        return None
    years = months / 12
    if years < 4:
        return "1-3"
    if years < 7:
        return "4-6"
    if years < 10:
        return "7-10"
    return "10+"


def format_span(months: int) -> str:
    """"6년 3개월" (Figma 268:5769). 12개월 미만이면 개월만, 딱 떨어지면 년만."""
    if months <= 0:
        return "0개월"
    years, rest = divmod(months, 12)
    if years == 0:
        return f"{rest}개월"
    if rest == 0:
        return f"{years}년"
    return f"{years}년 {rest}개월"
