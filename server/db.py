"""SQLite 기록 — 세션/발화/교정 (+3단계용 기억·재등장 스키마 선반영).

시장 조사 결론 3번: family_facts(가족 기억)·learned_items(표현 재등장 큐)를
처음부터 스키마에 포함해 차별화 기능("기억+재등장 루프")의 기반을 마련한다.
MVP에서는 sessions/utterances/corrections만 실제로 기록한다.
"""
import os
import sqlite3
import time

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at REAL NOT NULL,
    ended_at REAL
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
-- 3단계(기억+재등장 루프)용 스키마 선반영
CREATE TABLE IF NOT EXISTS family_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile TEXT NOT NULL DEFAULT 'default',
    fact TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS learned_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile TEXT NOT NULL DEFAULT 'default',
    expression TEXT NOT NULL,
    meaning TEXT,
    first_seen REAL NOT NULL,
    next_due REAL NOT NULL,
    correct_count INTEGER NOT NULL DEFAULT 0
);
"""


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.executescript(_SCHEMA)
    return conn


def start_session() -> int:
    with _connect() as conn:
        cur = conn.execute("INSERT INTO sessions (started_at) VALUES (?)", (time.time(),))
        return cur.lastrowid


def end_session(session_id: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE sessions SET ended_at=? WHERE id=?", (time.time(), session_id))


def log_turn(session_id: int, user_text: str, reply: str, corrections: list[dict]) -> None:
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


def session_stats(session_id: int) -> dict:
    with _connect() as conn:
        n_user = conn.execute(
            "SELECT COUNT(*) FROM utterances WHERE session_id=? AND role='user'",
            (session_id,),
        ).fetchone()[0]
        corrections = conn.execute(
            "SELECT original, corrected, note FROM corrections WHERE session_id=? ORDER BY ts",
            (session_id,),
        ).fetchall()
    return {
        "sentences_spoken": n_user,
        "corrections": [
            {"original": o, "corrected": c, "note": n} for o, c, n in corrections
        ],
    }
