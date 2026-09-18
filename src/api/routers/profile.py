"""GET/PUT /api/profile — 온보딩 프로필 (P2, docs/05-api-contract.md 9장, 9/14 신규).

CLAUDE.md 6장 P2 "온보딩(현재 직무/목표 직무/연차)"에 대응.

**구현 노트 (9/14, 카카오 로그인 Phase B)**: "인증 없는 단일 유저 데모"였던 전제가
바뀌면서 `profile`도 싱글턴(id=1)에서 유저당 1행으로 바뀌었다 — 로그인 유저의
`user_id`로 조회/저장한다.

**구현 노트 (9/18, Figma "00 · 온보딩" 268:5731 재설계)**: 온보딩이 4단계로 바뀌면서
이 엔드포인트가 세 가지를 더 다룬다.
  - `target_jobs` — 2/4 "어디로 가고 싶으세요?"(다중 선택)
  - `companies` — 3/4 "어디서 얼마나 일하셨어요?"(회사 + 기간)
  - `years_segment` — **더 이상 받지 않고 회사 기간에서 계산한다.** 화면에도 "연차는
    여기서 자동으로 계산해요. 따로 묻지 않을게요"라고 적혀 있다. 계산을 서버에 둔
    이유는 화면이 보여주는 "6년 3개월"과 저장되는 구간이 갈라지지 않게 하기 위해서다
    (`src/career_span.py`).

이 값들은 아직 경력기술서 생성/JD 매칭에 연결돼 있지 않다 — 화면 컨텍스트 용도다.
"""
from fastapi import APIRouter, Depends

from src.api.schemas import CompanyPayload, ProfileResponse, ProfileUpdateRequest
from src.auth.deps import get_current_user
from src.career_span import to_years_segment, total_months
from src.storage import db

router = APIRouter(tags=["profile"])


def _to_response(profile: db.Profile) -> ProfileResponse:
    months = total_months([(c.started_at, c.ended_at) for c in profile.companies])
    return ProfileResponse(
        job_field=profile.job_field,
        job_detail=profile.job_detail,
        years_segment=profile.years_segment,
        target_jobs=profile.target_jobs,
        companies=[
            CompanyPayload(name=c.name, started_at=c.started_at, ended_at=c.ended_at)
            for c in profile.companies
        ],
        total_months=months,
    )


@router.get("/profile", response_model=ProfileResponse)
def get_profile(current_user: db.User = Depends(get_current_user)) -> ProfileResponse:
    return _to_response(db.get_profile(current_user.id))


@router.put("/profile", response_model=ProfileResponse)
def update_profile(
    payload: ProfileUpdateRequest, current_user: db.User = Depends(get_current_user)
) -> ProfileResponse:
    companies = (
        None
        if payload.companies is None
        else [
            db.Company(name=c.name.strip(), started_at=c.started_at, ended_at=c.ended_at)
            for c in payload.companies
            if c.name.strip()
        ]
    )

    # 회사를 받았으면 연차는 거기서 계산한 값이 이긴다 — 요청이 years_segment를 같이
    # 보내더라도 무시한다. 두 값이 어긋난 채로 저장되는 경우를 아예 없앤다.
    years_segment = payload.years_segment
    if companies is not None:
        years_segment = to_years_segment(total_months([(c.started_at, c.ended_at) for c in companies]))

    db.save_profile(
        current_user.id,
        job_field=payload.job_field,
        job_detail=payload.job_detail,
        years_segment=years_segment,
        target_jobs=payload.target_jobs,
        companies=companies,
    )
    return _to_response(db.get_profile(current_user.id))
