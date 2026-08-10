"""End-to-end: search results reach the summary + LLM context, and a failing
search provider must not fail the task."""
import asyncio, json, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

tmpdir = tempfile.mkdtemp()
from app import config
config.DB_PATH = Path(tmpdir) / "t.db"
config.DATA_DIR = Path(tmpdir)
import app.database as database
database.DB_PATH = config.DB_PATH
import app.tasks.manager as mgr
mgr.DB_PATH = config.DB_PATH

from app.crawlers.base import BaseCrawler
from app.search import registry
from app.search.base import SearchProvider, SearchResult
from app.analysis.llm_insight import build_context


class Stub(BaseCrawler):
    name = "auto"
    label = "聚合"
    async def fetch(self, keyword, target_count, progress_cb):
        yield [f"真的很好看，非常喜欢 {i}" for i in range(20)]
        yield [f"太难看了，浪费时间 {i}" for i in range(20)]


def install_provider(name, *, count=0, boom=None):
    class P(SearchProvider):
        async def search(self, query, *, limit):
            if boom:
                raise RuntimeError(boom)
            return [SearchResult(title=f"{name} 标题{i}", url=f"https://{name}.com/{i}",
                                 snippet=f"{name} 摘要{i}", source=name, rank=i + 1)
                    for i in range(count)]
    P.name = name; P.label = name.upper()
    registry._REGISTRY[name] = P
    return name


async def run_task(providers):
    # restrict search_all to just our stubs, but keep the rest of the real
    # signature so the manager's call site is genuinely exercised
    orig = registry.search_all

    async def patched(query, *, limit=10, providers=None, total_limit=None):
        return await orig(query, limit=limit, providers=stub_providers,
                          total_limit=total_limit)

    stub_providers = providers
    mgr.search_all = patched

    m = mgr.TaskManager()
    tid = await m.create_task("测试", "auto", 40)
    await asyncio.wait_for(m._tasks[tid], timeout=120)
    import aiosqlite
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT status,error FROM tasks WHERE task_id=?", (tid,))
        t = await cur.fetchone()
        cur = await db.execute("SELECT summary_json FROM results WHERE task_id=?", (tid,))
        r = await cur.fetchone()
    return dict(t), (json.loads(r["summary_json"]) if r else None)


async def main():
    await database.init_db()
    mgr.get_crawler = lambda platform, platforms=None: Stub()

    print("case 1: healthy provider")
    names = [install_provider("sp_ok", count=3)]
    t, s = await run_task(names)
    assert t["status"] == "completed", t
    print("   status:", t["status"], "| search_results:", len(s["search_results"]))
    assert len(s["search_results"]) == 3, s["search_results"]
    assert s["search_results"][0]["source"] == "sp_ok"
    assert s["search_status"][0]["ok"] is True
    # sentiment must be computed from comments ONLY (40 comments in, 40 analysed)
    print("   total analysed:", s["total"], "(must equal 40 comments, not 43)")
    assert s["total"] == 40, f"search results leaked into sentiment analysis: {s['total']}"

    ctx = build_context(s, "xml")
    assert "<web_search_context>" in ctx and "sp_ok 标题0" in ctx
    md = build_context(s, "markdown")
    assert "搜索引擎背景资料" in md
    print("   XML + markdown context contain search block: OK")
    for n in names: registry._REGISTRY.pop(n, None)

    print("\ncase 2: provider raises -> task must still complete")
    names = [install_provider("sp_boom", boom="engine down")]
    t, s = await run_task(names)
    print("   status:", t["status"], "| search_results:", len(s["search_results"]),
          "| status msg:", s["search_status"][0]["message"])
    assert t["status"] == "completed", t
    assert s["search_results"] == []
    assert s["search_status"][0]["ok"] is False
    assert s["total"] == 40
    for n in names: registry._REGISTRY.pop(n, None)

    print("\nSEARCH PIPELINE OK")


asyncio.run(main())
