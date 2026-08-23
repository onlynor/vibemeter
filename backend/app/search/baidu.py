"""百度网页搜索 provider

要点（都是实测出来的，改动前先确认）：

* 必须先访问一次 www.baidu.com 拿 ``BAIDUID`` 再发检索请求。直接打
  ``/s`` 只会拿到 7 个左右的容器且大多是卡片；带上 Cookie 后能拿到完整
  一页（实测 20 个容器 / 19 条自然结果）。
  这个预热是**串行**的一次往返，所以 Cookie 在进程内按 TTL 复用：
  只有第一次检索（以及 TTL 过期后）才真的去打首页，之后直接带上缓存值。
  预热还有独立的短时限——它只是为了拿一个 Cookie，卡在这一步等于整次
  检索白白耗掉 provider 的时间预算。
* 广告和自然结果的区别在跳转域名：广告是 ``www.baidu.com/baidu.php?url=``，
  自然结果是 ``www.baidu.com/link?url=``。
* 真实目标地址挂在容器的 ``mu`` 属性上，优先取它，省掉逐条解析 302 跳转
  的开销（那会让一次检索多出十几个请求）。
"""
from __future__ import annotations

import asyncio
import logging
import time

import httpx

from app.config import SEARCH_COOKIE_TTL, SEARCH_OVERFETCH, SEARCH_WARMUP_TIMEOUT
from app.crawlers.http_utils import fetch_text, make_client
from app.search.base import ResultSpec, SearchProvider, SearchResult
from app.search.registry import register_provider


logger = logging.getLogger(__name__)

# 进程内的 BAIDUID 缓存。锁把并发的冷启动收敛成一次预热请求，
# 否则同时发起的几个任务会各打一次首页，反而更慢也更像机器人。
_cookie_cache: dict[str, str] = {}
_cookie_expires_at: float = 0.0
_cookie_lock = asyncio.Lock()


async def _ensure_cookies(client: httpx.AsyncClient) -> None:
    """给客户端装上 BAIDUID：命中缓存就省掉一次串行往返

    预热失败不致命——照常检索，最多是结果被裁剪成几张卡片，
    由上层的"未解析出结果"来体现。
    """
    global _cookie_cache, _cookie_expires_at

    now = time.monotonic()
    async with _cookie_lock:
        if _cookie_cache and now < _cookie_expires_at:
            client.cookies.update(_cookie_cache)
            return
        try:
            await asyncio.wait_for(
                client.get(BaiduSearchProvider.HOME), timeout=SEARCH_WARMUP_TIMEOUT
            )
        except asyncio.CancelledError:
            raise
        except (asyncio.TimeoutError, httpx.HTTPError) as exc:
            logger.debug("百度预热失败，继续裸检索：%s", exc)
            return
        jar = dict(client.cookies)
        if jar:
            _cookie_cache = jar
            _cookie_expires_at = time.monotonic() + SEARCH_COOKIE_TTL


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
            # 预热拿 BAIDUID（缓存命中时不发请求），否则结果页会被裁成几张卡片
            await _ensure_cookies(client)
            html = await fetch_text(
                client,
                self.SEARCH_URL,
                params={
                    "wd": query,
                    # 多要一些，广告与非结果容器会在解析阶段被剔掉
                    "rn": max(limit, self.default_limit) + SEARCH_OVERFETCH,
                    "ie": "utf-8",
                },
                headers={"Referer": self.HOME},
            )

        if not html:
            raise RuntimeError("百度检索无响应")
        if "百度安全验证" in html or "wappass.baidu.com/static/captcha" in html:
            raise RuntimeError("百度触发安全验证，请稍后再试")

        return parse_results(html, BAIDU_SPEC, self.name, limit)
