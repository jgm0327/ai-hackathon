"""앱 기준 시각 헬퍼 — Track B (9/17 신규).

**왜 필요한가**: 이 앱에는 "사람이 사는 시간대"에 묶인 값이 두 종류 있다.

1. 퇴근 알림 시각 — 유저가 "18:00"이라고 입력하면 그건 당연히 한국 시간 18시다.
2. 카드의 "오늘" — 홈 화면 "오늘 남긴 것", `/stack` 주간 스트릭이 전부 날짜 문자열
   비교에 의존한다.

둘 다 `datetime.now()`(서버 로컬 시간)로 계산하고 있었는데, 이러면 코드가 도는 곳에
따라 결과가 달라진다. 실제로 GitHub Actions 러너는 UTC라 퇴근 알림이 9시간 어긋난
시각에 발송되고 있었다(9/17 발견). OCI VM도 기본이 UTC라 그대로 배포하면 카드의
"오늘"이 한국시간 09:00에 바뀌는 문제까지 생긴다.

그래서 시간대를 서버 환경에 맡기지 않고 `settings.app_timezone`으로 못박는다 —
로컬(Windows, KST)이든 CI(UTC)든 OCI(UTC)든 동일하게 동작한다.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.config import settings


def app_tz() -> ZoneInfo:
    return ZoneInfo(settings.app_timezone)


def now_local() -> datetime:
    """앱 기준 시간대의 현재 시각 (timezone-aware)."""
    return datetime.now(app_tz())


def today_local() -> date:
    """앱 기준 시간대의 오늘 날짜. 카드 `created_at`이 이 값을 쓴다."""
    return now_local().date()
