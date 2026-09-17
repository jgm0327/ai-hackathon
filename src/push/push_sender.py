"""VAPID 서명 기반 실제 Web Push 발송 — Track E(Tier 2) 담당.

**구현 노트 (9/17, 트리거 변경)**: 원래는 GitHub Actions 스케줄 워크플로가 이 모듈을
호출했는데, 무료 러너의 스케줄이 심하게 지연돼(설정은 `*/5`인데 실측 평균 205분 간격)
5분짜리 발송 윈도와 거의 겹치지 않아 알림이 사실상 안 왔다. 이제 FastAPI 앱 내부
스케줄러(`src/api/scheduler.py`)가 1분마다 호출한다 — 로컬과 배포가 같은 경로로
동작해서 로컬에서 그대로 검증할 수 있다.

수동 테스트는 여전히 이 한 줄로 가능하다(스케줄러가 부르는 것과 같은 함수):
    python -c "from src.push.push_sender import send_due_reminders; print(send_due_reminders())"
"""
import json
from datetime import datetime, timedelta

from pywebpush import WebPushException, webpush

from src.config import settings
from src.push.subscription_store import list_subscriptions, mark_reminder_sent
from src.timeutil import now_local


def send_push(subscription: dict, title: str, body: str) -> None:
    """단일 유저에게 푸시를 발송한다."""
    if not settings.vapid_private_key:
        raise ValueError("VAPID_PRIVATE_KEY가 설정되어 있지 않습니다 (.env 확인)")
    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps({"title": title, "body": body}),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_contact_email},
        )
    except WebPushException as ex:
        # TODO(Track E): 만료된 구독(410 Gone) 등은 subscription_store에서 정리하는 로직 추가
        print(f"push 발송 실패: {ex}")


def send_due_reminders(window_minutes: int = 5) -> int:
    """(퇴근시각-15분)이 방금 지난 유저들에게 발송한다. 발송 건수를 반환한다.

    **시각 기준 (9/17 수정)**: `datetime.now()`(서버 로컬 시간) 대신 앱 기준 시간대를
    쓴다. 유저가 입력한 "18:00"은 한국 시간 18시인데, 이전 코드는 코드가 도는 머신의
    시간대로 해석해서 UTC 환경(GitHub Actions 러너, OCI VM)에서는 9시간 어긋난 시각에
    발송됐다.

    **중복 방지 (9/17 신규)**: 스케줄러가 1분마다 도는데 윈도는 그보다 넓으므로, 기록이
    없으면 같은 알림이 윈도 내내 반복 발송된다. 유저별로 "오늘 보냈음"을 남겨 하루 한
    번만 나가게 한다(기존 코드의 `중복 발송 방지는 TODO`가 이 문제였다).

    `window_minutes`는 "얼마나 늦어도 보낼 것인가"의 유예 구간이다 — 서버가 잠깐
    멈췄다 돌아와도 이 안이면 발송한다. 너무 넓히면 한참 지난 뒤에 "퇴근 15분 전"이
    도착해 오히려 이상해지므로 짧게 유지한다.
    """
    now = now_local()
    today_str = now.date().isoformat()
    sent = 0

    for user_id, entry in list_subscriptions().items():
        if entry.get("last_sent_date") == today_str:
            continue  # 오늘 이미 보냄

        try:
            parsed = datetime.strptime(entry["leave_time"], "%H:%M")
        except (KeyError, ValueError):
            # 한 유저의 값이 깨져도 나머지 유저 발송까지 막지 않는다.
            print(f"leave_time 파싱 실패, 건너뜀: {entry.get('leave_time')!r}")
            continue

        # now와 같은 시간대의 aware datetime으로 맞춘다 — naive와 aware를 비교하면
        # TypeError가 난다.
        leave_time = now.replace(
            hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0
        )
        remind_at = leave_time - timedelta(minutes=15)

        if remind_at <= now < remind_at + timedelta(minutes=window_minutes):
            send_push(entry["subscription"], "퇴근 15분 전!", "오늘 하루 업무 기록, 잊지 말고 남겨보세요.")
            mark_reminder_sent(user_id, today_str)
            sent += 1

    return sent
