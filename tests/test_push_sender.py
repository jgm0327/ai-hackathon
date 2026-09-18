"""send_due_reminders() 테스트 (9/17 신규) — 시간대 + 중복 방지.

이 두 가지는 실서버에서 조용히 깨지는 종류의 버그라 테스트로 고정해둔다.

- **시간대**: 이전 코드는 `datetime.now()`(서버 로컬 시간)로 계산해서, UTC 환경
  (GitHub Actions 러너, OCI VM 기본값)에서는 유저가 KST로 입력한 퇴근 시각이
  9시간 어긋난 시점에 발송됐다. 실제로 알림이 안 오던 원인 중 하나.
- **중복 방지**: 스케줄러가 1분마다 도는데 발송 윈도는 5분이라, 기록이 없으면
  같은 알림이 5번 나간다.

시각은 `src.push.push_sender.now_local`을 직접 패치해서 고정한다 — 실제 시계에
의존하면 테스트가 하루 중 언제 도는지에 따라 붙었다 떨어졌다 한다.
"""
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from src.push.push_sender import send_due_reminders

KST = ZoneInfo("Asia/Seoul")


def _at(hour: int, minute: int) -> datetime:
    """2026-09-17 해당 시각(KST)."""
    return datetime(2026, 9, 17, hour, minute, tzinfo=KST)


def _subs(leave_time: str = "18:00", last_sent_date: str | None = None) -> dict:
    entry = {"subscription": {"endpoint": "https://example.test/ep"}, "leave_time": leave_time}
    if last_sent_date:
        entry["last_sent_date"] = last_sent_date
    return {"user-key-1": entry}


@pytest.fixture
def push_env():
    """발송/저장 부수효과를 막고 호출만 기록한다."""
    with patch("src.push.push_sender.send_push") as send, patch(
        "src.push.push_sender.mark_reminder_sent"
    ) as mark:
        yield send, mark


# --- 시간대 ---


def test_sends_at_15min_before_leave_time_in_app_timezone(push_env):
    """퇴근 18:00이면 KST 17:45에 발송된다."""
    send, _ = push_env
    with patch("src.push.push_sender.now_local", return_value=_at(17, 45)):
        with patch("src.push.push_sender.list_subscriptions", return_value=_subs("18:00")):
            assert send_due_reminders() == 1
    send.assert_called_once()


def test_does_not_send_outside_window(push_env):
    """윈도(17:45~17:50) 밖에서는 안 보낸다."""
    send, _ = push_env
    for hour, minute in [(17, 44), (17, 50), (18, 0), (9, 0)]:
        with patch("src.push.push_sender.now_local", return_value=_at(hour, minute)):
            with patch("src.push.push_sender.list_subscriptions", return_value=_subs("18:00")):
                assert send_due_reminders() == 0, f"{hour}:{minute}에 발송되면 안 됨"
    send.assert_not_called()


def test_utc_server_time_does_not_shift_send_time(push_env):
    """서버가 UTC여도 발송 시점은 KST 기준으로 유지된다.

    9/17 실제 버그 재현: 이전 구현은 `datetime.now()`를 썼기 때문에 UTC 러너에서
    "17:45"를 UTC로 해석해 KST 02:45에 발송했다. now_local()이 시간대를 고정하므로
    UTC 08:45(=KST 17:45)에 정상 발송돼야 한다.
    """
    send, _ = push_env
    utc_now = datetime(2026, 9, 17, 8, 45, tzinfo=ZoneInfo("UTC"))
    # now_local()은 앱 시간대(KST)로 변환된 값을 돌려준다 — 같은 순간을 가리킨다.
    with patch("src.push.push_sender.now_local", return_value=utc_now.astimezone(KST)):
        with patch("src.push.push_sender.list_subscriptions", return_value=_subs("18:00")):
            assert send_due_reminders() == 1
    send.assert_called_once()


# --- 중복 방지 ---


def test_skips_user_already_sent_today(push_env):
    send, _ = push_env
    subs = _subs("18:00", last_sent_date="2026-09-17")
    with patch("src.push.push_sender.now_local", return_value=_at(17, 45)):
        with patch("src.push.push_sender.list_subscriptions", return_value=subs):
            assert send_due_reminders() == 0
    send.assert_not_called()


