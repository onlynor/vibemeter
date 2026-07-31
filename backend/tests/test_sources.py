"""Verify the douban/tieba concurrent-chunk rewrites, incl. failure fallbacks."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.crawlers.douban import DoubanCrawler
from app.crawlers.tieba import TiebaCrawler


async def noop(cur, msg=""):
    pass


async def drain(agen):
    out = []
    async for b in agen:
        out.extend(b)
    return out


def _subjects(n):
    return [
        {"kind": "movie", "sid": str(i), "title": f"T{i}", "subtitle": "",
         "url": f"https://movie.douban.com/subject/{i}/"}
        for i in range(n)
    ]


async def test_douban_happy():
    """Two pages per subject, then exhausted."""
    c = DoubanCrawler()
    c._search_subjects = lambda *a, **k: _ret(_subjects(5))
    async def fake_page(client, subject, page):
        if page >= 2:
            return []
        return [f"c{subject['sid']}-p{page}-{i}" for i in range(5)]
    c._fetch_page = fake_page
    out = await drain(c.fetch("kw", 1000, noop))
    print(f"  douban happy -> {len(out)} comments, {len(c.get_source_items())} source items")
    assert len(out) == 50, len(out)          # 5 subjects x 2 pages x 5
    assert len({o.split('-')[0] for o in out}) == 5, "not all subjects contributed"
    print("  douban happy OK")


async def test_douban_streams_first_page_early():
    """The first batch must not wait for all pages (the bug that got douban
    dropped from aggregate runs)."""
    c = DoubanCrawler()
    c._search_subjects = lambda *a, **k: _ret(_subjects(3))
    async def fake_page(client, subject, page):
        await asyncio.sleep(0.2)
        return [] if page >= 4 else [f"s{subject['sid']}p{page}"]
    c._fetch_page = fake_page

    loop = asyncio.get_running_loop()
    t0 = loop.time()
    first_at = None
    async for _ in c.fetch("kw", 1000, noop):
        if first_at is None:
            first_at = loop.time() - t0
            break
    print(f"  douban first-batch at {first_at:.2f}s (all 4 pages would be ~4x longer)")
    assert first_at < 0.5, f"first batch too late: {first_at}"
    print("  douban streaming OK")


async def test_douban_one_subject_raises():
    c = DoubanCrawler()
    c._search_subjects = lambda *a, **k: _ret(_subjects(3))
    async def fake_page(client, subject, page):
        if subject["sid"] == "1":
            raise RuntimeError("boom")
        return [f"c{subject['sid']}"] if page == 0 else []
    c._fetch_page = fake_page
    out = await drain(c.fetch("kw", 1000, noop))
    print(f"  douban partial-failure -> {out}")
    assert sorted(out) == ["c0", "c2"], out
    print("  douban partial-failure OK (one bad subject does not kill the round)")


async def test_douban_concurrency_is_real():
    """5 subjects x 0.3s for page 0: serial ~1.5s, concurrency 3 -> ~0.6s."""
    import app.crawlers.douban as dmod
    orig_sleep = dmod.polite_sleep
    async def no_sleep(*a, **k):
        return
    dmod.polite_sleep = no_sleep
    try:
        c = DoubanCrawler()
        c._search_subjects = lambda *a, **k: _ret(_subjects(5))
        async def fake_page(client, subject, page):
            if page >= 1:
                return []
            await asyncio.sleep(0.3)
            return ["x"]
        c._fetch_page = fake_page
        loop = asyncio.get_running_loop()
        t0 = loop.time()
        await drain(c.fetch("kw", 1000, noop))
        elapsed = loop.time() - t0
        print(f"  douban timing -> {elapsed:.2f}s (serial would be ~1.5s)")
        assert elapsed < 0.9, f"not actually concurrent: {elapsed}"
    finally:
        dmod.polite_sleep = orig_sleep
    print("  douban concurrency OK")


async def test_tieba_fallback_to_thread_content():
    c = TiebaCrawler()
    threads = [
        {"tid": "1", "title": "A", "content": "content-A", "forum": "f",
         "url": "https://tieba.baidu.com/p/1"},
        {"tid": "2", "title": "B", "content": "content-B", "forum": "f",
         "url": "https://tieba.baidu.com/p/2"},
        {"tid": "3", "title": "C", "content": "", "forum": "f",
         "url": "https://tieba.baidu.com/p/3"},
    ]
    c._search_threads = lambda *a, **k: _ret(threads)
    async def fake_replies(client, thread, target, collected):
        if thread["tid"] == "1":
            return ["floor-1a", "floor-1b"]
        if thread["tid"] == "2":
            return []            # no floors -> fall back to thread body
        raise RuntimeError("blocked")   # error -> fall back, but content empty
    c._fetch_replies = fake_replies
    out = await drain(c.fetch("kw", 1000, noop))
    print(f"  tieba fallback -> {out}")
    assert sorted(out) == ["content-B", "floor-1a", "floor-1b"], out
    print("  tieba fallback OK")


def _ret(value):
    async def inner():
        return value
    return inner()


async def main():
    for fn in (test_douban_happy, test_douban_streams_first_page_early,
               test_douban_one_subject_raises,
               test_douban_concurrency_is_real, test_tieba_fallback_to_thread_content):
        print(f"{fn.__name__}:")
        await fn()
    print("\nALL PASS")


asyncio.run(main())
