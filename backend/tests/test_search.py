"""搜索检索层单元测试

不依赖网络：解析用内联 HTML 夹具，聚合用桩 provider。
运行： backend/.venv/bin/python tests/test_search.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.search import registry
from app.search.base import ResultSpec, SearchProvider, SearchResult, parse_results
from app.search.baidu import BAIDU_SPEC, BaiduSearchProvider


# --- 夹具：按实测的百度结果页结构裁剪 ---------------------------------

BAIDU_HTML = """
<html><body>
  <div class="result c-container" mu="https://www.baidu.com/baidu.php?url=AD">
    <h3><a href="https://www.baidu.com/baidu.php?url=AD1">广告标题</a></h3>
    <div class="c-abstract">这是一条广告</div>
  </div>
  <div class="result c-container" data-tuiguang="1" mu="https://ad.example.com">
    <h3><a href="http://www.baidu.com/link?url=X">属性标记的广告</a></h3>
  </div>
  <div class="result c-container" mu="https://baike.baidu.com/item/test">
    <h3><a href="http://www.baidu.com/link?url=AAA">  百科  条目 </a></h3>
    <div class="c-abstract">简介：这是摘要正文。</div>
  </div>
  <div class="result c-container" mu="http://nourl.ubs.baidu.com/51270">
    <h3><a href="http://www.baidu.com/link?url=BBB">占位地址的卡片</a></h3>
    <div class="c-abstract">卡片摘要</div>
  </div>
  <div class="result c-container" mu="https://baike.baidu.com/item/test">
    <h3><a href="http://www.baidu.com/link?url=CCC">重复 URL 的结果</a></h3>
  </div>
  <div class="result c-container">
    <h3><a href="https://www.example.com/page">无 mu 属性</a></h3>
    <div class="content-right">优先级更高的摘要</div>
  </div>
  <div class="result c-container"><span>没有标题链接的容器</span></div>
