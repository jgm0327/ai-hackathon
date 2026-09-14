"""카카오 로그인(OAuth Authorization Code) REST API 래퍼 — Track B 담당 (9/14 신규).

여기서 하는 일은 순수 HTTP 왕복뿐이다 — 쿠키/세션/DB는 손대지 않는다
(그건 `src/api/routers/auth.py`의 몫). 토큰 교환은 반드시 서버(여기)에서만
한다 — REST API 키를 브라우저에 노출하지 않기 위함.

플로우 (표준 OAuth Authorization Code):
1. `build_authorize_url()`로 만든 URL로 브라우저를 리다이렉트한다 (실제 네비게이션,
   fetch 아님 — 카카오 로그인/동의 화면을 보여줘야 하므로).
2. 사용자가 동의하면 카카오가 `redirect_uri`로 `?code=...&state=...`를 붙여 되돌려준다.
3. `exchange_code_for_token()`으로 `code`를 `access_token`으로 교환한다(서버-서버).
4. `fetch_kakao_user()`로 그 토큰을 이용해 사용자 정보(카카오 id, 닉네임)를 가져온다.
"""
from dataclasses import dataclass
from urllib.parse import urlencode

import requests

from src.config import settings

_AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
_USER_INFO_URL = "https://kapi.kakao.com/v2/user/me"

# 닉네임만 받는다(이메일 제외) — 이메일(account_email) 스코프는 카카오가 "비즈니스 앱"
# 심사를 요구해서 해커톤 일정상 무리다. 로그인 식별에는 카카오 id + 닉네임으로 충분.
_SCOPE = "profile_nickname"


class KakaoOAuthError(Exception):
    """토큰 교환/사용자 정보 조회가 실패했을 때. 라우터가 잡아서 401/502로 변환한다."""


@dataclass
class KakaoToken:
    access_token: str


@dataclass
class KakaoUserInfo:
    kakao_id: str
    nickname: str | None
    profile_image_url: str | None


def build_authorize_url(state: str) -> str:
    """브라우저를 리다이렉트할 카카오 인가 URL을 만든다. `state`는 호출부가 CSRF 방지용으로
    쿠키에 저장해뒀다가 콜백에서 되돌아온 값과 대조해야 한다."""
    params = {
        "client_id": settings.kakao_rest_api_key,
        "redirect_uri": settings.kakao_redirect_uri,
        "response_type": "code",
        "state": state,
        "scope": _SCOPE,
    }
    return f"{_AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code_for_token(code: str) -> KakaoToken:
    """인가 코드를 액세스 토큰으로 교환한다(서버-서버 호출)."""
    data = {
        "grant_type": "authorization_code",
        "client_id": settings.kakao_rest_api_key,
        "redirect_uri": settings.kakao_redirect_uri,
        "code": code,
    }
    # Client Secret은 콘솔에서 켰을 때만 필요 — 빈 문자열이면 아예 안 보낸다(카카오가
    # "설정 안 했는데 보내는" 요청도 거부하는 경우가 있어 조건부로 포함시킨다).
    if settings.kakao_client_secret:
        data["client_secret"] = settings.kakao_client_secret

    response = requests.post(
        _TOKEN_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
        timeout=10,
    )
    if not response.ok:
        raise KakaoOAuthError(f"카카오 토큰 교환 실패: {response.status_code} {response.text}")

    body = response.json()
    access_token = body.get("access_token")
    if not access_token:
        raise KakaoOAuthError(f"카카오 응답에 access_token이 없습니다: {body}")
    return KakaoToken(access_token=access_token)


def fetch_kakao_user(access_token: str) -> KakaoUserInfo:
    """액세스 토큰으로 카카오 사용자 정보를 가져온다."""
    response = requests.get(
        _USER_INFO_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
        },
        timeout=10,
    )
    if not response.ok:
        raise KakaoOAuthError(f"카카오 사용자 정보 조회 실패: {response.status_code} {response.text}")

    body = response.json()
    kakao_id = body.get("id")
    if kakao_id is None:
        raise KakaoOAuthError(f"카카오 응답에 id가 없습니다: {body}")

    properties = body.get("properties") or {}
    return KakaoUserInfo(
        # 카카오 id는 큰 정수로 오지만 산술 연산 대상이 아니라 식별자일 뿐이므로,
        # 정밀도/오버플로 걱정 없이 문자열로 저장한다.
        kakao_id=str(kakao_id),
        nickname=properties.get("nickname"),
        profile_image_url=properties.get("profile_image"),
    )
