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
from app.search.base import (
    ResultSpec,
    SearchProvider,
    SearchResult,
    clean_text,
    parse_results,
    strip_snippet_noise,
)
from app.search.baidu import BAIDU_SPEC, BaiduSearchProvider
from app.search.bing import BING_SPEC, BingSearchProvider, _resolve_redirect


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
    # 汉字之间的空白全部压掉：那些空格是标签边界的产物，不是原文内容
    assert first.title == "百科条目", repr(first.title)
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


# --- 夹具：按实测的必应结果页结构裁剪 ---------------------------------

BING_HTML = """
<html><body><ol id="b_results">
  <li class="b_ad"><div><h2><a href="https://cn.bing.com/aclick?ld=X">推广结果</a></h2></div></li>
  <li class="b_algo">
    <h2><a href="https://www.gov.cn/a.htm"><strong>小米汽车</strong>销量再创新高</a></h2>
    <div class="b_caption"><p>2 小时之前 · <strong>小米汽车</strong>本月交付量公布。</p></div>
  </li>
  <li class="b_algo">
    <h2><a href="https://www.bing.com/ck/a?!&amp;&amp;p=1&amp;u=a1aHR0cHM6Ly9leGFtcGxlLmNvbS9uZXdz">跳转包装的结果</a></h2>
    <div class="b_caption"><p>2026年1月2日 · 正文摘要。</p></div>
  </li>
  <li class="b_algo">
    <h2><a href="https://cn.bing.com/aclick?u=Y">漏进 b_algo 的广告</a></h2>
  </li>
</ol></body></html>
"""


def test_bing_parser():
    results = parse_results(BING_HTML, BING_SPEC, "bing", limit=10)
    titles = [r.title for r in results]
    print(f"  parsed {len(results)}: {titles}")

    assert "推广结果" not in titles, "b_ad 容器不该被选中"
    assert "漏进 b_algo 的广告" not in titles, "aclick 广告未被过滤"
    assert len(results) == 2, titles

    # <strong> 包住的查询词不该把标题切碎
    assert results[0].title == "小米汽车销量再创新高", repr(results[0].title)
    # 摘要开头的相对时间被剥掉
    assert results[0].snippet == "小米汽车本月交付量公布。", repr(results[0].snippet)
    assert results[1].snippet == "正文摘要。", repr(results[1].snippet)
    assert [r.rank for r in results] == [1, 2]
    print("  bing parser OK")


def test_bing_redirect_resolution():
    wrapped = "https://www.bing.com/ck/a?!&&p=1&u=a1aHR0cHM6Ly9leGFtcGxlLmNvbS9uZXdz"
    assert _resolve_redirect(wrapped) == "https://example.com/news"
    # 直链原样放行
    direct = "https://www.gov.cn/a.htm"
    assert _resolve_redirect(direct) == direct
    # 解不开时退回原链接，而不是丢掉这条结果
    assert _resolve_redirect("https://www.bing.com/ck/a?u=a1@@@") .startswith("https://www.bing.com/ck/a")
    assert _resolve_redirect("https://www.bing.com/ck/a?x=1") == "https://www.bing.com/ck/a?x=1"
    print("  bing redirect OK")


