"""SQLite 기록 — 프로필/세션/발화/교정 + 기억·재등장 루프 (3단계).

3단계에서 실제로 켜진 것:
- profiles        : 가족 프로필 (아이 1 + 성인 2). 레벨·목표·관심사 = 온보딩 결과.
- family_facts    : 대화에서 배운 개인 사실 (프롬프트에 주입 → "기억하는 친구" 경험)
- learned_items   : 교정·새 표현 자동 저장 = 단어장 + 재등장 큐(가벼운 간격 반복,
                    본격 SRS는 4단계). next_due가 지난 항목을 세션 시작 시 프롬프트에
                    주입해 자연 재등장시킨다.

주의: 2단계까지의 DB(레거시)는 sessions에 profile_id가 없고
family_facts/learned_items가 옛 스키마(빈 테이블)라서 _migrate()가 보정한다.
"""
import os
import sqlite3
import time
from datetime import date, datetime, timedelta

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL DEFAULT 'adult',        -- 'child' | 'adult'
    level TEXT NOT NULL DEFAULT 'beginner',    -- 'beginner' | 'intermediate' | 'advanced'
    goals TEXT NOT NULL DEFAULT '',            -- 온보딩: 학습 목표 (자유 텍스트)
    interests TEXT NOT NULL DEFAULT '',        -- 온보딩: 관심사·상황 → family_facts 시드
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at REAL NOT NULL,
    ended_at REAL,
    profile_id INTEGER REFERENCES profiles(id)
);
CREATE TABLE IF NOT EXISTS utterances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    role TEXT NOT NULL,           -- 'user' | 'assistant'
    text TEXT NOT NULL,
    ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    original TEXT NOT NULL,
    corrected TEXT NOT NULL,
    note TEXT,
    ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS family_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    fact TEXT NOT NULL,
    created_at REAL NOT NULL,
    UNIQUE(profile_id, fact)
);
CREATE TABLE IF NOT EXISTS learned_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    expression TEXT NOT NULL,
    meaning TEXT NOT NULL DEFAULT '',          -- 한국어 뜻/설명
    source TEXT NOT NULL DEFAULT 'correction', -- 'correction' | 'taught'
    first_seen REAL NOT NULL,
    last_seen REAL NOT NULL,
    next_due REAL NOT NULL,
    times_seen INTEGER NOT NULL DEFAULT 1,
    UNIQUE(profile_id, expression)
);
"""


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _migrate(conn: sqlite3.Connection) -> None:
    """2단계 레거시 DB 보정. 새 DB에는 아무 것도 하지 않는다."""
    if "profile_id" not in _columns(conn, "sessions"):
        conn.execute("ALTER TABLE sessions ADD COLUMN profile_id INTEGER REFERENCES profiles(id)")
    # 옛 선반영 스키마(profile TEXT)는 한 번도 기록된 적 없는 빈 테이블 → 새 스키마로 재생성
    for table in ("family_facts", "learned_items"):
        cols = _columns(conn, table)
        if cols and "profile_id" not in cols:
            conn.execute(f"DROP TABLE {table}")
    conn.executescript(_SCHEMA)


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.executescript(_SCHEMA)
    _migrate(conn)
    return conn


# ──────────────────────────── 프로필 ────────────────────────────

def create_profile(name: str, kind: str, level: str,
                   goals: str = "", interests: str = "") -> int:
    """온보딩: 프로필 생성 + 관심사·목표를 family_facts로 시드.

    시드 덕분에 첫 세션부터 Emma가 "너 축구 좋아한다며?"처럼 아는 척할 수 있다.
    """
    now = time.time()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO profiles (name, kind, level, goals, interests, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (name.strip(), kind, level, goals.strip(), interests.strip(), now),
        )
        pid = cur.lastrowid
        seeds = []
        if interests.strip():
            seeds.append(f"Interests: {interests.strip()}")
        if goals.strip():
            seeds.append(f"Learning goal: {goals.strip()}")
        for fact in seeds:
            conn.execute(
                "INSERT OR IGNORE INTO family_facts (profile_id, fact, created_at) "
                "VALUES (?,?,?)", (pid, fact, now),
            )
        return pid


def list_profiles() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, name, kind, level, goals, interests FROM profiles ORDER BY id"
        ).fetchall()
    return [
        {"id": r[0], "name": r[1], "kind": r[2], "level": r[3],
         "goals": r[4], "interests": r[5]}
        for r in rows
    ]


def get_profile(profile_id: int) -> dict | None:
    for p in list_profiles():
        if p["id"] == profile_id:
            return p
    return None


# ──────────────────────────── 세션/턴 ────────────────────────────

def start_session(profile_id: int | None = None) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO sessions (started_at, profile_id) VALUES (?,?)",
            (time.time(), profile_id),
        )
        return cur.lastrowid


def end_session(session_id: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE sessions SET ended_at=? WHERE id=?", (time.time(), session_id))


def log_turn(session_id: int, user_text: str, reply: str,
             corrections: list[dict], profile_id: int | None = None,
             memory: list[str] | None = None, taught: list[dict] | None = None) -> None:
    """한 턴 기록. 교정→learned_items(단어장), memory→family_facts, taught→learned_items."""
    now = time.time()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO utterances (session_id, role, text, ts) VALUES (?,?,?,?)",
            (session_id, "user", user_text, now),
        )
        conn.execute(
            "INSERT INTO utterances (session_id, role, text, ts) VALUES (?,?,?,?)",
            (session_id, "assistant", reply, now),
        )
        for c in corrections:
            conn.execute(
                "INSERT INTO corrections (session_id, original, corrected, note, ts) "
                "VALUES (?,?,?,?,?)",
                (session_id, c.get("original", ""), c.get("corrected", ""),
                 c.get("note", ""), now),
            )
        if profile_id is None:
            return
        for c in corrections:
            if c.get("corrected"):
                _upsert_learned(conn, profile_id, c["corrected"],
                                c.get("note", ""), "correction", now)
        for t in (taught or []):
            if t.get("expression"):
                _upsert_learned(conn, profile_id, t["expression"],
                                t.get("meaning", ""), "taught", now)
        for fact in (memory or []):
            fact = str(fact).strip()
            if fact:
                conn.execute(
                    "INSERT OR IGNORE INTO family_facts (profile_id, fact, created_at) "
                    "VALUES (?,?,?)", (profile_id, fact, now),
                )


def _upsert_learned(conn: sqlite3.Connection, profile_id: int, expression: str,
                    meaning: str, source: str, now: float) -> None:
    # 첫 복습은 다음날(+1일). 이후 간격은 mark_reviewed에서 늘어난다.
    conn.execute(
        "INSERT INTO learned_items "
        "(profile_id, expression, meaning, source, first_seen, last_seen, next_due) "
        "VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(profile_id, expression) DO UPDATE SET "
        "last_seen=excluded.last_seen, "
        "meaning=CASE WHEN excluded.meaning != '' THEN excluded.meaning ELSE meaning END",
        (profile_id, expression.strip(), meaning.strip(), source, now, now, now + 86400),
    )


# ──────────────────── 기억 + 재등장 루프 ────────────────────

def recent_facts(profile_id: int, limit: int = 8) -> list[str]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT fact FROM family_facts WHERE profile_id=? "
            "ORDER BY created_at DESC LIMIT ?", (profile_id, limit),
        ).fetchall()
    return [r[0] for r in rows]


def due_items(profile_id: int, limit: int = 3) -> list[dict]:
    """복습 시점이 지난 표현 — 세션 시작 시 프롬프트에 주입해 재등장시킨다."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, expression, meaning FROM learned_items "
            "WHERE profile_id=? AND next_due<=? ORDER BY next_due LIMIT ?",
            (profile_id, time.time(), limit),
        ).fetchall()
    return [{"id": r[0], "expression": r[1], "meaning": r[2]} for r in rows]