def test_yesterdays_record_does_not_block_today(push_env):
    """어제 보낸 기록은 오늘 발송을 막지 않는다."""
    send, _ = push_env
    subs = _subs("18:00", last_sent_date="2026-09-16")
    with patch("src.push.push_sender.now_local", return_value=_at(17, 45)):
        with patch("src.push.push_sender.list_subscriptions", return_value=subs):
            assert send_due_reminders() == 1
    send.assert_called_once()


def test_marks_sent_with_today_date(push_env):
    send, mark = push_env
    with patch("src.push.push_sender.now_local", return_value=_at(17, 45)):
        with patch("src.push.push_sender.list_subscriptions", return_value=_subs("18:00")):
            send_due_reminders()
    mark.assert_called_once_with("user-key-1", "2026-09-17")


def test_repeated_ticks_within_window_send_only_once(push_env):
    """스케줄러가 1분마다 도는 실제 상황 — 윈도 안에서 5번 돌아도 발송은 1회.

    중복 방지가 없으면 여기서 5번 발송된다(기존 코드의 TODO였던 문제).
    """
    send, _ = push_env
    state = _subs("18:00")

    def fake_mark(user_id, date_str):
        state[user_id]["last_sent_date"] = date_str

    with patch("src.push.push_sender.mark_reminder_sent", side_effect=fake_mark):
        for minute in range(45, 50):  # 17:45 ~ 17:49
            with patch("src.push.push_sender.now_local", return_value=_at(17, minute)):
                with patch("src.push.push_sender.list_subscriptions", return_value=state):
                    send_due_reminders()

    assert send.call_count == 1


# --- 견고성 ---


def test_malformed_leave_time_does_not_block_other_users(push_env):
    """한 유저의 값이 깨져도 나머지는 정상 발송된다."""
    send, _ = push_env
    subs = {
        "broken": {"subscription": {"endpoint": "x"}, "leave_time": "이상한값"},
        "ok": {"subscription": {"endpoint": "y"}, "leave_time": "18:00"},
    }
    with patch("src.push.push_sender.now_local", return_value=_at(17, 45)):
        with patch("src.push.push_sender.list_subscriptions", return_value=subs):
            assert send_due_reminders() == 1
    send.assert_called_once()


# --- 주말 제외 (9/18 신규, Figma 온보딩 4/4 "주말에는 쉬어요") ---


def test_skip_weekends_blocks_saturday_send():
    """토요일엔 보내지 않는다."""
    saturday = datetime(2026, 9, 19, 17, 45, tzinfo=KST)  # 2026-09-19는 토요일
    assert saturday.weekday() == 5
    entry = {
        "subscription": {"endpoint": "e"},
        "leave_time": "18:00",
        "skip_weekends": True,
    }
    with (
        patch("src.push.push_sender.list_subscriptions", return_value={"u1": entry}),
        patch("src.push.push_sender.now_local", return_value=saturday),
        patch("src.push.push_sender.send_push") as mock_send,
        patch("src.push.push_sender.mark_reminder_sent"),
    ):
        assert send_due_reminders() == 0
    assert mock_send.call_count == 0


def test_skip_weekends_still_sends_on_weekday():
    friday = datetime(2026, 9, 18, 17, 45, tzinfo=KST)  # 금요일
    assert friday.weekday() == 4
    entry = {
        "subscription": {"endpoint": "e"},
        "leave_time": "18:00",
        "skip_weekends": True,
    }
    with (
        patch("src.push.push_sender.list_subscriptions", return_value={"u1": entry}),
        patch("src.push.push_sender.now_local", return_value=friday),
        patch("src.push.push_sender.send_push") as mock_send,
        patch("src.push.push_sender.mark_reminder_sent"),
    ):
        assert send_due_reminders() == 1
    assert mock_send.call_count == 1


def test_legacy_entry_without_flag_still_sends_on_weekend():
    """켠 적 없는 설정을 기존 구독에 소급 적용하지 않는다."""
    saturday = datetime(2026, 9, 19, 17, 45, tzinfo=KST)
    entry = {"subscription": {"endpoint": "e"}, "leave_time": "18:00"}  # 플래그 없음
    with (
        patch("src.push.push_sender.list_subscriptions", return_value={"u1": entry}),
        patch("src.push.push_sender.now_local", return_value=saturday),
        patch("src.push.push_sender.send_push"),
        patch("src.push.push_sender.mark_reminder_sent"),
    ):
        assert send_due_reminders() == 1
