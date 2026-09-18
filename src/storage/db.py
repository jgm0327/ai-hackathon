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
    # 9/16 신규 — 새 홈 화면(Figma 100:692 "01·기록·Tab A", "오늘 남긴 것" 목록)이
    # "09:40" 같은 분 단위 시각을 요구해서 추가했다. `created_at`(날짜만, "YYYY-MM-DD")은
    # `/stack` 주간 스트릭이 정확한 문자열 동등 비교로 의존하고 있어(같은 날짜 카드를
    # 묶는 로직) 절대 건드리지 않고, 시각만 별도 컬럼으로 추가했다 — 기존 동작 무변경,
    # 순수 추가. 예전 카드는 마이그레이션 시점에 없던 컬럼이라 None(빈 문자열).
    created_time: str | None = None


@dataclass
class Project:
    id: int
    name: str
    started_at: str
    ended_at: str | None
    is_current: bool


@dataclass
class ResumeDraft:
    """유저가 직접 손본 경력기술서 초안 (9/14 신규).

    `build_resume()`의 AI 초안 자체(구조화된 StarItem 목록)는 CLAUDE.md 3장에 따라
    여전히 저장하지 않는다 — 저장하는 건 그것과 다른 것으로, "유저가 그 초안을
    가져다 직접 고친 자유 텍스트(마크다운)"다. 한 번 고치기 시작하면 카드 구조와는
    더 이상 엮여 있을 필요가 없는 독립된 문서라(카드가 바뀌어도 재검증/재동기화할
    필요 없음), 3장이 막았던 "AI 그룹핑을 정식 데이터로 저장" 문제가 여기선 생기지
    않는다. 프로젝트당 1개(최신 저장본만 유지, 버전 관리 없음 — 간단한 버전).
    """

    project_id: int
    content: str
    updated_at: str


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
        # 9/16 신규 — 기존에 이미 만들어진 DB 파일엔 `CREATE TABLE IF NOT EXISTS`가
        # 새 컬럼을 추가해주지 않으므로 직접 마이그레이션한다. 멱등(이미 있으면 스킵).
        existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(cards)")}
        if "created_time" not in existing_columns:
            conn.execute("ALTER TABLE cards ADD COLUMN created_time TEXT")
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS resume_drafts (
                project_id INTEGER PRIMARY KEY REFERENCES projects(id),
                user_id    INTEGER NOT NULL REFERENCES users(id),
                content    TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        # 9/18 신규 — "마스터 경력기술서"(여러 프로젝트를 한 문서로, Figma 4.2.1
        # "범위 선택") 초안은 프로젝트 하나에 귀속되지 않아 resume_drafts에 담을 수
        # 없다(그 테이블은 project_id가 PK다). 기존 테이블을 재구성하는 대신 유저당
        # 1개짜리 별도 테이블을 추가한다 — 기존 프로젝트 단위 초안의 동작은 무변경.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS master_resume_drafts (
                user_id    INTEGER PRIMARY KEY REFERENCES users(id),
                content    TEXT NOT NULL,
                updated_at TEXT NOT NULL
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


def save_card(
    user_id: int,
    project_id: int | None,
    parsed: ParsedEntry,
    created_at: str,
    created_time: str | None = None,
) -> int:
    """파싱된 카드 한 장을 저장한다. project_id가 None이면 프로젝트 미배정 상태로 저장된다.

    `created_time`(9/16 신규, "HH:MM")은 선택 — 홈 화면 "오늘 남긴 것" 목록 전용이라
    안 넘기면 그냥 NULL로 저장된다(기존 호출부 하위 호환).
    """
    init_db()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO cards
                (user_id, project_id, raw_text, refined_sentence, skill_tags, confidence,
                 created_at, created_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                project_id,
                parsed.raw_text,
                parsed.refined_sentence,
                json.dumps(parsed.skill_tags, ensure_ascii=False),
                parsed.confidence,
                created_at,
                created_time,
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


def get_skill_category_counts(user_id: int, project_id: int, top_n: int = 4) -> list[tuple[str, int]]:
    """카드를 대표 태그(skill_tags[0]) 기준으로 묶어 몇 장씩 있는지 센다 (9/16 신규,
    Figma 100:692 홈 화면 "무엇이 쌓였나요" 버블 차트).

    태그를 지어내지 않는다(CLAUDE.md 2.2) — 각 카드의 대표 태그는 parse_note()가
    실제로 뽑은 skill_tags의 첫 번째 값을 그대로 쓴다. 상위 top_n개 다음은 전부
    "미분류" 하나로 합친다(태그가 아예 없는 카드도 여기 포함). 반환값의 count 합계는
    항상 해당 프로젝트의 전체 카드 수와 같다 — 카드 한 장은 정확히 한 카테고리에만
    속한다(태그를 여러 개 가진 카드도 대표 태그 하나로만 집계 — 중복 집계 방지).
    """
    cards = list_cards(user_id, project_id)
    counts: dict[str, int] = {}
    for card in cards:
        category = card.skill_tags[0] if card.skill_tags else "미분류"
        counts[category] = counts.get(category, 0) + 1

    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    top = [kv for kv in ranked if kv[0] != "미분류"][:top_n]
    top_names = {name for name, _ in top}
    rest_count = sum(count for name, count in ranked if name not in top_names)

    return top + [("미분류", rest_count)] if rest_count > 0 else top


def list_unassigned_cards(user_id: int) -> list[Card]:
    """프로젝트가 아직 배정되지 않은(`project_id IS NULL`) 카드만 반환한다 (9/14 신규).

    "4.1.1 AI 프로젝트 자동 제안" 기능 전용 — 이미 어떤 프로젝트에 배정된 카드는
    이 함수가 절대 건드리지 않는다. `list_cards(user_id)`는 그대로 두고(기존 계약
    변경 없음) 병행 함수로 추가했다.
    """
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM cards WHERE user_id = ? AND project_id IS NULL ORDER BY created_at",
            (user_id,),
        ).fetchall()
    return [_row_to_card(row) for row in rows]


def bulk_assign_cards_to_project(user_id: int, card_ids: list[int], project_id: int) -> int:
    """주어진 카드들의 project_id를 한 번에 갱신한다 (9/14 신규 — "미분류 카드를
    새 프로젝트로 묶기" 전용).

    이 유저 소유가 아닌 card_id는 조용히 무시한다(다른 카드 함수들과 동일한 소유권
    규칙 — `WHERE ... AND user_id = ?`). 반환값은 실제로 갱신된 행 수라, 호출부가
    "몇 개가 가로채기당해 무시됐는지"를 감지할 수 있다.
    """
    if not card_ids:
        return 0
    init_db()
    placeholders = ",".join("?" for _ in card_ids)
    with _connect() as conn:
        cur = conn.execute(
            f"UPDATE cards SET project_id = ? WHERE id IN ({placeholders}) AND user_id = ?",
            (project_id, *card_ids, user_id),
        )
        return cur.rowcount


def get_card(user_id: int, card_id: int) -> Card | None:
    """카드 하나를 id로 조회한다. 이 유저 소유가 아니면(다른 유저 카드이거나 존재하지
    않으면) None — 둘을 구분해서 알려주지 않는다(다른 유저 데이터 존재 여부가 새면 안 됨)."""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM cards WHERE id = ? AND user_id = ?", (card_id, user_id)
        ).fetchone()
    return _row_to_card(row) if row else None


