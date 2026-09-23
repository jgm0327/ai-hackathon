"""send_due_reminders() 테스트 (9/17 신규, 9/23 저장소 이전에 맞춰 재작성).

고정해두는 것들 — 전부 실서버에서 조용히 깨지는 종류다.

- **시간대**: 이전 코드는 `datetime.now()`(서버 로컬 시간)로 계산해서, UTC 환경
  (GitHub Actions 러너, OCI VM 기본값)에서는 유저가 KST로 입력한 퇴근 시각이
  9시간 어긋난 시점에 발송됐다.
- **중복 방지**: 스케줄러가 1분마다 도는데 발송 윈도는 5분이라, 기록이 없으면
  같은 알림이 5번 나간다.
- **기기 여러 대 (9/23 신규)**: 한 사람이 기기 3대를 등록했으면 알림은 3대 모두에
  가야 하지만 "오늘 보냈음"은 **한 번만** 기록돼야 한다. 기기 단위로 기록하면
  다음 틱에 아직 안 찍힌 기기로 또 나간다.
- **죽은 구독 정리 (9/23 신규)**: 410/404를 받은 구독은 그 자리에서 지운다.

시각은 `now_local`을 직접 패치해서 고정한다 — 실제 시계에 의존하면 테스트가 하루 중
언제 도는지에 따라 붙었다 떨어졌다 한다. 저장소는 conftest의 `_isolated_db`가 주는
임시 SQLite를 그대로 쓴다(모킹하지 않는다 — 실제 조회 경로까지 같이 검증된다).
"""
from datetime import datetime
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pytest

from src.push.push_sender import send_due_reminders, send_push
from src.storage import db

KST = ZoneInfo("Asia/Seoul")


def _at(hour: int, minute: int) -> datetime:
    """2026-09-17(목) 해당 시각(KST)."""
    return datetime(2026, 9, 17, hour, minute, tzinfo=KST)


@pytest.fixture
def user_id() -> int:
    return db.upsert_user(
        kakao_id="push-test", nickname="테스터", profile_image_url=None, now="2026-01-01T00:00:00"
    )


def _enable(user_id: int, leave_time="18:00", skip_weekends=False, devices=1) -> None:
    for i in range(devices):
        db.save_push_subscription(
            user_id, f"https://example.test/ep{i}", "p256dh", "auth", "2026-09-17T00:00:00"
        )
    db.save_push_settings(user_id, True, leave_time, skip_weekends)


@pytest.fixture
def sent():
    """실제 발송을 막고 호출만 기록한다."""
    with patch("src.push.push_sender.send_push", return_value=True) as mock:
        yield mock


# --- 시간대 ---


def test_sends_at_15min_before_leave_time_in_app_timezone(user_id, sent):
    """퇴근 18:00이면 KST 17:45에 발송된다."""
    _enable(user_id)
    with patch("src.push.push_sender.now_local", return_value=_at(17, 45)):
        assert send_due_reminders() == 1
    sent.assert_called_once()


def test_does_not_send_outside_window(user_id, sent):
    """윈도(17:45~17:50) 밖에서는 안 보낸다."""
    _enable(user_id)
    for hour, minute in [(17, 44), (17, 50), (18, 0), (9, 0)]:
        with patch("src.push.push_sender.now_local", return_value=_at(hour, minute)):
            assert send_due_reminders() == 0
    sent.assert_not_called()


def test_utc_server_time_does_not_shift_send_time(user_id, sent):
    """서버가 UTC여도 발송 시점은 KST 기준으로 유지된다.

    9/17 실제 버그 재현: 이전 구현은 `datetime.now()`를 썼기 때문에 UTC 러너에서
    "17:45"를 UTC로 해석해 KST 02:45에 발송했다.
    """
    _enable(user_id)
    utc_now = datetime(2026, 9, 17, 8, 45, tzinfo=ZoneInfo("UTC"))
    with patch("src.push.push_sender.now_local", return_value=utc_now.astimezone(KST)):
        assert send_due_reminders() == 1
    sent.assert_called_once()


