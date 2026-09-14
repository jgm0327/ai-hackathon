"""카드/프로젝트 영속 저장 — Track B 담당 (CLAUDE.md P0 1순위, 9/13 피벗 신규).

이전까지는 `st.session_state`뿐이라 새로고침하면 모든 카드가 소실됐다.
이 제품의 핵심 가치("시간차 누적")는 영속 저장 없이는 성립하지 않는다.

SQLite로 충분하다 — 단일 VM, 단일 프로세스, 데이터 수천 건 규모라
별도 DB 서버를 띄울 이유가 없다 (docs/02-architecture.md 4.1절 참고).

프로젝트는 사람이 만들고(`create_project`), 그 안의 작업 묶음은 AI가 만든다
(`build_resume()`이 그때그때 LLM으로 묶음 — DB에 저장하지 않는다. CLAUDE.md 3장).

**구현 노트 (9/14, 카카오 로그인 Phase A)**: `users`/`sessions` 테이블과 관련 함수를
여기 추가한다. `projects`/`cards`/`profile`은 아직 손대지 않는다(Phase B에서 user_id를
배선한다) — Phase A는 인증 배관만 독립적으로 완성해서 검증하기 위해 의도적으로 범위를
좁혔다(계획서 6장). 세션은 JWT가 아니라 opaque 토큰 + DB 테이블 방식을 쓴다 — 이
저장소가 지금까지 ORM/서명 라이브러리 없이 raw sqlite3만 써왔던 패턴과 더 잘 맞고,
로그아웃(즉시 무효화)이 `DELETE` 한 줄로 끝난다.
"""
import json
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.config import settings
from src.parsing.parser import ParsedEntry


@dataclass
class User:
    id: int
    kakao_id: str
    nickname: str | None
    profile_image_url: str | None
    created_at: str
    last_login_at: str


@dataclass
class Session:
    id: str
    user_id: int
    created_at: str
    expires_at: str


@dataclass
class Card:
    id: int
    project_id: int | None
    raw_text: str
    refined_sentence: str
    skill_tags: list[str]
    confidence: float
    created_at: str


@dataclass
class Project:
    id: int
    name: str
    started_at: str
    ended_at: str | None
    is_current: bool


@dataclass
class Profile:
    """온보딩에서 받는 유저 프로필 — 싱글턴(단일 유저 데모 전제, 인증 없음).

    `years_segment`는 CLAUDE.md 2.4 원칙(연차 직접 입력 배제)에 따라 자유 입력이
    아니라 4개 세그먼트 중 하나만 허용한다: "1-3", "4-6", "7-10", "10+".
    """

    job_field: str | None
    job_detail: str | None
    years_segment: str | None


def _connect() -> sqlite3.Connection:
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """스키마를 초기화한다. 몇 번을 다시 호출해도 안전하다(멱등)."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id                INTEGER PRIMARY KEY,
                kakao_id          TEXT NOT NULL UNIQUE,
                nickname          TEXT,
                profile_image_url TEXT,
                created_at        TEXT NOT NULL,
                last_login_at     TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id         TEXT PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id          INTEGER PRIMARY KEY,
                user_id     INTEGER NOT NULL REFERENCES users(id),
                name        TEXT NOT NULL,
                started_at  TEXT NOT NULL,
                ended_at    TEXT,
                is_current  INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cards (
                id               INTEGER PRIMARY KEY,
                user_id          INTEGER NOT NULL REFERENCES users(id),
                project_id       INTEGER REFERENCES projects(id),
                raw_text         TEXT NOT NULL,
                refined_sentence TEXT NOT NULL,
                skill_tags       TEXT NOT NULL,
                confidence       REAL,
                created_at       TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS profile (
                user_id       INTEGER PRIMARY KEY REFERENCES users(id),
                job_field     TEXT,
                job_detail    TEXT,
                years_segment TEXT
            )
            """
        )


