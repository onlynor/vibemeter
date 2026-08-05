"""爬虫工厂与数据源可用性探测"""
from __future__ import annotations

import asyncio
import time
from typing import Sequence

from app.config import HOTSPOTS_CACHE_SECONDS
from app.crawlers.auto import AutoCrawler
from app.crawlers.base import BaseCrawler
from app.crawlers.bilibili import BilibiliCrawler
from app.crawlers.cookies import cookie_configured, cookie_env_name
from app.crawlers.douban import DoubanCrawler
from app.crawlers.tieba import TiebaCrawler
from app.crawlers.weibo import WeiboCrawler
from app.crawlers.zhihu import ZhihuCrawler


__all__ = [
    "get_crawler",
    "source_health",
    "BaseCrawler",
    "SUPPORTED_PLATFORMS",
    "PLATFORM_LABELS",
]


_REGISTRY: dict[str, type[BaseCrawler]] = {
    "auto": AutoCrawler,
    "bilibili": BilibiliCrawler,
    "weibo": WeiboCrawler,
    "douban": DoubanCrawler,
    "zhihu": ZhihuCrawler,
    "tieba": TiebaCrawler,
}

PLATFORM_LABELS: dict[str, str] = {
    "auto": "聚合搜索",
    "bilibili": "B站",
    "weibo": "微博",
    "douban": "豆瓣",
    "zhihu": "知乎",
    "tieba": "贴吧",
}

SUPPORTED_PLATFORMS = list(_REGISTRY.keys())

# 单个数据源探测的最长等待时间（秒）
PING_TIMEOUT: float = 25.0


def get_crawler(platform: str, platforms: Sequence[str] | None = None) -> BaseCrawler:
    """返回指定平台的爬虫实例

    ``platforms`` 只对 ``auto`` 有意义：限定聚合爬虫本轮启动哪几个源。
    单平台任务传了也无害，直接忽略。
    """
    cls = _REGISTRY.get(platform)
    if cls is None:
        raise ValueError(f"Unknown platform: {platform!r}")
    if cls is AutoCrawler:
        return AutoCrawler(platforms)
    return cls()


async def _ping_one(platform: str) -> dict:
    """探测单个平台，异常与超时都折算成不可用"""
    crawler = get_crawler(platform)
    issue = crawler.cookie_issue
    if issue:
        # Cookie 本身就不合法，没必要再发请求，直接报真正的原因
        ok, message = False, issue
    else:
        try:
            ok, message = await asyncio.wait_for(crawler.ping(), timeout=PING_TIMEOUT)
        except asyncio.TimeoutError:
            ok, message = False, f"探测超时（{PING_TIMEOUT:.0f}s）"
        except Exception as exc:
            ok, message = False, f"探测失败：{exc}"
    return {
        "platform": platform,
        "label": PLATFORM_LABELS.get(platform, platform),
        "ok": ok,
        "message": message,
        "cookie_env": cookie_env_name(platform),
        "cookie_required": crawler.cookie_required,
        "cookie_configured": cookie_configured(platform),
    }


async def _probe_all() -> list[dict]:
    """并发探测所有单一数据源，并据此合成聚合搜索的可用性"""
    platforms = [p for p in SUPPORTED_PLATFORMS if p != "auto"]
    results = await asyncio.gather(*(_ping_one(p) for p in platforms))

    usable = [item["label"] for item in results if item["ok"]]
    auto = {
        "platform": "auto",
        "label": PLATFORM_LABELS["auto"],
        "ok": bool(usable),
        "message": (
            f"当前可用：{'、'.join(usable)}"
            if usable else "所有公开数据源当前均不可用"
        ),
        "cookie_env": "",
        "cookie_required": False,
        "cookie_configured": False,
    }
    return [auto, *results]


class _SourceHealthCache:
    """缓存探测结果，避免连点按钮时反复对各平台打真实请求

    与 ``hotspots.service.HotspotService`` 同款做法：单飞锁 + 时间戳。
    """

    def __init__(self, ttl: float = HOTSPOTS_CACHE_SECONDS) -> None:
        self._lock = asyncio.Lock()
        self._ttl = ttl
        self._cached_at = 0.0
        self._cache: list[dict] = []

    def _fresh(self, now: float) -> bool:
        return bool(self._cache) and now - self._cached_at < self._ttl

    async def get(self) -> list[dict]:
        now = time.time()
        if self._fresh(now):
            return self._cache
        async with self._lock:
            now = time.time()
            if self._fresh(now):
                return self._cache
            self._cache = await _probe_all()
            self._cached_at = now
            return self._cache


_health_cache = _SourceHealthCache()


async def source_health() -> list[dict]:
    """返回各数据源可用性（带 5 分钟缓存）"""
    return await _health_cache.get()
