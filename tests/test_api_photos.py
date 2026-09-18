"""기록 첨부 사진 — Figma "03 · 커리어 스택" 4.1-b "첨부한 사진" (9/18 신규).

DB 격리와 로그인 유저 오버라이드는 `tests/conftest.py`의 `_isolated_db`(autouse)/
`current_user_id` 픽스처가 담당한다. 사진 디렉터리는 여기서 tmp_path로 따로 격리한다 —
안 그러면 테스트가 실제 `data/photos`에 파일을 흘린다.
"""
import base64
import json
from dataclasses import replace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.config import settings
from src.storage import db

MOCK_LLM_RESPONSE = json.dumps(
    {
        "refined_sentence": "가입 배너 문구를 A/B 테스트해 전환율을 개선했습니다.",
        "skill_tags": ["캠페인 운영"],
        "confidence": 0.9,
        "case_summary": "",
    },
    ensure_ascii=False,
)

# 1x1 PNG. 실제 이미지 바이트여야 업로드 경로(크기/확장자 처리)를 그대로 통과한다.
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


@pytest.fixture(autouse=True)
def _isolated_photo_dir(tmp_path, monkeypatch):
    """사진 저장 디렉터리를 테스트마다 갈아끼운다.

    `settings`는 frozen dataclass라 속성을 덮어쓸 수 없어서, 인스턴스 자체를
    tmp_path를 가리키는 복제본으로 바꾼다. `db`와 `photos` 라우터가 각각 import한
    참조를 둘 다 갈아야 한다.
    """
    patched = replace(settings, photo_dir=str(tmp_path / "photos"))
    monkeypatch.setattr("src.storage.db.settings", patched)
    monkeypatch.setattr("src.api.routers.photos.settings", patched)
    yield


@pytest.fixture(autouse=True)
def _no_op_canonicalize(monkeypatch):
    monkeypatch.setattr("src.agent.pipeline.canonicalize_tags", lambda tags: tags)
    yield


@pytest.fixture
def client():
    return TestClient(app)


def _create_card(client) -> dict:
    with patch("src.parsing.parser._call_llm", return_value=MOCK_LLM_RESPONSE):
        return client.post("/api/cards", json={"raw_text": "가입 배너 A/B 테스트"}).json()


def _upload(client, card_id: int, name: str = "shot.png", mime: str = "image/png"):
    return client.post(
        f"/api/cards/{card_id}/photos", files={"file": (name, PNG_BYTES, mime)}
    )


def test_upload_requires_login(client):
    assert _upload(client, 1).status_code == 401


def test_upload_returns_201_and_metadata(client, current_user_id):
    card = _create_card(client)
    response = _upload(client, card["id"])

    assert response.status_code == 201
    body = response.json()
    assert body["card_id"] == card["id"]
    assert body["mime_type"] == "image/png"
    assert body["byte_size"] == len(PNG_BYTES)
    assert body["original_name"] == "shot.png"
    # 디스크 파일명은 응답에 실리지 않는다 — 내부 경로를 노출할 이유가 없다.
    assert "stored_name" not in body


def test_uploaded_photo_is_listed_and_served(client, current_user_id):
    card = _create_card(client)
    photo_id = _upload(client, card["id"]).json()["id"]

    listed = client.get(f"/api/cards/{card['id']}/photos").json()["photos"]
    assert [p["id"] for p in listed] == [photo_id]

    served = client.get(f"/api/photos/{photo_id}")
    assert served.status_code == 200
    assert served.content == PNG_BYTES
    # 본인만 볼 수 있는 자원이라 공유 캐시에 담기면 안 된다.
    assert "private" in served.headers["cache-control"]


def test_card_list_reports_photo_count(client, current_user_id):
    card = _create_card(client)
    assert client.get("/api/cards").json()["cards"][0]["photo_count"] == 0

    _upload(client, card["id"])
    _upload(client, card["id"])
    assert client.get("/api/cards").json()["cards"][0]["photo_count"] == 2


def test_rejects_non_image_mime(client, current_user_id):
    card = _create_card(client)
    response = client.post(
        f"/api/cards/{card['id']}/photos",
        files={"file": ("memo.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 415


def test_rejects_oversized_file(client, current_user_id, monkeypatch):
    card = _create_card(client)
    monkeypatch.setattr("src.api.routers.photos.settings", replace(settings, photo_max_bytes=10))
    response = _upload(client, card["id"])
    assert response.status_code == 413


def test_rejects_when_card_is_full(client, current_user_id, monkeypatch):
    card = _create_card(client)
    monkeypatch.setattr(
        "src.api.routers.photos.settings", replace(settings, photo_max_per_card=1)
    )
    assert _upload(client, card["id"]).status_code == 201
    assert _upload(client, card["id"]).status_code == 409


def test_upload_to_unknown_card_returns_404(client, current_user_id):
    assert _upload(client, 9999).status_code == 404


def test_other_users_photo_is_not_visible(client, current_user_id):
    """남의 사진은 403이 아니라 404 — 존재 여부 자체가 새면 안 된다."""
    card = _create_card(client)
    photo_id = _upload(client, card["id"]).json()["id"]

    other = db.upsert_user("other-kakao", "남", None, "2026-09-18T00:00:00+09:00")
    assert db.get_card_photo(other, photo_id) is None


def test_delete_photo_removes_row_and_file(client, current_user_id):
    card = _create_card(client)
    photo_id = _upload(client, card["id"]).json()["id"]
    stored = db.get_card_photo(current_user_id, photo_id).stored_name
    assert db.photo_path(stored).exists()

    assert client.delete(f"/api/photos/{photo_id}").status_code == 204
    assert client.get(f"/api/photos/{photo_id}").status_code == 404
    assert not db.photo_path(stored).exists()


def test_delete_photo_is_idempotent(client, current_user_id):
    assert client.delete("/api/photos/9999").status_code == 204


def test_deleting_card_also_deletes_its_photos(client, current_user_id):
    """Figma 4.1-c가 "되돌릴 수 없어요"라고 명시한다 — 파일도 같이 사라져야 한다."""
    card = _create_card(client)
    photo_id = _upload(client, card["id"]).json()["id"]
    stored = db.get_card_photo(current_user_id, photo_id).stored_name

    assert client.delete(f"/api/cards/{card['id']}").status_code == 204
    assert db.get_card_photo(current_user_id, photo_id) is None
    assert not db.photo_path(stored).exists()


def test_serving_photo_whose_file_vanished_returns_404(client, current_user_id):
    """행은 있는데 파일이 없는 경우 — 500으로 터지지 않고 404로 알린다."""
    card = _create_card(client)
    photo_id = _upload(client, card["id"]).json()["id"]
    db.photo_path(db.get_card_photo(current_user_id, photo_id).stored_name).unlink()

    assert client.get(f"/api/photos/{photo_id}").status_code == 404


def test_photo_path_rejects_path_traversal():
    with pytest.raises(ValueError):
        db.photo_path("../app.db")