def mark_reviewed(item_ids: list[int]) -> None:
    """재등장시킨 항목의 다음 복습 간격을 늘린다 (1일 → 2.5일 → 6일…)."""
    if not item_ids:
        return
    now = time.time()
    with _connect() as conn:
        for iid in item_ids:
            conn.execute(
                "UPDATE learned_items SET times_seen=times_seen+1, last_seen=?, "
                "next_due=? + 86400 * (2.5 * times_seen) WHERE id=?",
                (now, now, iid),
            )


def notebook(profile_id: int, limit: int = 200) -> list[dict]:
    """단어장 — 교정으로 배운 문장 + Emma가 가르쳐준 표현."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT expression, meaning, source, first_seen, times_seen "
            "FROM learned_items WHERE profile_id=? ORDER BY first_seen DESC LIMIT ?",
            (profile_id, limit),
        ).fetchall()
    return [
        {"expression": r[0], "meaning": r[1], "source": r[2],
         "first_seen": r[3], "times_seen": r[4]}
        for r in rows
    ]


# ──────────────────────────── 리포트/통계 ────────────────────────────

def streak_days(profile_id: int) -> int:
    """오늘(또는 어제)부터 연속으로 대화한 날 수."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT date(started_at, 'unixepoch', 'localtime') "
            "FROM sessions WHERE profile_id=?", (profile_id,),
        ).fetchall()
    days = {datetime.strptime(r[0], "%Y-%m-%d").date() for r in rows}
    if not days:
        return 0
    day = date.today()
    if day not in days:
        day -= timedelta(days=1)     # 오늘 아직 안 했어도 어제까지의 스트릭 유지
        if day not in days:
            return 0
    streak = 0
    while day in days:
        streak += 1
        day -= timedelta(days=1)
    return streak