def upsert_user(
    kakao_id: str, nickname: str | None, profile_image_url: str | None, now: str
) -> int:
    """카카오 id로 유저를 찾아 로그인 정보를 갱신하거나, 없으면 새로 만든다.

    매 로그인마다 호출된다 — 닉네임/프로필 사진은 카카오 쪽에서 바뀔 수 있으므로
    로그인 때마다 최신값으로 덮어쓰고 `last_login_at`도 갱신한다.
    """
    init_db()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO users (kakao_id, nickname, profile_image_url, created_at, last_login_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(kakao_id) DO UPDATE SET
                nickname = excluded.nickname,
                profile_image_url = excluded.profile_image_url,
                last_login_at = excluded.last_login_at
            """,
            (kakao_id, nickname, profile_image_url, now, now),
        )
        row = conn.execute("SELECT id FROM users WHERE kakao_id = ?", (kakao_id,)).fetchone()
        return row["id"]


def get_user(user_id: int) -> User | None:
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_user(row) if row else None


def create_session(user_id: int, ttl_days: int) -> Session:
    """새 세션을 만들어 반환한다. `id`(고엔트로피 opaque 토큰)가 곧 쿠키 값이다."""
    init_db()
    session_id = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=ttl_days)
    with _connect() as conn:
        conn.execute(
            "INSERT INTO sessions (id, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (session_id, user_id, now.isoformat(), expires_at.isoformat()),
        )
    return Session(id=session_id, user_id=user_id, created_at=now.isoformat(), expires_at=expires_at.isoformat())


def get_session(session_id: str) -> Session | None:
    """세션을 조회한다. 존재하지 않거나 만료됐으면 None — 호출부가 따로 만료를 체크할 필요 없다."""
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        return None
    session = _row_to_session(row)
    if datetime.fromisoformat(session.expires_at) < datetime.now(timezone.utc):
        return None
    return session


def delete_session(session_id: str) -> None:
    """세션을 삭제한다(로그아웃). 존재하지 않아도 조용히 무시한다(멱등)."""
    init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def save_card(user_id: int, project_id: int | None, parsed: ParsedEntry, created_at: str) -> int:
    """파싱된 카드 한 장을 저장한다. project_id가 None이면 프로젝트 미배정 상태로 저장된다."""
    init_db()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO cards
                (user_id, project_id, raw_text, refined_sentence, skill_tags, confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                project_id,
                parsed.raw_text,
                parsed.refined_sentence,
                json.dumps(parsed.skill_tags, ensure_ascii=False),
                parsed.confidence,
                created_at,
            ),
        )
        return cur.lastrowid


def list_cards(user_id: int, project_id: int | None = None) -> list[Card]:
    """유저의 카드 목록을 오래된 순으로 반환한다. project_id 생략 시 그 유저의 전체."""
    init_db()
    with _connect() as conn:
        if project_id is not None:
            rows = conn.execute(
                "SELECT * FROM cards WHERE user_id = ? AND project_id = ? ORDER BY created_at",
                (user_id, project_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM cards WHERE user_id = ? ORDER BY created_at", (user_id,)
            ).fetchall()
    return [_row_to_card(row) for row in rows]


def get_card(user_id: int, card_id: int) -> Card | None:
    """카드 하나를 id로 조회한다. 이 유저 소유가 아니면(다른 유저 카드이거나 존재하지
    않으면) None — 둘을 구분해서 알려주지 않는다(다른 유저 데이터 존재 여부가 새면 안 됨)."""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM cards WHERE id = ? AND user_id = ?", (card_id, user_id)
        ).fetchone()
    return _row_to_card(row) if row else None


def update_card_tags(user_id: int, card_id: int, skill_tags: list[str]) -> Card | None:
    """카드의 skill_tags를 통째로 덮어쓴다 (9/14 신규 — 카테고리 직접 수정).

    LLM이 자동으로 뽑은 태그를 나중에(연 몇 회, `/stack`에서) 사람이 손으로 고칠 수
    있게 하는 기능이다 — 매일 쓰는 입력 경로에는 선택지를 안 넣는다는 원칙(CLAUDE.md
    2.1)과, 저장 시점엔 LLM/임베딩이 자동으로 분류한다는 원칙(2.3)은 그대로 유지하고,
    "저장된 다음에 가끔 고쳐 쓰는" 별개의 경로로만 추가한다.

    이 유저 소유가 아니거나 존재하지 않으면 아무것도 안 바꾸고 None을 반환한다
    (다른 카드 함수들과 동일한 소유권 규칙).
    """
    init_db()
    with _connect() as conn:
        conn.execute(
            "UPDATE cards SET skill_tags = ? WHERE id = ? AND user_id = ?",
            (json.dumps(skill_tags, ensure_ascii=False), card_id, user_id),
        )
    return get_card(user_id, card_id)


def create_project(user_id: int, name: str, started_at: str) -> int:
    """새 프로젝트를 만들고 자동으로 그 유저의 현재(is_current) 프로젝트로 지정한다."""
    init_db()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO projects (user_id, name, started_at, is_current) VALUES (?, ?, ?, 0)",
            (user_id, name, started_at),
        )
        project_id = cur.lastrowid
    set_current_project(user_id, project_id)
    return project_id


def list_projects(user_id: int) -> list[Project]:
    """그 유저의 프로젝트 목록을 시작일 최신순으로 반환한다."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM projects WHERE user_id = ? ORDER BY started_at DESC", (user_id,)
        ).fetchall()
    return [_row_to_project(row) for row in rows]


