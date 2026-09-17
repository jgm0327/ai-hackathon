"""LLM 호출 엔드포인트 레이트 리밋 — Track B (9/17 신규).

**왜 필요한가**: 이 서비스의 LLM 엔드포인트는 전부 로그인 뒤에 있지만(익명 남용은
불가), 로그인한 유저 한 명이 "경력기술서 만들기"를 연타하거나 프론트 버그로 루프가
돌면 Sonnet 호출이 그대로 청구서가 된다. 스키마 길이 제한(schemas.py)이 "한 번에
얼마나 큰 입력이 가느냐"를 막는다면, 여기는 "얼마나 자주 가느냐"를 막는다.

**왜 slowapi를 안 쓰는가**: 이 코드베이스는 처음부터 필요한 만큼만 직접 구현하는
쪽을 택해왔고(parsing/resume.py의 LangChain 미사용 노트 참고), 여기 필요한 건
"유저별 슬라이딩 윈도" 하나뿐이라 40줄이면 끝난다. slowapi는 기본이 IP 기준이라
어차피 커스텀 키 함수를 써야 하고, 그럴 거면 의존성을 늘릴 이유가 없다.

**한계(의도적)**: 프로세스 메모리에만 저장한다. 서버를 재시작하면 카운터가 비고,
워커를 여러 개 띄우면 워커마다 따로 센다. 지금 배포 구성이 OCI 단일 VM + uvicorn
단일 프로세스라(docs/02-architecture.md 4장) 실제로 문제가 되지 않는다. 워커를
늘리는 시점에는 Redis 등 공유 저장소로 옮겨야 한다 — 그때 이 모듈만 갈아끼우면 된다.
"""
import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException

from src.auth.deps import get_current_user
from src.storage import db

# (윈도 길이 초, 그 안에서 허용할 최대 호출 수)
#
# 정상 사용이면 닿지 않는 선으로 잡았다 — 경력기술서 생성은 이직 준비 시점에만 쓰는
# 경로라(CLAUDE.md 2.1) 분당 몇 번이면 충분하고, 메모 입력은 매일 쓰지만 사람이
# 손으로 치는 속도라 분당 20회를 넘기 어렵다.
_WINDOW_SECONDS = 60

# 엔드포인트 묶음별 분당 상한. 비싼 모델(Sonnet)을 쓰는 쪽을 더 빡빡하게 잡는다.
LIMIT_HEAVY = 10  # 경력기술서 생성/보강/공고분석/역질문 — Sonnet
LIMIT_LIGHT = 30  # 메모 저장/재정리 — Haiku
LIMIT_BATCH = 3   # 노션 동기화 — 한 번에 최대 50회 호출이라 가장 빡빡하게

_lock = threading.Lock()
_hits: dict[str, deque[float]] = defaultdict(deque)


def _check(bucket: str, user_id: int, limit: int) -> None:
    """슬라이딩 윈도. 윈도를 벗어난 기록은 버리고, 남은 게 limit 이상이면 429."""
    key = f"{bucket}:{user_id}"
    now = time.monotonic()
    cutoff = now - _WINDOW_SECONDS

    with _lock:
        timestamps = _hits[key]
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()

        if len(timestamps) >= limit:
            # 가장 오래된 기록이 윈도를 벗어나면 다시 열린다.
            retry_after = max(1, int(timestamps[0] + _WINDOW_SECONDS - now) + 1)
            raise HTTPException(
                status_code=429,
                detail="요청이 너무 잦습니다. 잠시 후 다시 시도해 주세요.",
                headers={"Retry-After": str(retry_after)},
            )

        timestamps.append(now)


def _make_dependency(bucket: str, limit: int):
    """`Depends()`에 넣을 의존성을 만든다.

    `get_current_user`를 그대로 재사용하므로, 이 의존성을 건 라우트는 로그인 검사도
    함께 수행된다 — 라우터가 이미 선언한 `current_user`와 중복 호출되지만 세션 조회
    한 번(가벼운 DB 읽기)이라 문제되지 않고, 덕분에 라우터 시그니처를 안 바꿔도 된다.
    """

    def dependency(current_user: db.User = Depends(get_current_user)) -> None:
        _check(bucket, current_user.id, limit)

    return dependency


# 라우터에서 `dependencies=[Depends(limit_heavy)]` 형태로 건다.
limit_heavy = _make_dependency("heavy", LIMIT_HEAVY)
limit_light = _make_dependency("light", LIMIT_LIGHT)
limit_batch = _make_dependency("batch", LIMIT_BATCH)


def reset_for_tests() -> None:
    """테스트 격리용 — 테스트끼리 카운터가 새는 걸 막는다."""
    with _lock:
        _hits.clear()