def session_stats(session_id: int) -> dict:
    with _connect() as conn:
        row = conn.execute(
            "SELECT profile_id, started_at FROM sessions WHERE id=?", (session_id,),
        ).fetchone()
        profile_id, started_at = (row or (None, None))
        n_user = conn.execute(
            "SELECT COUNT(*) FROM utterances WHERE session_id=? AND role='user'",
            (session_id,),
        ).fetchone()[0]
        corrections = conn.execute(
            "SELECT original, corrected, note FROM corrections WHERE session_id=? ORDER BY ts",
            (session_id,),
        ).fetchall()
        taught = []
        if profile_id is not None and started_at is not None:
            taught = conn.execute(
                "SELECT expression, meaning FROM learned_items "
                "WHERE profile_id=? AND source='taught' AND first_seen>=? "
                "ORDER BY first_seen", (profile_id, started_at),
            ).fetchall()
    stats = {
        "sentences_spoken": n_user,
        "duration_sec": int(time.time() - started_at) if started_at else 0,
        "corrections": [
            {"original": o, "corrected": c, "note": n} for o, c, n in corrections
        ],
        "taught": [{"expression": e, "meaning": m} for e, m in taught],
    }
    if profile_id is not None:
        stats["streak_days"] = streak_days(profile_id)
    return stats


def history(profile_id: int, limit: int = 30) -> list[dict]:
    """과거 세션 목록 — 부모가 아이의 학습 기록을 보는 용도."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT s.id, s.started_at, s.ended_at, "
            " (SELECT COUNT(*) FROM utterances u WHERE u.session_id=s.id AND u.role='user'), "
            " (SELECT COUNT(*) FROM corrections c WHERE c.session_id=s.id) "
            "FROM sessions s WHERE s.profile_id=? ORDER BY s.started_at DESC LIMIT ?",
            (profile_id, limit),
        ).fetchall()
    return [
        {"session_id": r[0], "started_at": r[1], "ended_at": r[2],
         "sentences_spoken": r[3], "corrections": r[4]}
        for r in rows
    ]
