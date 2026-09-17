"""퇴근 알림 스케줄러 — FastAPI 앱 내부에서 도는 백그라운드 루프 (9/17 신규).

**왜 앱 안에 두는가**: 원래는 GitHub Actions 스케줄 워크플로가 발송을 트리거했는데
두 가지가 겹쳐 사실상 알림이 안 왔다.

1. 무료 러너의 스케줄 지연 — cron은 `*/5`인데 실측 실행 간격이 평균 205분이라
   5분짜리 발송 윈도와 거의 겹치지 않았다.
2. 러너가 UTC라 유저가 입력한 KST 시각이 9시간 어긋나 계산됐다(timeutil.py 참고).

앱 안으로 들여오면 로컬(Windows)과 배포(OCI VM)가 **같은 경로로** 동작해서, 로컬에서
그대로 재현·검증할 수 있다. cron/작업 스케줄러 등록도, cron 전용 환경변수 설정도
필요 없다 — 이미 로딩된 `settings`를 그대로 쓴다.

**왜 APScheduler를 안 쓰는가**: 필요한 게 "1분마다 함수 하나 호출"뿐이라 asyncio 루프
하나로 충분하다. 이 레포가 langchain/slowapi를 들이지 않은 것과 같은 판단이다.

**단일 프로세스 전제**: uvicorn 워커를 여러 개 띄우면 이 루프도 워커마다 돌아서 같은
알림이 중복 발송된다. 현재 배포 구성은 단일 프로세스이고(레이트 리밋도 같은 전제,
`src/api/rate_limit.py` 참고), 워커를 늘릴 때는 이 루프를 별도 프로세스로 빼야 한다.
"""
import asyncio
import logging

from src.push.push_sender import send_due_reminders

logger = logging.getLogger(__name__)

# 확인 주기. 발송 윈도(send_due_reminders의 window_minutes, 기본 5분)보다 짧아야
# 윈도를 건너뛰지 않는다.
TICK_SECONDS = 60


async def _loop() -> None:
    while True:
        try:
            sent = await asyncio.to_thread(send_due_reminders)
            if sent:
                logger.info("퇴근 알림 발송: %d건", sent)
        except asyncio.CancelledError:
            raise
        except Exception:
            # 한 번 실패해도 루프는 계속 돈다 — 네트워크 일시 장애(Upstash/푸시 서비스)로
            # 스케줄러가 통째로 죽으면 그날 알림이 전부 사라진다.
            logger.exception("퇴근 알림 발송 중 오류")
        await asyncio.sleep(TICK_SECONDS)


def start() -> asyncio.Task | None:
    """앱 시작 시 루프를 띄운다. VAPID 키가 없으면 띄우지 않는다.

    키가 없으면 `send_push()`가 매번 ValueError를 던지므로, 1분마다 예외 로그만 쌓인다.
    푸시를 설정하지 않은 환경(테스트, 로컬 일부)에서는 조용히 비활성으로 두는 게 맞다.
    """
    from src.config import settings

    if not settings.vapid_private_key:
        logger.info("VAPID_PRIVATE_KEY가 없어 퇴근 알림 스케줄러를 시작하지 않습니다.")
        return None

    task = asyncio.create_task(_loop())
    logger.info("퇴근 알림 스케줄러 시작 (%d초 주기)", TICK_SECONDS)
    return task
