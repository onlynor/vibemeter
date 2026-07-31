"""百度网页搜索 provider

要点（都是实测出来的，改动前先确认）：

* 必须先访问一次 www.baidu.com 拿 ``BAIDUID`` 再发检索请求。直接打
  ``/s`` 只会拿到 7 个左右的容器且大多是卡片；带上 Cookie 后能拿到完整
  一页（实测 20 个容器 / 19 条自然结果）。
* 广告和自然结果的区别在跳转域名：广告是 ``www.baidu.com/baidu.php?url=``，
  自然结果是 ``www.baidu.com/link?url=``。
* 真实目标地址挂在容器的 ``mu`` 属性上，优先取它，省掉逐条解析 302 跳转
  的开销（那会让一次检索多出十几个请求）。
"""
from __future__ import annotations

from app.crawlers.http_utils import fetch_text, make_client
from app.search.base import ResultSpec, SearchProvider, SearchResult
from app.search.registry import register_provider


BAIDU_SPEC = ResultSpec(
    container="div[class*=c-container]",
    title="h3",
    link="h3 a",
    snippet=(
        "[class*=content-right]",
        ".c-abstract",
        "[class*=abstract]",
        ".c-span-last",
    ),
    real_url_attr="mu",
    placeholder_url_markers=("nourl.ubs.baidu.com",),
    ad_href_markers=("baidu.php?",),
    ad_attrs=("data-tuiguang",),
)


@register_provider
class BaiduSearchProvider(SearchProvider):
    """百度网页检索"""

    name = "baidu"
    label = "百度搜索"
    default_limit = 10

    HOME = "https://www.baidu.com/"
    SEARCH_URL = "https://www.baidu.com/s"

    async def search(self, query: str, *, limit: int) -> list[SearchResult]:
        from app.search.base import parse_results  # 局部导入避免循环引用

        async with make_client(referer=self.HOME) as client:
            # 预热拿 BAIDUID，否则结果页会被裁剪成几张卡片
            try:
                await client.get(self.HOME)
            except Exception:
                # 预热失败不致命，后面照常尝试检索
                pass
            html = await fetch_text(
                client,
                self.SEARCH_URL,
                params={
                    "wd": query,
                    # 多要一些，广告与非结果容器会在解析阶段被剔掉
                    "rn": max(limit, 10) + 10,
                    "ie": "utf-8",
                },
                headers={"Referer": self.HOME},
            )

        if not html:
            raise RuntimeError("百度检索无响应")
        if "百度安全验证" in html or "wappass.baidu.com/static/captcha" in html:
            raise RuntimeError("百度触发安全验证，请稍后再试")

        return parse_results(html, BAIDU_SPEC, self.name, limit)
