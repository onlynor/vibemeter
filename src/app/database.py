"""Async SQLite database initialization."""
from __future__ import annotations

import aiosqlite

from app.config import DB_PATH, ensure_directories


_INIT_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    task_no         INTEGER UNIQUE,
    task_id        TEXT PRIMARY KEY,
    keyword        TEXT NOT NULL,
    platform       TEXT NOT NULL,
    target_count   INTEGER NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending',
    current_count  INTEGER DEFAULT 0,
    total_count    INTEGER DEFAULT 0,
    start_time     TEXT,
    end_time       TEXT,
    error          TEXT
);

CREATE TABLE IF NOT EXISTS comments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         TEXT NOT NULL,
    content         TEXT NOT NULL,
    platform        TEXT NOT NULL,
    fetch_time      TEXT NOT NULL,
    sentiment_score REAL,
    sentiment_label TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
);

CREATE TABLE IF NOT EXISTS results (
    task_id                  TEXT PRIMARY KEY,
    summary_json             TEXT,
    positive_words_json      TEXT,
    negative_words_json      TEXT,
    all_words_json           TEXT,
    time_series_json         TEXT,
    heatmap_json             TEXT,
    comparison_words_json    TEXT,
    positive_comments_json   TEXT,
    negative_comments_json   TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
);

CREATE INDEX IF NOT EXISTS idx_comments_task ON comments(task_id);
CREATE INDEX IF NOT EXISTS idx_comments_label ON comments(task_id, sentiment_label);
"""


async def init_db() -> None:
    """Create database file and tables on application startup."""
    ensure_directories()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(_INIT_SQL)
        await _ensure_columns(db)
        await db.commit()


async def _ensure_columns(db: aiosqlite.Connection) -> None:
    """Add new result columns for existing databases created by older builds."""
    cursor = await db.execute("PRAGMA table_info(tasks)")
    existing_tasks = {row[1] for row in await cursor.fetchall()}
    if "task_no" not in existing_tasks:
        await db.execute("ALTER TABLE tasks ADD COLUMN task_no INTEGER")
    await _backfill_task_numbers(db)

    cursor = await db.execute("PRAGMA table_info(results)")
    existing = {row[1] for row in await cursor.fetchall()}
    wanted = {
        "time_series_json": "ALTER TABLE results ADD COLUMN time_series_json TEXT",
        "heatmap_json": "ALTER TABLE results ADD COLUMN heatmap_json TEXT",
        "comparison_words_json": "ALTER TABLE results ADD COLUMN comparison_words_json TEXT",
    }
    for name, sql in wanted.items():
        if name not in existing:
            await db.execute(sql)


async def _backfill_task_numbers(db: aiosqlite.Connection) -> None:
    """Fill missing task_no values for databases created before task numbering."""
    cursor = await db.execute("SELECT COALESCE(MAX(task_no), 0) FROM tasks")
    next_no = (await cursor.fetchone())[0] or 0
    cursor = await db.execute(
        """SELECT task_id
           FROM tasks
           WHERE task_no IS NULL
           ORDER BY start_time, rowid"""
    )
    rows = await cursor.fetchall()
    for row in rows:
        next_no += 1
        await db.execute(
            "UPDATE tasks SET task_no = ? WHERE task_id = ?",
            (next_no, row[0]),
        )


def db_connect() -> aiosqlite.Connection:
    """Return a fresh async connection. Caller is responsible for closing."""
    return aiosqlite.connect(DB_PATH)
