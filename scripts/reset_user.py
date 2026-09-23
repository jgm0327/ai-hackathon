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
    # 됐다. 그전엔 아래 _delete_push_subscription()이 따로 처리했는데, 저장소 키가
    # sha256(endpoint)라 `str(user_id)`로는 **애초에 한 건도 못 찾았다**(무해한 no-op).
    "push_subscriptions",
    "push_settings",
    "cards",
    "resume_drafts",
    "master_resume_drafts",
    "profile_companies",
    "profile",
    "projects",
    "users",
]


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

    for table in TABLES:
        col = "id" if table == "users" else "user_id"
        n = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = ?", (uid,)).fetchone()[0]
        print(f"  {table:22s}  {n}행")
        if not args.dry_run:
            conn.execute(f"DELETE FROM {table} WHERE {col} = ?", (uid,))
    if not args.dry_run:
        conn.commit()

    print()
    if args.dry_run:
        print("[dry-run] 아무것도 지우지 않았습니다.")
    else:
        print(f"user_id={uid} 삭제 완료. 다음 로그인 때 새 유저로 온보딩부터 시작합니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