# --- 중복 방지 ---


def test_skips_user_already_sent_today(user_id, sent):
    _enable(user_id)
    db.mark_push_sent(user_id, "2026-09-17")
    with patch("src.push.push_sender.now_local", return_value=_at(17, 45)):
        assert send_due_reminders() == 0
    sent.assert_not_called()


def test_yesterdays_record_does_not_block_today(user_id, sent):
    _enable(user_id)
    db.mark_push_sent(user_id, "2026-09-16")
    with patch("src.push.push_sender.now_local", return_value=_at(17, 45)):
        assert send_due_reminders() == 1
    sent.assert_called_once()


def test_marks_sent_with_today_date(user_id, sent):
    _enable(user_id)
    with patch("src.push.push_sender.now_local", return_value=_at(17, 45)):
        send_due_reminders()
    assert db.get_push_settings(user_id).last_sent_date == "2026-09-17"


def test_repeated_ticks_within_window_send_only_once(user_id, sent):
    """스케줄러가 1분마다 도는 실제 상황 — 윈도 안에서 5번 돌아도 발송은 1회."""
    _enable(user_id)
    for minute in range(45, 50):  # 17:45 ~ 17:49
        with patch("src.push.push_sender.now_local", return_value=_at(17, minute)):
            send_due_reminders()
    assert sent.call_count == 1


# --- 기기 여러 대 (9/23 신규) ---


def test_sends_to_every_device_of_the_user(user_id, sent):
    _enable(user_id, devices=3)
    with patch("src.push.push_sender.now_local", return_value=_at(17, 45)):
        assert send_due_reminders() == 3
    assert sent.call_count == 3


def test_multiple_devices_still_mark_sent_once(user_id, sent):
    """기기가 3대여도 다음 틱엔 아무 데도 안 간다 — 기록이 사람 단위라서."""
    _enable(user_id, devices=3)
    for minute in range(45, 50):
        with patch("src.push.push_sender.now_local", return_value=_at(17, minute)):
            send_due_reminders()
    assert sent.call_count == 3  # 첫 틱의 3대뿐


def test_settings_are_per_account_not_per_device(user_id, sent):
    """기기를 추가해도 설정은 한 벌이다.

    예전 구조(Upstash)에서는 구독마다 leave_time이 따로 들어 있어서 기기를 늘리면
    설정이 갈라졌다 — 실제로 한 계정에 17:42/18:00/18:00 세 벌이 쌓여 있었다.
    """
    _enable(user_id, leave_time="18:00", devices=1)
    db.save_push_subscription(
        user_id, "https://example.test/second", "p", "a", "2026-09-17T00:00:00"
    )
    db.save_push_settings(user_id, True, "19:00", False)

    with patch("src.push.push_sender.now_local", return_value=_at(17, 45)):
        assert send_due_reminders() == 0  # 옛 시각으로는 안 나간다
    with patch("src.push.push_sender.now_local", return_value=_at(18, 45)):
        assert send_due_reminders() == 2  # 새 시각으로 두 대 모두


# --- 꺼짐 상태 ---


def test_disabled_user_gets_nothing(user_id, sent):
    """알림을 끈 계정엔 보내지 않는다 — 신고받은 문제의 핵심."""
    _enable(user_id)
    db.delete_push_subscriptions_for_user(user_id)
    db.save_push_settings(user_id, False, "18:00", False)
    with patch("src.push.push_sender.now_local", return_value=_at(17, 45)):
        assert send_due_reminders() == 0
    sent.assert_not_called()


def test_enabled_but_no_device_is_not_a_recipient(user_id, sent):
    """보낼 곳이 없으면 대상이 아니다(마지막 기기를 지운 직후 등)."""
    db.save_push_settings(user_id, True, "18:00", False)
    with patch("src.push.push_sender.now_local", return_value=_at(17, 45)):
        assert send_due_reminders() == 0
    sent.assert_not_called()


