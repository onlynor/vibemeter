"""Bilibili comment crawler using the public reply API."""
from __future__ import annotations

import asyncio
from typing import AsyncIterator
from urllib.parse import quote

from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler, ProgressCallback
from app.crawlers.hot_fallback import bilibili_hot
from app.crawlers.http_utils import fetch_json, make_client, polite_sleep


class BilibiliCrawler(BaseCrawler):
    """Bilibili crawler: keyword -> video AID list -> per-video comment pages.

    Sorting: ``order=click`` ranks by view-count so big-keyword queries
    find the actual viral videos rather than recent uploads. When the
    search returns nothing, we fall back to the platform-wide popular
    list so the analysis still produces real comments.
    """

    name = "bilibili"
    SEARCH_URL = "https://api.bilibili.com/x/web-interface/search/type"
    REPLY_MAIN_URL = "https://api.bilibili.com/x/v2/reply/main"
    HOME = "https://www.bilibili.com/"

    def _extra_headers(self) -> dict[str, str]:
        return {
            "Referer": self.HOME,
            "Origin": "https://www.bilibili.com",
            "Accept": "application/json, text/plain, */*",
        }

    async def _bootstrap_cookies(self, client) -> None:
        """Visit the homepage once to obtain buvid3 and other anti-spam cookies."""
        try:
            await client.get(self.HOME, headers=self._extra_headers())
        except Exception:
            pass

    async def _search_videos(self, client, keyword: str, limit: int = 50) -> list[dict]:
        """Search videos and return them sorted by view count (popularity)."""
        videos: list[dict] = []
        for page in (1, 2, 3, 4, 5):
            payload = await fetch_json(
                client,
                self.SEARCH_URL,
                params={
                    "search_type": "video",
                    "keyword": keyword,
                    "order": "click",
                    "page": page,
                    "duration": 0,
                },
                headers=self._extra_headers(),
            )
            if not payload or payload.get("code") != 0:
                continue
            results = (payload.get("data") or {}).get("result") or []
            for item in results:
                aid = item.get("aid")
                if not aid:
                    continue
                bvid = str(item.get("bvid") or "").strip()
                title = BeautifulSoup(item.get("title") or "", "html.parser").get_text(" ", strip=True)
                subtitle = BeautifulSoup(item.get("description") or "", "html.parser").get_text(" ", strip=True)
                videos.append({
                    "aid": int(aid),
                    "bvid": bvid,
                    "title": title or f"B站视频 {aid}",
                    "subtitle": subtitle[:80],
                    "url": (
                        f"https://www.bilibili.com/video/{quote(bvid)}/"
                        if bvid else f"https://www.bilibili.com/video/av{aid}/"
                    ),
                    "embed_url": (
                        f"https://player.bilibili.com/player.html?bvid={quote(bvid)}&page=1&high_quality=1&as_wide=1"
                        if bvid else ""
                    ),
                    "display_type": "video",
                    "platform": "bilibili",
                })
                if len(videos) >= limit:
                    break
            if len(videos) >= limit:
                break
            await polite_sleep(0.2, 0.5)
        return videos[:limit]

    async def _fetch_comments_for(self, client, aid: int) -> tuple[int, list[str]]:
        """Pull hot replies for a single video.

        Returns ``(code, messages)`` so the caller can distinguish a
        rate-limit (``code == -412``) from a video that simply has no
        comments. Bilibili's ``/reply/main`` is the only public
        endpoint that still works without wbi signing, and it caps at
        ~3 hot replies per request — we just take one shot per aid
        and let the caller fan out across many videos.
        """
        payload = await fetch_json(
            client,
            self.REPLY_MAIN_URL,
            params={
                "type": 1,
                "oid": aid,
                "mode": 3,
                "next": 0,
                "ps": 30,
            },
            headers=self._extra_headers(),
        )
        if not payload:
            return -1, []
        code = int(payload.get("code") or 0)
        if code != 0:
            return code, []
        replies = (payload.get("data") or {}).get("replies") or []
        msgs = [
            (reply.get("content") or {}).get("message", "")
            for reply in replies
            if (reply.get("content") or {}).get("message")
        ]
        return 0, msgs

    async def fetch(
        self,
        keyword: str,
        target_count: int,
        progress_cb: ProgressCallback,
    ) -> AsyncIterator[list[str]]:
        collected = 0
        self.reset_source_items()
        async with make_client(referer=self.HOME) as client:
            await self._bootstrap_cookies(client)
            videos = await self._search_videos(client, keyword)
            used_fallback = False
            if not videos:
                await progress_cb(0, "B站关键词无相关视频，已切换为热门视频榜...")
                videos = await bilibili_hot(client, limit=10)
                used_fallback = True
            if not videos:
                raise RuntimeError("B站搜索与热门榜均未返回任何视频")
            for video in videos[:6]:
                self.record_source_item({
                    "platform": self.name,
                    "title": video["title"],
                    "subtitle": video["subtitle"],
                    "url": video["url"],
                    "embed_url": video["embed_url"],
                    "display_type": video["display_type"],
                })
            prefix = "热门" if used_fallback else "相关"
            await progress_cb(0, f"找到 {len(videos)} 个{prefix}视频，开始采集评论...")

            # Fan-out comment fetches: keep concurrency modest so B站
            # doesn't return ``-412`` (banned). 3 in flight gives ~5×
            # speedup vs sequential while staying well under the rate
            # limit for unauthenticated clients.
            concurrency = 3
            banned_count = 0
            for start in range(0, len(videos), concurrency):
                if collected >= target_count:
                    break
                chunk = videos[start:start + concurrency]
                results = await asyncio.gather(
                    *(self._fetch_comments_for(client, v["aid"]) for v in chunk),
                    return_exceptions=True,
                )
                batch: list[str] = []
                for r in results:
                    if isinstance(r, Exception):
                        continue
                    code, msgs = r
                    if code == -412:
                        banned_count += 1
                    batch.extend(msgs)
                if batch:
                    yield batch
                    collected += len(batch)
                    await progress_cb(collected, "")
                # Back off harder when we start seeing bans.
                await polite_sleep(0.05, 0.2)
                if banned_count >= 5 and collected == 0:
                    raise RuntimeError(
                        "B站接口连续返回 -412 风控（请稍后再试或登录后导出 Cookie）"
                    )
        if collected == 0:
            raise RuntimeError("B站候选视频均无可读评论")
