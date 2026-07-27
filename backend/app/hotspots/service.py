"""从远程数据源获取并缓存首页热搜"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from urllib.parse import quote

import httpx

from app.config import HOTSPOTS_CACHE_SECONDS


# 每个来源最多取多少条，以及合并后的总条数上限
PER_SOURCE_LIMIT: int = 10
MAX_HOTSPOTS: int = 40

# 各来源共用的浏览器 UA
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


class HotspotService:
    """提供 5 分钟缓存的首页热搜数据"""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._cached_at = 0.0
        self._cache: list[dict[str, Any]] = []

    async def get_hotspots(self) -> list[dict[str, Any]]:
        now = time.time()
        if self._cache and now - self._cached_at < HOTSPOTS_CACHE_SECONDS:
            return self._cache
        async with self._lock:
            now = time.time()
            if self._cache and now - self._cached_at < HOTSPOTS_CACHE_SECONDS:
                return self._cache
            items = await self._fetch_all()
            self._cache = items
            self._cached_at = now
            return items

    async def _fetch_all(self) -> list[dict[str, Any]]:
        providers = await asyncio.gather(
            self._fetch_baidu(),
            self._fetch_weibo(),
            self._fetch_bilibili(),
            self._fetch_zhihu(),
            return_exceptions=True,
        )
        merged: list[dict[str, Any]] = []
        for payload in providers:
            if isinstance(payload, Exception):
                continue
            merged.extend(payload)
        if merged:
            return merged[:MAX_HOTSPOTS]
        return []

    async def _fetch_baidu(self) -> list[dict[str, Any]]:
        """百度实时热搜

        页面数据以前挂在 ``window.__INITIAL_DATA__``、卡片名叫 hotSearch，
        现已改成 ``<!--s-data:...-->`` 注释 + hotList 卡片，这里按新结构解析。
        """
        url = "https://top.baidu.com/board?tab=realtime"
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": _UA})
            response.raise_for_status()
        payload = _extract_baidu_payload(response.text)
        if not payload:
            return []
        cards = (((payload.get("data") or {}).get("cards")) or [])
        for card in cards:
            if card.get("component") not in ("hotList", "hotSearch"):
                continue
            content = card.get("content") or []
            return [
                {
                    "source": "baidu",
                    "title": item.get("word") or "",
                    "subtitle": item.get("desc") or "",
                    "rank": idx + 1,
                    "score": item.get("hotScore") or item.get("hotChange") or "",
                    "url": item.get("url") or self._build_search_url("baidu", item.get("word") or ""),
                    "is_mock": False,
                }
                for idx, item in enumerate(content[:PER_SOURCE_LIMIT])
                if item.get("word")
            ]
        return []

    async def _fetch_weibo(self) -> list[dict[str, Any]]:
        """微博实时热搜（该接口现在强制校验 Referer，缺失会 403）"""
        url = "https://weibo.com/ajax/side/hotSearch"
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={
                    "User-Agent": _UA,
                    "Referer": "https://weibo.com/",
                    "x-requested-with": "XMLHttpRequest",
                },
            )
            response.raise_for_status()
            payload = response.json()
        realtime = ((payload.get("data") or {}).get("realtime")) or []
        return [
            {
                "source": "weibo",
                "title": item.get("word") or "",
                "subtitle": item.get("note") or "",
                "rank": idx + 1,
                "score": item.get("num") or item.get("raw_hot") or "",
                "url": self._build_search_url("weibo", item.get("word") or ""),
                "is_mock": False,
            }
            for idx, item in enumerate(realtime[:PER_SOURCE_LIMIT])
            if item.get("word")
        ]

    async def _fetch_bilibili(self) -> list[dict[str, Any]]:
        """B站热搜词（匿名可读，无需签名）"""
        url = "https://api.bilibili.com/x/web-interface/wbi/search/square"
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            response = await client.get(
                url,
                params={"limit": PER_SOURCE_LIMIT},
                headers={"User-Agent": _UA, "Referer": "https://www.bilibili.com/"},
            )
            response.raise_for_status()
            payload = response.json()
        if payload.get("code") != 0:
            return []
        trending = ((payload.get("data") or {}).get("trending")) or {}
        items = trending.get("list") or []
        return [
            {
                "source": "bilibili",
                "title": item.get("show_name") or item.get("keyword") or "",
                "subtitle": "",
                "rank": idx + 1,
                "score": "",
                "url": self._build_search_url(
                    "bilibili", item.get("keyword") or item.get("show_name") or ""
                ),
                "is_mock": False,
            }
            for idx, item in enumerate(items[:PER_SOURCE_LIMIT])
            if item.get("show_name") or item.get("keyword")
        ]

    async def _fetch_zhihu(self) -> list[dict[str, Any]]:
        """知乎热榜（api.zhihu.com 匿名可读，网页端 v3 接口则需登录）"""
        url = "https://api.zhihu.com/topstory/hot-lists/total"
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            response = await client.get(
                url,
                params={"limit": PER_SOURCE_LIMIT},
                headers={"User-Agent": _UA, "x-api-version": "3.0.91"},
            )
            response.raise_for_status()
            payload = response.json()
        items: list[dict[str, Any]] = []
        for idx, entry in enumerate((payload.get("data") or [])[:PER_SOURCE_LIMIT]):
            target = entry.get("target") or {}
            title = ((target.get("title_area") or {}).get("text") or "").strip()
            if not title:
                continue
            link = (target.get("link") or {}).get("url") or ""
            items.append({
                "source": "zhihu",
                "title": title,
                "subtitle": ((target.get("excerpt_area") or {}).get("text") or "").strip(),
                "rank": idx + 1,
                "score": ((target.get("metrics_area") or {}).get("text") or "").strip(),
                # 热榜条目本身就是问题页，直接给来源链接而不是搜索页
                "url": link or self._build_search_url("zhihu", title),
                "is_mock": False,
            })
        return items

    @staticmethod
    def _build_search_url(source: str, title: str) -> str:
        query = quote(title.strip())
        if not query:
            return ""
        if source == "weibo":
            return f"https://s.weibo.com/weibo?q={query}"
        if source == "bilibili":
            return f"https://search.bilibili.com/all?keyword={query}"
        if source == "zhihu":
            return f"https://www.zhihu.com/search?type=content&q={query}"
        return f"https://www.baidu.com/s?wd={query}"


hotspot_service = HotspotService()


def _extract_baidu_payload(html: str) -> dict[str, Any] | None:
    """从百度热搜页里取出内嵌的 JSON 数据块"""
    marker = "<!--s-data:"
    start = html.find(marker)
    if start < 0:
        return None
    start += len(marker)
    end = html.find("-->", start)
    if end < 0:
        return None
    try:
        return json.loads(html[start:end])
    except ValueError:
        return None