# --- 견고성 ---


def test_malformed_leave_time_does_not_block_other_users(sent):
    """한 유저의 값이 깨져도 나머지는 정상 발송된다."""
    broken = db.upsert_user("broken", None, None, "2026-01-01T00:00:00")
    ok = db.upsert_user("ok", None, None, "2026-01-01T00:00:00")
    _enable(broken, leave_time="18:00")
    _enable(ok, leave_time="18:00")
    # 스키마(LEAVE_TIME_PATTERN)가 막는 값이지만 예전 데이터/직접 수정으로 들어올 수 있다.
    with db._connect() as conn:
        conn.execute(
            "UPDATE push_settings SET leave_time = ? WHERE user_id = ?", ("이상한값", broken)
        )

    with patch("src.push.push_sender.now_local", return_value=_at(17, 45)):
        assert send_due_reminders() == 1
    sent.assert_called_once()


# --- 주말 제외 (9/18, Figma 온보딩 4/4 "주말에는 쉬어요") ---


def test_skip_weekends_blocks_saturday_send(user_id, sent):
    saturday = datetime(2026, 9, 19, 17, 45, tzinfo=KST)
    assert saturday.weekday() == 5
    _enable(user_id, skip_weekends=True)
    with patch("src.push.push_sender.now_local", return_value=saturday):
        assert send_due_reminders() == 0
    sent.assert_not_called()


def test_skip_weekends_still_sends_on_weekday(user_id, sent):
    friday = datetime(2026, 9, 18, 17, 45, tzinfo=KST)
    assert friday.weekday() == 4
    _enable(user_id, skip_weekends=True)
    with patch("src.push.push_sender.now_local", return_value=friday):
        assert send_due_reminders() == 1


def test_weekend_send_when_flag_off(user_id, sent):
    """토글을 끈 사람은 주말에도 받는다."""
    saturday = datetime(2026, 9, 19, 17, 45, tzinfo=KST)
    _enable(user_id, skip_weekends=False)
    with patch("src.push.push_sender.now_local", return_value=saturday):
        assert send_due_reminders() == 1


# --- 죽은 구독 정리 (9/23 신규) ---


def _webpush_error(status: int):
    from pywebpush import WebPushException

    exc = WebPushException("gone")
    exc.response = Mock(status_code=status)
    return exc


@pytest.mark.parametrize("status", [404, 410])
def test_dead_subscription_is_deleted(user_id, status):
    """410/404를 받으면 그 구독을 지운다 — 그전엔 print만 하고 영원히 남았다."""
    _enable(user_id)
    subscription = db.list_push_subscriptions(user_id)[0]
    with patch("src.push.push_sender.webpush", side_effect=_webpush_error(status)):
        assert send_push(subscription, "제목", "본문") is False
    assert db.list_push_subscriptions(user_id) == []


def test_temporary_failure_keeps_subscription(user_id):
    """일시적 오류(5xx 등)로는 지우지 않는다 — 다음 기회에 다시 보내야 한다."""
    _enable(user_id)
    subscription = db.list_push_subscriptions(user_id)[0]
    with patch("src.push.push_sender.webpush", side_effect=_webpush_error(503)):
        assert send_push(subscription, "제목", "본문") is False
    assert len(db.list_push_subscriptions(user_id)) == 1


def test_all_devices_dead_does_not_mark_sent(user_id):
    """전부 만료됐으면 "보냈다"고 적지 않는다 — 실제로 아무도 못 받았으므로."""
    _enable(user_id, devices=2)
    with (
        patch("src.push.push_sender.webpush", side_effect=_webpush_error(410)),
        patch("src.push.push_sender.now_local", return_value=_at(17, 45)),
    ):
        assert send_due_reminders() == 0
    assert db.get_push_settings(user_id).last_sent_date is None
    assert db.list_push_subscriptions(user_id) == []
