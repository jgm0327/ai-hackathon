"""GET/PUT /api/profile — 온보딩 프로필 (P2, docs/05-api-contract.md 9장, 9/14 신규).

CLAUDE.md 6장 P2 "온보딩(현재 직무/목표 직무/연차)"에 대응.

**구현 노트 (9/14, 카카오 로그인 Phase B)**: "인증 없는 단일 유저 데모"였던 전제가
바뀌면서 `profile`도 싱글턴(id=1)에서 유저당 1행으로 바뀌었다 — 로그인 유저의
`user_id`로 조회/저장한다.

이 값 자체는 다른 기능(경력기술서 생성, JD 매칭)에 아직 연결돼 있지 않다 — 온보딩
화면과 입력 화면 상단에 컨텍스트를 보여주는 용도로만 쓰인다. 나중에 JD 매칭 필터 등에
활용하고 싶어지면 이 프로필을 읽어서 확장하면 된다.
"""
from fastapi import APIRouter, Depends

from src.api.schemas import ProfileResponse, ProfileUpdateRequest
from src.auth.deps import get_current_user
from src.storage import db

router = APIRouter(tags=["profile"])


@router.get("/profile", response_model=ProfileResponse)
def get_profile(current_user: db.User = Depends(get_current_user)) -> ProfileResponse:
    return ProfileResponse.model_validate(db.get_profile(current_user.id))


@router.put("/profile", response_model=ProfileResponse)
def update_profile(
    payload: ProfileUpdateRequest, current_user: db.User = Depends(get_current_user)
) -> ProfileResponse:
    db.save_profile(
        current_user.id,
        job_field=payload.job_field,
        job_detail=payload.job_detail,
        years_segment=payload.years_segment,
    )
    return ProfileResponse.model_validate(db.get_profile(current_user.id))