def test_text_normalisation():
    # 汉字之间的空白压掉，字母之间的保留
    assert clean_text(" 小米汽车 （ 小米 ） ") == "小米汽车（小米）"
    assert clean_text("Xiaomi SU7 Ultra") == "Xiaomi SU7 Ultra"
    assert clean_text("AI 技术") == "AI 技术"
    # 摘要噪音
    assert strip_snippet_noise("2026年1月2日 · 正文") == "正文"
    assert strip_snippet_noise("15 小时之前 · 正文") == "正文"
    assert strip_snippet_noise("正文 百度快照") == "正文"
    assert strip_snippet_noise("2026年的政策变化") == "2026年的政策变化"
    print("  text normalisation OK")


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
    assert ok.title == "标题" and ok.snippet == "摘要多行"
    assert ok.to_dict() == {
        "title": "标题", "url": "https://a.com", "snippet": "摘要多行",
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
    # bing.py 只是往包里多放了一个文件，注册表与聚合层都没为它改过一行
    assert "bing" in names
    assert isinstance(registry.get_provider("baidu"), BaiduSearchProvider)
    assert isinstance(registry.get_provider("bing"), BingSearchProvider)
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


def _make_fixed(name, items):
    """桩 provider，直接给定 (title, url) 列表"""
    class Stub(SearchProvider):
        async def search(self, query, *, limit):
            return [
                SearchResult(title=t, url=u, snippet="s", source=name, rank=i + 1)
                for i, (t, u) in enumerate(items[:limit])
            ]
    Stub.name = name
    Stub.label = name.upper()
    registry._REGISTRY[name] = Stub
    return name


async def test_cross_provider_dedup():
    """两个引擎命中同一篇稿件时只保留一条"""
    names = [
        _make_fixed("dd_a", [
            ("小米汽车月销量创新高", "https://news.example.com/a?id=1"),
            ("独家：供应链解读", "https://only-a.example.com/x"),
        ]),
        _make_fixed("dd_b", [
            # 同一 URL，只差 www 前缀 / 协议 / 结尾斜杠
            ("标题写法略有不同", "http://www.news.example.com/a/?id=1"),
            # 同一篇稿件被转载，链接不同但标题一致
            ("小米汽车月销量创新高", "https://mirror.example.com/repost"),
            ("只有 B 有的结果", "https://only-b.example.com/y"),
        ]),
    ]
    try:
        results, _ = await registry.search_all("kw", limit=10, providers=names)
        urls = [r.url for r in results]
        print(f"  merged {len(results)}: {urls}")
        assert len(results) == 3, urls
        assert "https://only-a.example.com/x" in urls
        assert "https://only-b.example.com/y" in urls
        assert "https://mirror.example.com/repost" not in urls, "标题转载未去重"
    finally:
        for n in names:
            registry._REGISTRY.pop(n, None)
    print("  cross-provider dedup OK")


async def test_short_titles_not_deduped():
    """短标题太容易撞车，不该因为一样就丢结果"""
    names = [
        _make_fixed("st_a", [("官网", "https://a.example.com")]),
        _make_fixed("st_b", [("官网", "https://b.example.com")]),
    ]
    try:
        results, _ = await registry.search_all("kw", limit=5, providers=names)
        print(f"  短标题结果数: {len(results)}")
        assert len(results) == 2, [r.url for r in results]
    finally:
        for n in names:
            registry._REGISTRY.pop(n, None)
    print("  short-title OK")


async def test_total_limit_caps_merged_output():
    names = [_make("tl_a", 5), _make("tl_b", 5)]
    try:
        full, _ = await registry.search_all("kw", limit=5, providers=names)
        capped, _ = await registry.search_all("kw", limit=5, providers=names, total_limit=3)
        print(f"  full={len(full)} capped={len(capped)}")
        assert len(full) == 10 and len(capped) == 3
        # 截断发生在轮转之后，前三条仍然跨引擎交替
        assert [r.source for r in capped] == ["tl_a", "tl_b", "tl_a"], capped
    finally:
        for n in names:
            registry._REGISTRY.pop(n, None)
    print("  total_limit OK")


async def test_empty_provider_list_means_disabled():
    """providers=[] 表示用户关掉了检索增强，与 None（全部）语义不同"""
    results, status = await registry.search_all("关键词", limit=5, providers=[])
    assert results == [] and status == []
    print("  disabled-by-empty-list OK")


async def test_empty_query_short_circuits():
    results, status = await registry.search_all("   ", limit=5)
    assert results == [] and status == []
    print("  empty query OK")


async def main():
    for fn in (test_baidu_parser, test_bing_parser, test_bing_redirect_resolution,
               test_text_normalisation, test_parser_limit_and_empty,
               test_search_result_model, test_provider_registration):
        print(f"{fn.__name__}:")
        fn()
    for fn in (test_aggregation_isolates_failures,
               test_aggregation_timeout_does_not_block,
               test_aggregation_interleaves_sources,
               test_cross_provider_dedup,
               test_short_titles_not_deduped,
               test_total_limit_caps_merged_output,
               test_empty_provider_list_means_disabled,
               test_empty_query_short_circuits):
        print(f"{fn.__name__}:")
        await fn()
    print("\nALL PASS")


asyncio.run(main())
