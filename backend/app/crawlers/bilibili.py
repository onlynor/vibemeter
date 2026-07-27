"""B站评论爬虫，使用公开回复 API"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator
from urllib.parse import quote

from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler, PingResult, ProgressCallback
from app.crawlers.hot_fallback import bilibili_hot
from app.crawlers.http_utils import fetch_json, make_client, polite_sleep


class BilibiliCrawler(BaseCrawler):
    """B站爬虫：关键词搜索视频，然后逐个采集评论"""

    name = "bilibili"
    label = "B站"
    SEARCH_URL = "https://api.bilibili.com/x/web-interface/search/type"
    REPLY_MAIN_URL = "https://api.bilibili.com/x/v2/reply/main"
    HOME = "https://www.bilibili.com/"

    def _extra_headers(self) -> dict[str, str]:
        h = {
            "Referer": self.HOME,
            "Origin": "https://www.bilibili.com",
            "Accept": "application/json, text/plain, */*",
        }
        # 可选：用户在 .env 里设置 BILIBILI_COOKIE 以突破 -412 风控
        if self.cookie:
            h["Cookie"] = self.cookie
        return h

    async def _bootstrap_cookies(self, client) -> None:
        """访问首页获取反垃圾 Cookie"""
        try:
            await client.get(self.HOME, headers=self._extra_headers())
        except Exception:
            pass

    async def _search_videos(self, client, keyword: str, limit: int = 50) -> list[dict]:
        """搜索视频并按播放量排序返回"""
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
        """拉取单个视频的热门回复，返回 (状态码, 评论列表)"""
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

            # 并发抓取评论，保持适度并发避免触发风控
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
                # 遇到风控时加大退避力度
                await polite_sleep(0.05, 0.2)
                if banned_count >= 5 and collected == 0:
                    raise RuntimeError(
                        "B站接口连续返回 -412 风控（请稍后再试或登录后导出 Cookie）"
                    )
        if collected == 0:
            raise RuntimeError("B站候选视频均无可读评论")

    async def ping(self) -> PingResult:
        """直接探评论接口本身，因为 -412 只会在这个接口上暴露"""
        async with make_client(referer=self.HOME) as client:
            await self._bootstrap_cookies(client)
            videos = await bilibili_hot(client, limit=1)
            if not videos:
                return False, "B站热门视频接口无返回"
            code, msgs = await self._fetch_comments_for(client, videos[0]["aid"])
        if code == -412:
            return False, (
                "B站评论接口返回 -412 风控"
                + ("（当前 Cookie 也被拦）" if self.has_cookie else "，可配置 BILIBILI_COOKIE 绕过")
            )
        if code != 0:
            return False, f"B站评论接口返回异常码 {code}"
        if not msgs:
            return False, "B站评论接口可达但未返回评论"
        suffix = "（已配置 Cookie）" if self.has_cookie else "（匿名访问）"
        return True, f"B站评论接口正常{suffix}"
