"""VAPID 서명 기반 실제 Web Push 발송 — Track E(Tier 2) 담당.

이 모듈은 Streamlit 앱 자체가 아니라, GitHub Actions 스케줄 워크플로 같은
외부 트리거에서 호출되는 스크립트에서 import해서 쓴다 (docs/04-push-notifications.md 참고).
"""
import json
import os
from datetime import datetime, timedelta

from pywebpush import WebPushException, webpush

from src.push.subscription_store import list_subscriptions

VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_CLAIMS = {"sub": os.getenv("VAPID_CONTACT_EMAIL", "mailto:example@example.com")}


def send_push(subscription: dict, title: str, body: str) -> None:
    """단일 유저에게 푸시를 발송한다."""
    if not VAPID_PRIVATE_KEY:
        raise ValueError("VAPID_PRIVATE_KEY가 설정되어 있지 않습니다 (.env 확인)")
    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps({"title": title, "body": body}),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims=VAPID_CLAIMS,
        )
    except WebPushException as ex:
        # TODO(Track E): 만료된 구독(410 Gone) 등은 subscription_store에서 정리하는 로직 추가
        print(f"push 발송 실패: {ex}")


def send_due_reminders(window_minutes: int = 5) -> None:
    """지금 시각 기준 (퇴근시각-15분)이 이미 지난 유저들에게 발송한다.

    GitHub Actions에서 이 함수를 window_minutes 주기(예: 5분마다)로 호출하는 것을 가정.
    같은 유저에게 중복 발송되지 않도록 하는 로직은 TODO.
    """
    now = datetime.now()
    for user_id, entry in list_subscriptions().items():
        leave_time = datetime.strptime(entry["leave_time"], "%H:%M").replace(
            year=now.year, month=now.month, day=now.day
        )
        remind_at = leave_time - timedelta(minutes=15)
        if remind_at <= now < remind_at + timedelta(minutes=window_minutes):
            send_push(entry["subscription"], "퇴근 15분 전!", "오늘 하루 업무 기록, 잊지 말고 남겨보세요.")
