"""VAPID 서명 기반 실제 Web Push 발송 — Track E(Tier 2) 담당.

**구현 노트 (9/17, 트리거 변경)**: 원래는 GitHub Actions 스케줄 워크플로가 이 모듈을
호출했는데, 무료 러너의 스케줄이 심하게 지연돼(설정은 `*/5`인데 실측 평균 205분 간격)
5분짜리 발송 윈도와 거의 겹치지 않아 알림이 사실상 안 왔다. 이제 FastAPI 앱 내부
스케줄러(`src/api/scheduler.py`)가 1분마다 호출한다 — 로컬과 배포가 같은 경로로
동작해서 로컬에서 그대로 검증할 수 있다.

**구현 노트 (9/23, 저장소 이전)**: 구독이 Upstash Redis에서 SQLite(`push_subscriptions`
/ `push_settings`)로 옮겨왔다. 발송 단위가 **기기에서 사람으로** 바뀐 게 핵심이다 —
예전엔 구독 한 건이 곧 한 유저였고 퇴근 시각도 구독 안에 들어 있어서, 기기가 3대면
설정이 3벌로 갈라지고 알림도 3번 나갔다. 지금은 유저의 설정 1벌을 보고 판단한 뒤
그 유저의 기기 전부에 같은 알림을 뿌린다.

수동 테스트는 여전히 이 한 줄로 가능하다(스케줄러가 부르는 것과 같은 함수):
    python -c "from src.push.push_sender import send_due_reminders; print(send_due_reminders())"
"""
import json
from datetime import datetime, timedelta

from pywebpush import WebPushException, webpush

from src.config import settings
from src.storage import db
from src.timeutil import now_local

# 이 코드가 오면 그 구독은 되살아나지 않는다 — 404는 없는 구독, 410은 만료/해지.
# 다른 코드(429 레이트리밋, 5xx 등)는 일시적일 수 있으므로 지우지 않는다.
_DEAD_SUBSCRIPTION_STATUSES = {404, 410}


def send_push(subscription: db.PushSubscription, title: str, body: str) -> bool:
    """기기 한 대에 푸시를 발송한다. 성공하면 True.

    **죽은 구독은 여기서 지운다 (9/23)**: 그전까지는 실패를 `print`만 하고 넘어가서,
    사용자가 브라우저 데이터를 지우거나 앱을 삭제해 endpoint가 죽어도 행이 영원히
    남았다. 스케줄러는 그 주소로 매일 계속 던졌고, 저장소에는 아무도 소유하지 않는
    고아 구독이 쌓였다(실제로 3건이 쌓여 있었다).
    """
    if not settings.vapid_private_key:
        raise ValueError("VAPID_PRIVATE_KEY가 설정되어 있지 않습니다 (.env 확인)")
    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=json.dumps({"title": title, "body": body}),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_contact_email},
        )
        return True
    except WebPushException as ex:
        status = getattr(ex.response, "status_code", None)
        if status in _DEAD_SUBSCRIPTION_STATUSES:
            db.delete_push_subscription(subscription.endpoint)
            print(f"push 구독 만료({status}) — 삭제함: id={subscription.id}")
        else:
            print(f"push 발송 실패(status={status}): {ex}")
        return False


def send_due_reminders(window_minutes: int = 5) -> int:
    """(퇴근시각-15분)이 방금 지난 유저들에게 발송한다. 실제 발송된 기기 수를 반환한다.

    **시각 기준 (9/17 수정)**: `datetime.now()`(서버 로컬 시간) 대신 앱 기준 시간대를
    쓴다. 유저가 입력한 "18:00"은 한국 시간 18시인데, 이전 코드는 코드가 도는 머신의
    시간대로 해석해서 UTC 환경(GitHub Actions 러너, OCI VM)에서는 9시간 어긋난 시각에
    발송됐다.

    **중복 방지**: 스케줄러가 1분마다 도는데 윈도는 그보다 넓으므로, 기록이 없으면 같은
    알림이 윈도 내내 반복 발송된다. "오늘 보냈음"을 **유저 단위로** 남겨 하루 한 번만
    나가게 한다 — 기기 단위로 남기면 기기 3대에 3번 간다(9/23 수정).

    `window_minutes`는 "얼마나 늦어도 보낼 것인가"의 유예 구간이다 — 서버가 잠깐
    멈췄다 돌아와도 이 안이면 발송한다. 너무 넓히면 한참 지난 뒤에 "퇴근 15분 전"이
    도착해 오히려 이상해지므로 짧게 유지한다.
    """
    now = now_local()
    today_str = now.date().isoformat()
    sent = 0

    for user_id, prefs, subscriptions in db.list_push_recipients():
        if prefs.last_sent_date == today_str:
            continue  # 오늘 이미 보냄

        # 주말 제외 (9/18 신규 — Figma 온보딩 4/4 "주말에는 쉬어요").
        if prefs.skip_weekends and now.weekday() >= 5:  # 5=토, 6=일
            continue

        try:
            parsed = datetime.strptime(prefs.leave_time, "%H:%M")
        except (TypeError, ValueError):
            # 한 유저의 값이 깨져도 나머지 유저 발송까지 막지 않는다.
            print(f"leave_time 파싱 실패, 건너뜀: user_id={user_id} {prefs.leave_time!r}")
            continue

        # now와 같은 시간대의 aware datetime으로 맞춘다 — naive와 aware를 비교하면
        # TypeError가 난다.
        leave_time = now.replace(hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0)
        remind_at = leave_time - timedelta(minutes=15)

        if not (remind_at <= now < remind_at + timedelta(minutes=window_minutes)):
            continue

        delivered = 0
        for subscription in subscriptions:
            if send_push(
                subscription, "퇴근 15분 전!", "오늘 하루 업무 기록, 잊지 말고 남겨보세요."
            ):
                delivered += 1

        # 한 대도 못 보냈으면 "보냈다"고 적지 않는다 — 전부 만료돼 방금 지워진 경우라
        # 다음 틱에는 대상에서 빠지고, 일시 장애였다면 윈도 안에서 다시 시도된다.
        if delivered:
            db.mark_push_sent(user_id, today_str)
            sent += delivered

    return sent