def set_current_project(user_id: int, project_id: int) -> None:
    """그 유저의 현재 프로젝트를 지정한다. 기존에 is_current였던 프로젝트는 자동 해제된다.

    `WHERE user_id = ?`를 걸어서, 다른 유저의 is_current에는 영향을 주지 않는다.
    """
    init_db()
    with _connect() as conn:
        conn.execute("UPDATE projects SET is_current = 0 WHERE user_id = ?", (user_id,))
        conn.execute(
            "UPDATE projects SET is_current = 1 WHERE id = ? AND user_id = ?",
            (project_id, user_id),
        )


def get_current_project(user_id: int) -> Project | None:
    """그 유저의 is_current=1인 프로젝트를 반환한다. 없으면 None."""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM projects WHERE user_id = ? AND is_current = 1", (user_id,)
        ).fetchone()
    return _row_to_project(row) if row else None


def delete_card(user_id: int, card_id: int) -> None:
    """카드 하나를 삭제한다. 이 유저 소유가 아니거나 존재하지 않아도 조용히 무시한다(멱등)."""
    init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM cards WHERE id = ? AND user_id = ?", (card_id, user_id))


def update_project(user_id: int, project_id: int, **fields) -> None:
    """프로젝트 필드를 부분 업데이트한다 (`name`, `started_at`, `ended_at`, `is_current`만 허용).

    `is_current=True`로 설정하면 `set_current_project()`와 동일하게 기존 current를
    자동으로 해제한다. 그 외 필드는 주어진 것만 갱신한다. 모든 UPDATE에 `user_id` 조건이
    붙어서, 다른 유저의 프로젝트 id를 넘겨도 아무 일도 일어나지 않는다.
    """
    init_db()
    allowed = {"name", "started_at", "ended_at", "is_current"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"알 수 없는 필드: {unknown}")

    if "is_current" in fields:
        is_current = fields.pop("is_current")
        if is_current:
            set_current_project(user_id, project_id)
        else:
            with _connect() as conn:
                conn.execute(
                    "UPDATE projects SET is_current = 0 WHERE id = ? AND user_id = ?",
                    (project_id, user_id),
                )

    if fields:
        columns = ", ".join(f"{key} = ?" for key in fields)
        with _connect() as conn:
            conn.execute(
                f"UPDATE projects SET {columns} WHERE id = ? AND user_id = ?",
                (*fields.values(), project_id, user_id),
            )


