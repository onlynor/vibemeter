"""Crawler factory."""
from __future__ import annotations

from app.crawlers.auto import AutoCrawler
from app.crawlers.base import BaseCrawler
from app.crawlers.bilibili import BilibiliCrawler
from app.crawlers.weibo import WeiboCrawler


__all__ = [
    "get_crawler",
    "BaseCrawler",
    "SUPPORTED_PLATFORMS",
    "PLATFORM_LABELS",
]


_REGISTRY: dict[str, type[BaseCrawler]] = {
    "auto": AutoCrawler,
    "bilibili": BilibiliCrawler,
    "weibo": WeiboCrawler,
}

PLATFORM_LABELS: dict[str, str] = {
    "auto": "聚合搜索",
    "bilibili": "B站",
    "weibo": "微博",
}

SUPPORTED_PLATFORMS = list(_REGISTRY.keys())


def get_crawler(platform: str) -> BaseCrawler:
    """Return a fresh crawler instance for the requested platform."""
    cls = _REGISTRY.get(platform)
    if cls is None:
        raise ValueError(f"Unknown platform: {platform!r}")
    return cls()
