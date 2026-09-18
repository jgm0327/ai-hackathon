"""기록 첨부 사진 — Figma "03 · 커리어 스택" 4.1-b "첨부한 사진" (9/18 신규).

**왜 DB가 아니라 디스크인가**: 이미지 바이트를 SQLite BLOB으로 넣으면 백업
내보내기(`GET /api/backup`)가 사진까지 통째로 메모리에 올리게 된다. OCI AMD
Micro(RAM 1GB, `tasks/track-d-deploy.md` 2장)에서 그건 바로 부담이 된다. 파일은
`settings.photo_dir`에 두고 DB에는 메타만 남긴다.

**왜 리사이즈를 안 하는가**: Pillow를 끌어오면 배포 이미지가 커지고, 같은 VM에서
FastAPI + Chroma와 메모리를 다퉈야 한다. 대신 업로드 크기를 서버에서 잘라내고
(`settings.photo_max_bytes`), 프론트가 보내기 전에 canvas로 줄인다
(`web/lib/imageResize.ts`) — 실제로 올라오는 건 긴 변 1600px짜리 JPEG다.

**소유권**: 전 엔드포인트가 `user_id`로 스코핑된다. 남의 사진은 404이지 403이
아니다 — 존재 여부 자체가 새면 안 된다(다른 카드 라우터와 같은 규칙).
"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from src.api.rate_limit import limit_light
from src.api.schemas import CardPhotoListResponse, CardPhotoResponse
from src.auth.deps import get_current_user
from src.config import settings
from src.storage import db
from src.timeutil import now_local

router = APIRouter(tags=["photos"])

# 브라우저가 실제로 그릴 수 있는 것만 받는다. HEIC는 크롬/안드로이드가 못 그려서
# 뺐다 — iOS Safari가 `<input type="file" accept="image/*">`로 고른 HEIC를 자동으로
# JPEG로 바꿔 올려주므로 실사용에 구멍이 생기지 않는다.
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


@router.post(
    "/cards/{card_id}/photos",
    response_model=CardPhotoResponse,
    status_code=201,
    dependencies=[Depends(limit_light)],
)
async def upload_card_photo(
    card_id: int,
    file: UploadFile = File(...),
    current_user: db.User = Depends(get_current_user),
) -> CardPhotoResponse:
    """기록 한 건에 사진 한 장을 붙인다.

    LLM을 타지 않는다 — 사진은 정리 대상이 아니라 근거 자료다. 그래서 매일 쓰는
    경로에 얹혀도 대기 시간이 늘지 않는다(CLAUDE.md 2.1).
    """
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415, detail="사진은 JPG, PNG, WEBP, GIF만 올릴 수 있어요."
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="빈 파일입니다.")
    if len(data) > settings.photo_max_bytes:
        limit_mb = settings.photo_max_bytes // (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"사진은 {limit_mb}MB까지 올릴 수 있어요.")

    # 장수 제한은 저장 **직전에** 센다. 먼저 세고 저장하면 그 사이에 들어온 요청과
    # 겹쳐 한도를 넘길 수 있는데, 어차피 단일 프로세스라 실질적인 경합은 없고
    # 넘더라도 사진 한 장이라 여기서는 이 단순함을 택한다.
    existing = db.count_card_photos(current_user.id, [card_id]).get(card_id, 0)
    if existing >= settings.photo_max_per_card:
        raise HTTPException(
            status_code=409,
            detail=f"한 기록에는 사진을 {settings.photo_max_per_card}장까지 붙일 수 있어요.",
        )

    photo = db.save_card_photo(
        current_user.id,
        card_id,
        data,
        file.filename or "photo",
        file.content_type,
        now_local().isoformat(),
    )
    if photo is None:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다")
    return CardPhotoResponse.model_validate(photo)


@router.get("/cards/{card_id}/photos", response_model=CardPhotoListResponse)
def list_card_photos_endpoint(
    card_id: int, current_user: db.User = Depends(get_current_user)
) -> CardPhotoListResponse:
    photos = db.list_card_photos(current_user.id, card_id)
    return CardPhotoListResponse(photos=[CardPhotoResponse.model_validate(p) for p in photos])


@router.get("/photos/{photo_id}")
def serve_photo(photo_id: int, current_user: db.User = Depends(get_current_user)) -> FileResponse:
    """사진 원본을 내려준다.

    `<img src>`로 직접 불리므로 세션 쿠키가 같이 간다(동일 출처) — 별도 토큰이
    필요 없다. 캐시는 `private`으로 둔다: 로그인한 본인만 볼 수 있는 자원이라
    중간 프록시(nginx 포함)가 공유 캐시에 담으면 안 된다. 사진은 한 번 올라오면
    내용이 안 바뀌므로 브라우저 캐시는 길게 잡아도 안전하다.
    """
    photo = db.get_card_photo(current_user.id, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="사진을 찾을 수 없습니다")
    path = db.photo_path(photo.stored_name)
    if not path.exists():
        # 행은 있는데 파일이 없는 경우(수동 삭제, 디스크 유실 등). 500으로 터뜨리는
        # 대신 404로 알려서 화면이 깨진 썸네일 하나만 비우고 넘어가게 한다.
        raise HTTPException(status_code=404, detail="사진 파일을 찾을 수 없습니다")
    return FileResponse(
        path,
        media_type=photo.mime_type,
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


@router.delete("/photos/{photo_id}", status_code=204)
def delete_photo(photo_id: int, current_user: db.User = Depends(get_current_user)) -> None:
    # 없거나 남의 것이어도 204 — 다른 삭제 엔드포인트(`DELETE /api/cards/{id}`)와
    # 같은 멱등 규칙이다.
    db.delete_card_photo(current_user.id, photo_id)
