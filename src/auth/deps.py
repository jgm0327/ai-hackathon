"""FastAPI 의존성 — "지금 로그인한 유저가 누구인가" — Track B 담당 (9/14 신규).

라우터는 `current_user: db.User = Depends(get_current_user)`만 선언하면 되고,
세션 쿠키 파싱/조회/만료 처리는 전부 여기 숨는다. 테스트는 이 함수 자체를
`app.dependency_overrides[get_current_user]`로 갈아끼워서 실제 카카오/쿠키 없이도
"로그인된 특정 유저"를 흉내낸다(계획서 7장).
"""
from fastapi import HTTPException, Request

from src.storage import db

SESSION_COOKIE_NAME = "session_id"


def get_current_user(request: Request) -> db.User:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    session = db.get_session(session_id)
    if session is None:
        # 존재하지 않거나 만료된 세션 — "쿠키는 있는데 세션이 없다"와 "쿠키 자체가
        # 없다"를 프론트에서 구분할 필요가 없으므로 동일하게 401로 취급한다.
        raise HTTPException(status_code=401, detail="세션이 만료됐습니다. 다시 로그인해 주세요.")

    user = db.get_user(session.user_id)
    if user is None:
        # 세션은 있는데 유저가 없는 건 정상 상태에서 일어날 수 없지만(FK로 보장됨),
        # 방어적으로 처리 — 있어도 손해 없고 없으면 원인 불명 500이 된다.
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다.")

    return user
