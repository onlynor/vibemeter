"""End-to-end: run the real TaskManager pipeline against a stubbed crawler
and assert source_stats lands in the persisted summary."""
import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Point the DB at a scratch file before anything imports DB_PATH.
tmpdir = tempfile.mkdtemp()
from app import config
config.DB_PATH = Path(tmpdir) / "t.db"
config.DATA_DIR = Path(tmpdir)

import app.database as database
database.DB_PATH = config.DB_PATH
import app.tasks.manager as mgr
mgr.DB_PATH = config.DB_PATH

from app.crawlers.base import BaseCrawler


class Stub(BaseCrawler):
    name = "auto"
    label = "聚合"

    async def fetch(self, keyword, target_count, progress_cb):
        yield [f"这部电影真的很好看，非常喜欢 {i}" for i in range(30)]
        yield [f"太难看了，浪费时间 {i}" for i in range(30)]

    def get_source_stats(self):
        return {"douban": 30, "bilibili": 30}


async def main():
    await database.init_db()
    mgr.get_crawler = lambda platform, platforms=None: Stub()

    m = mgr.TaskManager()
    task_id = await m.create_task("测试", "auto", 60)
    # drain progress queue so the pipeline isn't blocked, wait for the task
    task = m._tasks[task_id]
    await asyncio.wait_for(task, timeout=120)

    import aiosqlite
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT status, error FROM tasks WHERE task_id=?", (task_id,))
        trow = await cur.fetchone()
        cur = await db.execute("SELECT summary_json FROM results WHERE task_id=?", (task_id,))
        row = await cur.fetchone()

    print(f"  task status={trow['status']} error={trow['error']}")
    assert trow["status"] == "completed", dict(trow)
    assert row, "no results row"
    summary = json.loads(row["summary_json"])
    print(f"  total={summary['total']} pos={summary['positive']} neg={summary['negative']}")
    print(f"  source_stats={summary.get('source_stats')}")
    assert summary.get("source_stats") == {"douban": 30, "bilibili": 30}, summary.get("source_stats")
    print("\nPIPELINE OK")


asyncio.run(main())
