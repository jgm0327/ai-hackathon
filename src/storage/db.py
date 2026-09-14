"""카드/프로젝트 영속 저장 — Track B 담당 (CLAUDE.md P0 1순위, 9/13 피벗 신규).

이전까지는 `st.session_state`뿐이라 새로고침하면 모든 카드가 소실됐다.
이 제품의 핵심 가치("시간차 누적")는 영속 저장 없이는 성립하지 않는다.

SQLite로 충분하다 — 단일 VM, 단일 프로세스, 데이터 수천 건 규모라
별도 DB 서버를 띄울 이유가 없다 (docs/02-architecture.md 4.1절 참고).

프로젝트는 사람이 만들고(`create_project`), 그 안의 작업 묶음은 AI가 만든다
(`build_resume()`이 그때그때 LLM으로 묶음 — DB에 저장하지 않는다. CLAUDE.md 3장).
"""
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from src.config import settings
from src.parsing.parser import ParsedEntry


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
            CREATE TABLE IF NOT EXISTS projects (
                id          INTEGER PRIMARY KEY,
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
                id           INTEGER PRIMARY KEY CHECK (id = 1),
                job_field    TEXT,
                job_detail   TEXT,
                years_segment TEXT
            )
            """
        )


def save_card(project_id: int | None, parsed: ParsedEntry, created_at: str) -> int:
    """파싱된 카드 한 장을 저장한다. project_id가 None이면 프로젝트 미배정 상태로 저장된다."""
    init_db()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO cards
                (project_id, raw_text, refined_sentence, skill_tags, confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                parsed.raw_text,
                parsed.refined_sentence,
                json.dumps(parsed.skill_tags, ensure_ascii=False),
                parsed.confidence,
                created_at,
            ),
        )
        return cur.lastrowid


def list_cards(project_id: int | None = None) -> list[Card]:
    """카드 목록을 오래된 순으로 반환한다. project_id 생략 시 전체."""
    init_db()
    with _connect() as conn:
        if project_id is not None:
            rows = conn.execute(
                "SELECT * FROM cards WHERE project_id = ? ORDER BY created_at", (project_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM cards ORDER BY created_at").fetchall()
    return [_row_to_card(row) for row in rows]


def get_card(card_id: int) -> Card | None:
    """카드 하나를 id로 조회한다. 없으면 None (JD 매칭 등 단건 조회가 필요한 API용)."""
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
    return _row_to_card(row) if row else None


def create_project(name: str, started_at: str) -> int:
    """새 프로젝트를 만들고 자동으로 현재(is_current) 프로젝트로 지정한다."""
    init_db()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO projects (name, started_at, is_current) VALUES (?, ?, 0)",
            (name, started_at),
        )
        project_id = cur.lastrowid
    set_current_project(project_id)
    return project_id


def list_projects() -> list[Project]:
    """프로젝트 목록을 시작일 최신순으로 반환한다."""
    init_db()
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY started_at DESC").fetchall()
    return [_row_to_project(row) for row in rows]


def set_current_project(project_id: int) -> None:
    """현재 프로젝트를 지정한다. 기존에 is_current였던 프로젝트는 자동으로 해제된다."""
    init_db()
    with _connect() as conn:
        conn.execute("UPDATE projects SET is_current = 0")
        conn.execute("UPDATE projects SET is_current = 1 WHERE id = ?", (project_id,))


def get_current_project() -> Project | None:
    """is_current=1인 프로젝트를 반환한다. 프로젝트가 하나도 없으면 None."""
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM projects WHERE is_current = 1").fetchone()
    return _row_to_project(row) if row else None


def delete_card(card_id: int) -> None:
    """카드 하나를 삭제한다. 존재하지 않는 id여도 조용히 무시한다(멱등)."""
    init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM cards WHERE id = ?", (card_id,))


def update_project(project_id: int, **fields) -> None:
    """프로젝트 필드를 부분 업데이트한다 (`name`, `started_at`, `ended_at`, `is_current`만 허용).

    `is_current=True`로 설정하면 `set_current_project()`와 동일하게 기존 current를
    자동으로 해제한다. 그 외 필드는 주어진 것만 갱신한다.
    """
    init_db()
    allowed = {"name", "started_at", "ended_at", "is_current"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"알 수 없는 필드: {unknown}")

    if "is_current" in fields:
        is_current = fields.pop("is_current")
        if is_current:
            set_current_project(project_id)
        else:
            with _connect() as conn:
                conn.execute(
                    "UPDATE projects SET is_current = 0 WHERE id = ?", (project_id,)
                )

    if fields:
        columns = ", ".join(f"{key} = ?" for key in fields)
        with _connect() as conn:
            conn.execute(
                f"UPDATE projects SET {columns} WHERE id = ?",
                (*fields.values(), project_id),
            )


def get_profile() -> Profile:
    """온보딩 프로필을 반환한다. 아직 온보딩을 안 했으면 필드가 전부 None인 Profile.

    (프로젝트/카드와 달리 "없으면 None"이 아니라 항상 Profile 객체를 반환한다 —
    프론트가 "아직 값이 없다"와 "조회 자체가 실패했다"를 구분할 필요가 없게 한다.)
    """
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
    return _row_to_profile(row) if row else Profile(job_field=None, job_detail=None, years_segment=None)


def save_profile(job_field: str | None, job_detail: str | None, years_segment: str | None) -> None:
    """온보딩 프로필을 저장한다(싱글턴, upsert). 항상 세 필드 전체를 덮어쓴다."""
    init_db()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO profile (id, job_field, job_detail, years_segment)
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                job_field = excluded.job_field,
                job_detail = excluded.job_detail,
                years_segment = excluded.years_segment
            """,
            (job_field, job_detail, years_segment),
        )


def load_seed_cards(path: str = "data/seed_cards.json") -> None:
    """시드 데이터(프로젝트+카드)를 DB에 투입한다. 데모/개발용.

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
        project_id = create_project(project_data["name"], project_data["started_at"])
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
            save_card(project_id, parsed, card_data["created_at"])


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
