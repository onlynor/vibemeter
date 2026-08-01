"""必应（cn.bing.com）网页搜索 provider

存在的意义不只是"多一个源"：百度对同一 IP 的高频检索会弹安全验证，
一旦触发，检索增强就整段消失。必应的风控宽松得多，两者并联后单边被限流
时仍有背景资料可用——这正是聚合层做失败隔离想换来的效果。

要点（实测）：

* 结果容器是 ``li.b_algo``，广告在 ``li.b_ad``/``li.b_adTop`` 里，选择器本身
  就把广告排除了；``ad_href_markers`` 只是对漏网的 ``/aclick?`` 兜底。
* 多数结果的 ``h2 a[href]`` 就是真实地址，不需要像百度那样读容器属性。
  少数会包成 ``bing.com/ck/a?...&u=a1<base64url>``，这里就地解开，
  免得把一串跳转链接塞给模型和用户。
* ``ensearch=0`` 保证走中文界面；不带这个参数在部分出口 IP 上会返回英文页，
  摘要语言和评论语料对不上，LLM 读起来是割裂的。
"""
from __future__ import annotations

import base64
import binascii
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

from app.crawlers.http_utils import fetch_text, make_client
from app.search.base import ResultSpec, SearchProvider, SearchResult
from app.search.registry import register_provider


BING_SPEC = ResultSpec(
    container="li.b_algo",
    title="h2",
    link="h2 a",
    snippet=(
        ".b_caption p",
        "p.b_algoSlug",
        ".b_lineclamp2",
        ".b_lineclamp3",
        ".b_caption",
    ),
    ad_href_markers=("/aclick?", "/aclk?"),
)


def _resolve_redirect(url: str) -> str:
    """还原 ``bing.com/ck/a?...&u=a1<base64url>`` 里的真实地址

    解不开就原样返回：跳转链接虽然难看，但仍然可用，为此丢掉一条结果不值得。
    """
    if "bing.com/ck/a" not in url:
        return url
    raw = parse_qs(urlsplit(url).query).get("u", [""])[0]
    if not raw.startswith("a1"):
        return url
    payload = raw[2:]
    # base64url 且不带 padding，补齐后再解
    payload += "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload).decode("utf-8", "ignore")
    except (binascii.Error, ValueError):
        return url
    return decoded if decoded.startswith(("http://", "https://")) else url


@register_provider
class BingSearchProvider(SearchProvider):
    """必应网页检索"""

    name = "bing"
    label = "必应搜索"
    default_limit = 10

    HOME = "https://cn.bing.com/"
    SEARCH_URL = "https://cn.bing.com/search"

    async def search(self, query: str, *, limit: int) -> list[SearchResult]:
        from app.search.base import parse_results  # 局部导入避免循环引用

        async with make_client(referer=self.HOME) as client:
            try:
                # 预热拿 _EDGE_S / SRCHD 等 Cookie，冷启动时首页结果会偏少
                await client.get(self.HOME)
            except Exception:
                pass
            html = await fetch_text(
                client,
                self.SEARCH_URL,
                params={
                    "q": query,
                    "count": max(limit, 10) + 10,
                    "ensearch": 0,
                },
                headers={"Referer": self.HOME},
            )

        if not html:
            raise RuntimeError("必应检索无响应")
        if "b_captcha" in html or "请完成以下验证" in html:
            raise RuntimeError("必应触发人机验证，请稍后再试")

        results = parse_results(html, BING_SPEC, self.name, limit)
        return [replace(r, url=_resolve_redirect(r.url)) for r in results]
