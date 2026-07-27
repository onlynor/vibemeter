"""异步 SQLite 数据库初始化"""
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
    positive_comments_json   TEXT,
    negative_comments_json   TEXT,
    raw_comments_json        TEXT,
    cleaned_comments_json    TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
);

CREATE INDEX IF NOT EXISTS idx_comments_task ON comments(task_id);
CREATE INDEX IF NOT EXISTS idx_comments_label ON comments(task_id, sentiment_label);
"""


async def init_db() -> None:
    """应用启动时创建数据库文件和表"""
    ensure_directories()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(_INIT_SQL)
        await _ensure_columns(db)
        await db.commit()


async def _ensure_columns(db: aiosqlite.Connection) -> None:
    """为旧版数据库添加新的结果列"""
    cursor = await db.execute("PRAGMA table_info(tasks)")
    existing_tasks = {row[1] for row in await cursor.fetchall()}
    if "task_no" not in existing_tasks:
        await db.execute("ALTER TABLE tasks ADD COLUMN task_no INTEGER")
    await _backfill_task_numbers(db)

    cursor = await db.execute("PRAGMA table_info(results)")
    existing = {row[1] for row in await cursor.fetchall()}
    wanted = {
        # 原始/清洗后评论改存 SQLite 后新增，不再落盘到 data/raw、data/cleaned
        "raw_comments_json": "ALTER TABLE results ADD COLUMN raw_comments_json TEXT",
        "cleaned_comments_json": "ALTER TABLE results ADD COLUMN cleaned_comments_json TEXT",
    }
    for name, sql in wanted.items():
        if name not in existing:
            await db.execute(sql)


async def _backfill_task_numbers(db: aiosqlite.Connection) -> None:
    """为缺少任务编号的历史记录回填 task_no"""
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
    """返回一个新的异步数据库连接，调用方负责关闭"""
    return aiosqlite.connect(DB_PATH)
