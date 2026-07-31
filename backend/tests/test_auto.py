"""Standalone verification of AutoCrawler balancing / timeout / dedup behaviour.

Run: backend/.venv/bin/python scratchpad/test_auto.py
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.crawlers import auto as auto_mod
from app.crawlers.base import BaseCrawler

# Shrink the gate so the test doesn't wait the real 8s.
auto_mod.FIRST_BATCH_TIMEOUT = 1.0
auto_mod.SOURCE_DEADLINE = 3.0
auto_mod.EMIT_CHUNK = 10


class FakeCrawler(BaseCrawler):
    def __init__(self, name, label, batches, delay=0.0, first_delay=0.0, boom=None):
        self.name = name
        self.label = label
        self._batches = batches
        self._delay = delay
        self._first_delay = first_delay
        self._boom = boom
        self._source_items = []

    async def fetch(self, keyword, target_count, progress_cb):
        if self._first_delay:
            await asyncio.sleep(self._first_delay)
        if self._boom:
            raise RuntimeError(self._boom)
        self.record_source_item({
            "platform": self.name, "title": f"{self.label} post",
            "url": f"https://{self.name}.test/1", "subtitle": "",
            "embed_url": "", "display_type": "post",
        })
        for batch in self._batches:
            yield batch
            await asyncio.sleep(self._delay)


def make_auto(sources):
    a = auto_mod.AutoCrawler()
    a._sources = sources
    return a


async def collect(a, target):
    out = []
    async def cb(cur, msg=""):
        pass
    async for batch in a.fetch("kw", target, cb):
        out.extend(batch)
    return out


async def test_balance():
    """A fast high-volume source must not crowd out slower ones."""
    fast = FakeCrawler("douban", "豆瓣", [[f"d{i}" for i in range(60)]])
    slow = FakeCrawler("bilibili", "B站", [[f"b{i}" for i in range(60)]], first_delay=0.4)
    slow2 = FakeCrawler("tieba", "贴吧", [[f"t{i}" for i in range(60)]], first_delay=0.6)
    a = make_auto([fast, slow, slow2])
    out = await collect(a, 30)
    stats = a.get_source_stats()
    print(f"  balance -> total={len(out)} stats={stats}")
    assert len(out) == 30, f"expected 30, got {len(out)}"
    # Each source should be within a couple of items of an even 10/10/10 split.
    for p in ("douban", "bilibili", "tieba"):
        assert 8 <= stats.get(p, 0) <= 12, f"{p} unbalanced: {stats}"
    print("  balance OK")


async def test_dedup():
    """Identical content reposted across platforms consumes one slot, not three."""
    a1 = FakeCrawler("douban", "豆瓣", [["same", "same", "uniq-d"]])
    a2 = FakeCrawler("bilibili", "B站", [["same", "uniq-b"]])
    a = make_auto([a1, a2])
    out = await collect(a, 50)
    print(f"  dedup -> {sorted(out)}")
    assert sorted(out) == ["same", "uniq-b", "uniq-d"], out
    print("  dedup OK")


async def test_dead_source_does_not_hang():
    """A source that never yields must not stall the aggregate run."""
    class Hanger(FakeCrawler):
        async def fetch(self, keyword, target_count, progress_cb):
            await asyncio.sleep(3600)
            yield []

    good = FakeCrawler("douban", "豆瓣", [["x1", "x2", "x3"]])
    dead = Hanger("weibo", "微博", [])
    a = make_auto([good, dead])
    t0 = time.time()
    out = await collect(a, 50)
    elapsed = time.time() - t0
    print(f"  hang -> got {len(out)} in {elapsed:.2f}s")
    assert out == ["x1", "x2", "x3"], out
    assert elapsed < 5, f"took too long: {elapsed}"
    print("  no-hang OK")


async def test_slow_paginator_bounded_by_deadline():
    """Endless pagination is cut off at SOURCE_DEADLINE."""
    class Endless(FakeCrawler):
        async def fetch(self, keyword, target_count, progress_cb):
            i = 0
            while True:
                yield [f"e{i}"]
                i += 1
                await asyncio.sleep(0.2)

    a = make_auto([Endless("tieba", "贴吧", [])])
    t0 = time.time()
    out = await collect(a, 10_000)   # unreachable target -> deadline must stop it
    elapsed = time.time() - t0
    print(f"  deadline -> got {len(out)} in {elapsed:.2f}s")
    assert elapsed < auto_mod.SOURCE_DEADLINE + 2, f"deadline not enforced: {elapsed}"
    print("  deadline OK")


async def test_all_sources_fail():
    a = make_auto([FakeCrawler("douban", "豆瓣", [], boom="風控")])
    try:
        await collect(a, 10)
    except RuntimeError as exc:
        print(f"  all-fail -> {exc}")
        assert "未能获取真实数据" in str(exc)
        print("  all-fail OK")
        return
    raise AssertionError("expected RuntimeError")


async def test_source_items_still_collected():
    a1 = FakeCrawler("douban", "豆瓣", [["a"]])
    a2 = FakeCrawler("bilibili", "B站", [["b"]])
    a = make_auto([a1, a2])
    await collect(a, 50)
    items = a.get_source_items()
    print(f"  source_items -> {[i['platform'] for i in items]}")
    assert {i["platform"] for i in items} == {"douban", "bilibili"}, items
    print("  source_items OK")


async def main():
    for fn in (
        test_balance, test_dedup, test_dead_source_does_not_hang,
        test_slow_paginator_bounded_by_deadline, test_all_sources_fail,
        test_source_items_still_collected,
    ):
        print(f"{fn.__name__}:")
        await fn()
    print("\nALL PASS")


asyncio.run(main())
