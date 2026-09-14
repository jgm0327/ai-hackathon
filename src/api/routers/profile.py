"""GET/PUT /api/profile — 온보딩 프로필 (P2, docs/05-api-contract.md 9장, 9/14 신규).

CLAUDE.md 6장 P2 "온보딩(현재 직무/목표 직무/연차)"에 대응. 인증이 없는 단일 유저
데모 전제라 프로필은 싱글턴이다(로그인해서 여러 유저를 구분할 필요가 없음).

이 값 자체는 다른 기능(경력기술서 생성, JD 매칭)에 아직 연결돼 있지 않다 — 온보딩
화면과 입력 화면 상단에 컨텍스트를 보여주는 용도로만 쓰인다. 나중에 JD 매칭 필터 등에
활용하고 싶어지면 이 프로필을 읽어서 확장하면 된다.
"""
from fastapi import APIRouter

from src.api.schemas import ProfileResponse, ProfileUpdateRequest
from src.storage import db

router = APIRouter(tags=["profile"])


@router.get("/profile", response_model=ProfileResponse)
def get_profile() -> ProfileResponse:
    return ProfileResponse.model_validate(db.get_profile())


@router.put("/profile", response_model=ProfileResponse)
def update_profile(payload: ProfileUpdateRequest) -> ProfileResponse:
    db.save_profile(
        job_field=payload.job_field,
        job_detail=payload.job_detail,
        years_segment=payload.years_segment,
    )
    return ProfileResponse.model_validate(db.get_profile())
