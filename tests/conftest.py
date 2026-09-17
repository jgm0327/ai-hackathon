"""pytest 공용 픽스처 — Track B 담당 (9/14, 카카오 로그인 Phase B에서 신설).

API 레벨 테스트(test_api_*.py) 6개 전부가 이제 "격리된 SQLite + 로그인된 가짜 유저"
조합을 똑같이 필요로 한다 — 파일마다 반복해서 정의하던 `_isolated_db`를 여기 하나로
모으고, 실제 카카오/쿠키 없이 `Depends(get_current_user)`를 통과시키는
`app.dependency_overrides`까지 같이 처리한다.
"""
import pytest

from src.api import rate_limit
from src.api.main import app
from src.auth.deps import get_current_user
from src.storage import db


@pytest.fixture(autouse=True)
def _isolated_db(monkeypatch, tmp_path):
    """모든 테스트가 독립된 DB 파일을 쓰게 한다(모듈 전역 settings를 monkeypatch)."""

    class _FakeSettings:
        db_path = str(tmp_path / "test.db")

    monkeypatch.setattr(db, "settings", _FakeSettings())
    yield


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    """레이트 리밋 카운터를 테스트마다 비운다 (9/17).

    카운터는 프로세스 메모리에 유저 id별로 쌓이는데, 테스트는 전부 같은 가짜 유저를
    쓰므로 초기화하지 않으면 한 파일 안에서 앞 테스트가 쓴 횟수 때문에 뒤 테스트가
    429를 받는다(실제로 8개가 그렇게 깨졌다). 레이트 리밋 자체를 끄지 않고 비우기만
    하는 이유는, 리밋 동작 자체를 검증하는 테스트도 같은 픽스처 위에서 돌아야 하기
    때문이다.
    """
    rate_limit.reset_for_tests()
    yield


@pytest.fixture
def current_user_id() -> int:
    """이 테스트에서 "로그인된" 유저 하나를 만들고, FastAPI가 실제 쿠키/카카오 없이
    그 유저로 인증된 것처럼 동작하게 dependency override를 건다.

    이 픽스처를 쓰는 테스트에서만 오버라이드가 걸리므로(autouse 아님), "로그인 안 된
    상태"를 확인하려는 테스트(401 검증 등)는 그냥 이 픽스처를 요청하지 않으면 된다.
    """
    user_id = db.upsert_user(
        kakao_id="test-kakao-id", nickname="테스터", profile_image_url=None, now="2026-01-01T00:00:00"
    )
    app.dependency_overrides[get_current_user] = lambda: db.get_user(user_id)
    yield user_id
    app.dependency_overrides.pop(get_current_user, None)