</body></html>
"""


def test_baidu_parser():
    results = parse_results(BAIDU_HTML, BAIDU_SPEC, "baidu", limit=10)
    titles = [r.title for r in results]
    print(f"  parsed {len(results)}: {titles}")

    assert "广告标题" not in titles, "href 广告未被过滤"
    assert "属性标记的广告" not in titles, "data-tuiguang 广告未被过滤"
    assert len(results) == 3, titles

    first = results[0]
    assert first.title == "百科 条目", repr(first.title)   # 空白被压平
    assert first.url == "https://baike.baidu.com/item/test", first.url  # 用 mu 而非跳转链接
    assert first.snippet == "简介：这是摘要正文。", first.snippet
    assert first.source == "baidu"

    # 占位 mu 退回 href
    placeholder = results[1]
    assert "nourl" not in placeholder.url, placeholder.url
    assert placeholder.url.startswith("http://www.baidu.com/link?url=BBB"), placeholder.url

    # 重复 URL 被去掉；content-right 优先于 c-abstract
    assert results[2].snippet == "优先级更高的摘要", results[2].snippet

    # rank 连续且从 1 起，广告不占名次
    assert [r.rank for r in results] == [1, 2, 3], [r.rank for r in results]
    print("  baidu parser OK")


def test_parser_limit_and_empty():
    assert parse_results(BAIDU_HTML, BAIDU_SPEC, "baidu", limit=1) != []
    assert len(parse_results(BAIDU_HTML, BAIDU_SPEC, "baidu", limit=1)) == 1
    assert parse_results("", BAIDU_SPEC, "baidu", limit=5) == []
    assert parse_results("<html></html>", BAIDU_SPEC, "baidu", limit=5) == []
    print("  parser limit/empty OK")


def test_search_result_model():
    ok = SearchResult.build(title=" 标题 ", url="https://a.com", snippet=" 摘要\n多行 ",
                            source="baidu", rank=1)
    assert ok is not None
    assert ok.title == "标题" and ok.snippet == "摘要 多行"
    assert ok.to_dict() == {
        "title": "标题", "url": "https://a.com", "snippet": "摘要 多行",
        "source": "baidu", "rank": 1,
    }
    # 非法输入一律被拒
    assert SearchResult.build(title="", url="https://a.com", snippet="", source="b", rank=1) is None
    assert SearchResult.build(title="t", url="", snippet="", source="b", rank=1) is None
    assert SearchResult.build(title="t", url="ftp://x", snippet="", source="b", rank=1) is None
    assert SearchResult.build(title="t", url="javascript:alert(1)", snippet="", source="b", rank=1) is None
    print("  unified model OK")


def test_provider_registration():
    names = registry.available_providers()
    print(f"  registered providers: {names}")
    assert "baidu" in names
    assert isinstance(registry.get_provider("baidu"), BaiduSearchProvider)
    try:
        registry.get_provider("nope")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown provider should raise")

    # 注册新 provider 无需改动既有代码
    @registry.register_provider
    class _Dummy(SearchProvider):
        name = "dummy_reg"
        label = "Dummy"
        async def search(self, query, *, limit):
            return []

    assert "dummy_reg" in registry.available_providers()
    # 重名必须报错，避免静默覆盖
    try:
        @registry.register_provider
        class _Clash(SearchProvider):
            name = "dummy_reg"
            label = "Clash"
            async def search(self, query, *, limit):
                return []
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate name should raise")
    finally:
        registry._REGISTRY.pop("dummy_reg", None)
    print("  registration OK")


# --- 聚合：桩 provider ------------------------------------------------

def _make(name, count=0, *, delay=0.0, boom=None):
    # search 必须定义在类体内：__abstractmethods__ 在建类时就算好了，
    # 事后赋值不会解除抽象状态，实例化仍会 TypeError。
    class Stub(SearchProvider):
        async def search(self, query, *, limit):
            if delay:
                await asyncio.sleep(delay)
            if boom:
                raise RuntimeError(boom)
            return [
                SearchResult(title=f"{name}-{i}", url=f"https://{name}.com/{i}",
                             snippet="s", source=name, rank=i + 1)
                for i in range(count)
            ]
    Stub.name = name
    Stub.label = name.upper()
    registry._REGISTRY[name] = Stub
    return name


async def test_aggregation_isolates_failures():
    names = [
        _make("stub_ok", 3),
        _make("stub_boom", boom="provider exploded"),
        _make("stub_empty", 0),
    ]
    try:
        results, status = await registry.search_all("kw", limit=5, providers=names)
        by = {s["provider"]: s for s in status}
        print(f"  results={len(results)} status={[(s['provider'], s['ok']) for s in status]}")
        assert len(results) == 3, results
        assert by["stub_ok"]["ok"] and by["stub_ok"]["count"] == 3
        assert by["stub_boom"]["ok"] is False
        assert "provider exploded" in by["stub_boom"]["message"]
        assert by["stub_empty"]["ok"] is True and by["stub_empty"]["count"] == 0
    finally:
        for n in names:
            registry._REGISTRY.pop(n, None)
    print("  failure isolation OK")


async def test_aggregation_timeout_does_not_block():
    orig = registry.PROVIDER_TIMEOUT
    registry.PROVIDER_TIMEOUT = 0.3
    names = [_make("stub_fast", 2), _make("stub_slow", 2, delay=5.0)]
    try:
        loop = asyncio.get_running_loop()
        t0 = loop.time()
        results, status = await registry.search_all("kw", limit=5, providers=names)
        elapsed = loop.time() - t0
        by = {s["provider"]: s for s in status}
        print(f"  elapsed={elapsed:.2f}s results={len(results)}")
        assert elapsed < 1.5, f"slow provider blocked the pipeline: {elapsed}"
        assert len(results) == 2, results
        assert by["stub_slow"]["ok"] is False and "超时" in by["stub_slow"]["message"]
    finally:
        registry.PROVIDER_TIMEOUT = orig
        for n in names:
            registry._REGISTRY.pop(n, None)
    print("  timeout isolation OK")


async def test_aggregation_interleaves_sources():
    names = [_make("stub_a", 3), _make("stub_b", 3)]
    try:
        results, _ = await registry.search_all("kw", limit=5, providers=names)
        sources = [r.source for r in results]
        print(f"  merge order: {sources}")
        assert sources[:4] == ["stub_a", "stub_b", "stub_a", "stub_b"], sources
    finally:
        for n in names:
            registry._REGISTRY.pop(n, None)
    print("  interleave OK")


async def test_empty_query_short_circuits():
    results, status = await registry.search_all("   ", limit=5)
    assert results == [] and status == []
    print("  empty query OK")


async def main():
    for fn in (test_baidu_parser, test_parser_limit_and_empty,
               test_search_result_model, test_provider_registration):
        print(f"{fn.__name__}:")
        fn()
    for fn in (test_aggregation_isolates_failures,
               test_aggregation_timeout_does_not_block,
               test_aggregation_interleaves_sources,
               test_empty_query_short_circuits):
        print(f"{fn.__name__}:")
        await fn()
    print("\nALL PASS")


asyncio.run(main())