def update_card(
    user_id: int,
    card_id: int,
    *,
    skill_tags: list[str] | None = None,
    refined_sentence: str | None = None,
    confidence: float | None = None,
) -> Card | None:
    """카드의 skill_tags/refined_sentence/confidence를 손으로(또는 재정리로) 고친다
    (9/14 카테고리 수정 신규, 9/15 문장 수정 + confidence 추가).

    LLM이 자동으로 뽑은 결과를 나중에(연 몇 회, `/stack`에서) 사람이 손으로 고칠 수
    있게 하는 기능이다 — 매일 쓰는 입력 경로에는 선택지를 안 넣는다는 원칙(CLAUDE.md
    2.1)과, 저장 시점엔 LLM/임베딩이 자동으로 분류한다는 원칙(2.3)은 그대로 유지하고,
    "저장된 다음에 가끔 고쳐 쓰는" 별개의 경로로만 추가한다.

    `confidence`는 사람이 직접 고르는 값이 아니라 `pipeline.retry_refinement()`가
    재파싱 결과를 반영할 때만 쓴다 — PATCH API 스키마에는 노출하지 않는다.

    아무 것도 안 넘기면(호출부가 실수한 경우) 아무 것도 안 건드리고 현재 카드를 그대로
    반환한다 — 라우터 쪽에서 이미 "최소 하나"를 강제하지만, 여기서도 안전하게 둔다.

    이 유저 소유가 아니거나 존재하지 않으면 아무것도 안 바꾸고 None을 반환한다
    (다른 카드 함수들과 동일한 소유권 규칙).
    """
    init_db()
    sets: list[str] = []
    params: list[object] = []
    if skill_tags is not None:
        sets.append("skill_tags = ?")
        params.append(json.dumps(skill_tags, ensure_ascii=False))
    if refined_sentence is not None:
        sets.append("refined_sentence = ?")
        params.append(refined_sentence)
    if confidence is not None:
        sets.append("confidence = ?")
        params.append(confidence)
    if sets:
        with _connect() as conn:
            conn.execute(
                f"UPDATE cards SET {', '.join(sets)} WHERE id = ? AND user_id = ?",
                (*params, card_id, user_id),
            )
    return get_card(user_id, card_id)


def update_card_tags(user_id: int, card_id: int, skill_tags: list[str]) -> Card | None:
    """`update_card()`의 태그 전용 래퍼 — 기존 호출부 시그니처를 그대로 유지한다."""
    return update_card(user_id, card_id, skill_tags=skill_tags)


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


