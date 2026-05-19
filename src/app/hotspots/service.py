"""Fetch and cache homepage hotspots from remote providers."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from urllib.parse import quote

import httpx

from app.config import HOTSPOTS_CACHE_SECONDS


class HotspotService:
    """Provides a 5-minute cached hotspot feed for the homepage."""

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
            return_exceptions=True,
        )
        merged: list[dict[str, Any]] = []
        for payload in providers:
            if isinstance(payload, Exception):
                continue
            merged.extend(payload)
        if merged:
            return merged[:20]
        return []

    async def _fetch_baidu(self) -> list[dict[str, Any]]:
        url = "https://top.baidu.com/board?tab=realtime"
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
        text = response.text
        marker = "window.__INITIAL_DATA__="
        start = text.find(marker)
        if start < 0:
            return []
        start += len(marker)
        end = text.find(";</script>", start)
        if end < 0:
            return []
        payload = json.loads(text[start:end])
        cards = (((payload.get("data") or {}).get("cards")) or [])
        for card in cards:
            if card.get("component") == "hotSearch":
                content = card.get("content") or []
                return [
                    {
                        "source": "baidu",
                        "title": item.get("word") or "",
                        "subtitle": item.get("desc") or "",
                        "rank": idx + 1,
                        "score": item.get("hotScore") or item.get("hotChange") or "",
                        "url": self._build_search_url("baidu", item.get("word") or ""),
                        "is_mock": False,
                    }
                    for idx, item in enumerate(content[:10])
                    if item.get("word")
                ]
        return []

    async def _fetch_weibo(self) -> list[dict[str, Any]]:
        url = "https://weibo.com/ajax/side/hotSearch"
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
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
            for idx, item in enumerate(realtime[:10])
            if item.get("word")
        ]

    @staticmethod
    def _build_search_url(source: str, title: str) -> str:
        query = quote(title.strip())
        if not query:
            return ""
        if source == "weibo":
            return f"https://s.weibo.com/weibo?q={query}"
        return f"https://www.baidu.com/s?wd={query}"
hotspot_service = HotspotService()