def get_profile(user_id: int) -> Profile:
    """그 유저의 온보딩 프로필을 반환한다. 아직 온보딩을 안 했으면 필드가 전부 None인 Profile.

    (프로젝트/카드와 달리 "없으면 None"이 아니라 항상 Profile 객체를 반환한다 —
    프론트가 "아직 값이 없다"와 "조회 자체가 실패했다"를 구분할 필요가 없게 한다.)
    """
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM profile WHERE user_id = ?", (user_id,)).fetchone()
    return _row_to_profile(row) if row else Profile(job_field=None, job_detail=None, years_segment=None)


def save_profile(
    user_id: int, job_field: str | None, job_detail: str | None, years_segment: str | None
) -> None:
    """그 유저의 온보딩 프로필을 저장한다(유저당 1행, upsert). 항상 세 필드 전체를 덮어쓴다."""
    init_db()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO profile (user_id, job_field, job_detail, years_segment)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                job_field = excluded.job_field,
                job_detail = excluded.job_detail,
                years_segment = excluded.years_segment
            """,
            (user_id, job_field, job_detail, years_segment),
        )


def load_seed_cards(user_id: int, path: str = "data/seed_cards.json") -> None:
    """시드 데이터(프로젝트+카드)를 그 유저 소유로 DB에 투입한다. 데모/개발용.

    seed_cards.json 포맷:
        {"projects": [{"name": ..., "started_at": ..., "ended_at": (선택),
                        "cards": [{"created_at": ..., "raw_text": ..., "refined_sentence": ...,
                                   "skill_tags": [...], "confidence": ...}, ...]}, ...]}

    프로젝트는 JSON에 나열된 순서대로 생성되며, 마지막에 생성된 프로젝트가
    자동으로 is_current가 된다(create_project()의 동작) — 그래서 "현재 진행 중인"
    프로젝트를 JSON의 마지막 항목으로 두는 것을 권장한다.
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    for project_data in data.get("projects", []):
        project_id = create_project(user_id, project_data["name"], project_data["started_at"])
        if project_data.get("ended_at"):
            with _connect() as conn:
                conn.execute(
                    "UPDATE projects SET ended_at = ? WHERE id = ?",
                    (project_data["ended_at"], project_id),
                )
        for card_data in project_data.get("cards", []):
            parsed = ParsedEntry(
                raw_text=card_data["raw_text"],
                refined_sentence=card_data["refined_sentence"],
                skill_tags=card_data.get("skill_tags", []),
                confidence=card_data.get("confidence", 0.0),
            )
            save_card(user_id, project_id, parsed, card_data["created_at"])


def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        kakao_id=row["kakao_id"],
        nickname=row["nickname"],
        profile_image_url=row["profile_image_url"],
        created_at=row["created_at"],
        last_login_at=row["last_login_at"],
    )


def _row_to_session(row: sqlite3.Row) -> Session:
    return Session(
        id=row["id"],
        user_id=row["user_id"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
    )


def _row_to_card(row: sqlite3.Row) -> Card:
    return Card(
        id=row["id"],
        project_id=row["project_id"],
        raw_text=row["raw_text"],
        refined_sentence=row["refined_sentence"],
        skill_tags=json.loads(row["skill_tags"]),
        confidence=row["confidence"],
        created_at=row["created_at"],
    )


def _row_to_project(row: sqlite3.Row) -> Project:
    return Project(
        id=row["id"],
        name=row["name"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        is_current=bool(row["is_current"]),
    )


def _row_to_profile(row: sqlite3.Row) -> Profile:
    return Profile(
        job_field=row["job_field"],
        job_detail=row["job_detail"],
        years_segment=row["years_segment"],
    )
