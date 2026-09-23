"""유저 하나를 '가입 전' 상태로 되돌린다 — 데모 리허설/온보딩 재현용.

`users` 행까지 지우므로 다음 카카오 로그인 때 `upsert_user()`가 같은 kakao_id로
**새 유저를 만들고**, `profile`이 비어 있어 `AuthGate`가 `/onboarding`으로 보낸다.
세션·유저를 메모리에 캐시하는 곳이 없으므로 **API 재기동은 필요 없다.**

사용법 (레포 루트에서):
    python scripts/reset_user.py --list
    python scripts/reset_user.py --user-id 2 --dry-run
    python scripts/reset_user.py --user-id 2

주의: 카카오 쪽 세션·동의는 건드리지 않는다. 로그인 창까지 다시 보려면
카카오계정에서 로그아웃(또는 '연결된 서비스 관리'에서 연결 끊기)해야 한다.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import settings  # noqa: E402

# FK 참조 순서대로 — 자식부터 지운다.
# (SQLite는 기본적으로 FK를 강제하지 않지만, 순서를 지켜야 나중에 켜도 안전하다.)
TABLES = [
    "sessions",
    # 9/23 — 푸시 구독/설정이 Upstash에서 SQLite로 옮겨와 평범한 유저 스코프 테이블이
    # 됐다. 그전엔 _delete_push_subscription()이 따로 처리했는데, 저장소 키가
    # sha256(endpoint)라 `str(user_id)`로는 **애초에 한 건도 못 찾았다**(무해한 no-op).
    "push_subscriptions",
    "push_settings",
    # 9/23 — 아래 셋이 빠져 있었다. `users` 행까지 지우면서 이것들만 남으면 **주인 없는
    # 행**이 되고, 다음 로그인 때 같은 kakao_id로 새 user_id가 발급되므로 영영 안 보이는
    # 채로 남는다. notion_connections는 특히 **노션 액세스 토큰**을 들고 있어서,
    # "내 정보를 지운다"는 목적에서 빠뜨리면 안 되는 항목이다.
    "card_photos",  # cards보다 먼저 — 파일 삭제를 위해 아래에서 경로를 먼저 읽는다
    "saved_resumes",
    "notion_connections",
    "cards",
    "resume_drafts",
    "master_resume_drafts",
    "profile_companies",
    "profile",
    "projects",
    "users",
]


def _delete_photo_files(stored_names: list[str], dry_run: bool) -> None:
    """기록에 첨부된 사진 파일을 디스크에서 지운다 (9/23 신규).

    DB 행만 지우면 이미지 바이트는 그대로 남는다. 백업 내보내기에도 안 잡히고
    화면에도 안 보이는 파일이라, 한 번 놓치면 발견될 일이 없다.
    """
    photo_dir = Path(settings.photo_dir)
    print(f"  {'사진 파일':22s}  {len(stored_names)}개  ({photo_dir})")
    if dry_run:
        return
    for name in stored_names:
        target = photo_dir / name
        try:
            target.unlink(missing_ok=True)
        except OSError as exc:
            # 파일 하나가 안 지워져도 나머지 삭제를 막지 않는다 — DB는 이미 커밋됐다.
            print(f"    사진 삭제 실패({name}): {exc}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--user-id", type=int, help="지울 유저 id")
    ap.add_argument("--list", action="store_true", help="유저 목록만 출력")
    ap.add_argument("--dry-run", action="store_true", help="세어보기만 하고 지우지 않음")
    args = ap.parse_args()

    db_path = Path(settings.db_path)
    if not db_path.exists():
        print(f"DB 없음: {db_path.resolve()}", file=sys.stderr)
        print("레포 루트에서 실행했는지, .env의 DB_PATH가 맞는지 확인하세요.", file=sys.stderr)
        return 1
    print(f"DB: {db_path.resolve()}\n")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    if args.list or args.user_id is None:
        rows = list(conn.execute("SELECT id, kakao_id, nickname, created_at FROM users ORDER BY id"))
        if not rows:
            print("  (유저 없음)")
        for r in rows:
            cards = conn.execute(
                "SELECT COUNT(*) FROM cards WHERE user_id = ?", (r["id"],)
            ).fetchone()[0]
            print(
                f"  id={r['id']}  kakao_id={r['kakao_id']}  "
                f"nickname={r['nickname']!r}  cards={cards}  created={r['created_at']}"
            )
        if args.user_id is None:
            print("\n--user-id <N> 으로 지울 유저를 지정하세요.")
        return 0

    uid = args.user_id
    if conn.execute("SELECT 1 FROM users WHERE id = ?", (uid,)).fetchone() is None:
        print(f"user_id={uid} 없음", file=sys.stderr)
        return 1

    # 사진은 DB에 메타만 있고 바이트는 디스크에 있다(`settings.photo_dir`). 행을 지우기
    # **전에** 파일명을 읽어둬야 한다 — 지운 뒤에는 어느 파일이 이 유저 것이었는지
    # 알 방법이 없어 디스크에 고아 파일이 영영 남는다.
    photo_names = [
        r[0] for r in conn.execute(
            "SELECT stored_name FROM card_photos WHERE user_id = ?", (uid,)
        )
    ]

    for table in TABLES:
        col = "id" if table == "users" else "user_id"
        n = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = ?", (uid,)).fetchone()[0]
        print(f"  {table:22s}  {n}행")
        if not args.dry_run:
            conn.execute(f"DELETE FROM {table} WHERE {col} = ?", (uid,))
    if not args.dry_run:
        conn.commit()

    _delete_photo_files(photo_names, args.dry_run)

    print()
    if args.dry_run:
        print("[dry-run] 아무것도 지우지 않았습니다.")
    else:
        print(f"user_id={uid} 삭제 완료. 다음 로그인 때 새 유저로 온보딩부터 시작합니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