def get_project(user_id: int, project_id: int) -> Project | None:
    """프로젝트 하나를 id로 조회한다 (9/14 신규 — "미분류 카드 묶기"에서 방금 만든
    프로젝트를 응답에 바로 실어 보내려고 추가). 이 유저 소유가 아니면(다른 유저
    프로젝트이거나 존재하지 않으면) None — `get_card`와 동일한 소유권 규칙."""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id)
        ).fetchone()
    return _row_to_project(row) if row else None


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


def get_resume_draft(user_id: int, project_id: int) -> ResumeDraft | None:
    """저장된 초안이 없거나, project_id가 이 유저 소유가 아니면 None을 반환한다
    (다른 카드/프로필 함수들과 동일한 소유권 규칙 — 존재 여부 자체를 흘리지 않는다)."""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT d.* FROM resume_drafts d
            JOIN projects p ON p.id = d.project_id
            WHERE d.project_id = ? AND p.user_id = ?
            """,
            (project_id, user_id),
        ).fetchone()
    return _row_to_resume_draft(row) if row else None


def save_resume_draft(user_id: int, project_id: int, content: str, now: str) -> ResumeDraft | None:
    """초안을 저장한다(프로젝트당 1개, upsert). project_id가 이 유저 소유가 아니면
    아무것도 저장하지 않고 None을 반환한다.

    `resume_drafts.project_id`가 PK라, user_id 조건 없이 그냥 UPSERT하면 다른
    유저의 project_id를 넘겼을 때 그 프로젝트의 기존 초안을 덮어쓸 수 있다 —
    그래서 INSERT 전에 반드시 소유권을 먼저 확인한다(`update_project`의
    `WHERE user_id = ?` 가드와 같은 목적, PK 충돌 때문에 그 패턴을 그대로 못 써서
    여기선 사전 체크로 대신한다).
    """
    init_db()
    with _connect() as conn:
        owns = conn.execute(
            "SELECT 1 FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id)
        ).fetchone()
        if not owns:
            return None
        conn.execute(
            """
            INSERT INTO resume_drafts (project_id, user_id, content, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                content = excluded.content,
                updated_at = excluded.updated_at
            """,
            (project_id, user_id, content, now),
        )
    return ResumeDraft(project_id=project_id, content=content, updated_at=now)


def get_master_resume_draft(user_id: int) -> ResumeDraft | None:
    """유저의 "마스터 경력기술서" 초안을 반환한다 (9/18 신규, Figma 4.2.1 범위 선택).

    프로젝트 단위 초안(`get_resume_draft`)과 완전히 별개 저장소다. 반환 타입은
    재사용하되 `project_id`는 마스터를 뜻하는 0으로 채운다 — 프론트/스키마가
    "프로젝트 없음"을 이 값 하나로 판별한다.
    """
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM master_resume_drafts WHERE user_id = ?", (user_id,)
        ).fetchone()
    if row is None:
        return None
    return ResumeDraft(project_id=0, content=row["content"], updated_at=row["updated_at"])


def save_master_resume_draft(user_id: int, content: str, now: str) -> ResumeDraft:
    """마스터 초안을 저장한다(유저당 1개, upsert).

    `save_resume_draft`와 달리 소유권 사전 검사가 필요 없다 — PK가 user_id 자체라
    다른 유저의 행을 건드릴 경로가 존재하지 않는다.
    """
    init_db()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO master_resume_drafts (user_id, content, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                content = excluded.content,
                updated_at = excluded.updated_at
            """,
            (user_id, content, now),
        )
    return ResumeDraft(project_id=0, content=content, updated_at=now)


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
    row_keys = row.keys()
    return Card(
        id=row["id"],
        project_id=row["project_id"],
        raw_text=row["raw_text"],
        refined_sentence=row["refined_sentence"],
        skill_tags=json.loads(row["skill_tags"]),
        confidence=row["confidence"],
        created_at=row["created_at"],
        # "created_time" in row_keys 체크: 마이그레이션 전 스키마로 열린 아주 오래된
        # 연결이 남아있을 극단적 경우를 대비한 방어(평소엔 init_db()가 항상 먼저 돈다).
        created_time=row["created_time"] if "created_time" in row_keys else None,
    )


def _row_to_project(row: sqlite3.Row) -> Project:
    return Project(
        id=row["id"],
        name=row["name"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        is_current=bool(row["is_current"]),
    )


def _row_to_resume_draft(row: sqlite3.Row) -> ResumeDraft:
    return ResumeDraft(
        project_id=row["project_id"],
        content=row["content"],
        updated_at=row["updated_at"],
    )


def _row_to_profile(row: sqlite3.Row) -> Profile:
    return Profile(
        job_field=row["job_field"],
        job_detail=row["job_detail"],
        years_segment=row["years_segment"],
    )
