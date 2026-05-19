"""Weibo comment crawler using the m.weibo.cn mobile JSON API."""
from __future__ import annotations

from typing import AsyncIterator
from urllib.parse import quote

from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler, ProgressCallback
from app.crawlers.hot_fallback import weibo_hot
from app.crawlers.http_utils import fetch_json, make_client, polite_sleep


class WeiboCrawler(BaseCrawler):
    """Search Weibo for matching posts then drain their comment threads.

    The mobile container search is increasingly rate-limited for
    anonymous requests (``ok: -100``); when that happens we fall back
    to the public hot-search list so the dashboard still has real
    titles to display.
    """

    name = "weibo"
    BASE = "https://m.weibo.cn"

    def _extra_headers(self) -> dict[str, str]:
        return {
            "Referer": f"{self.BASE}/",
            "X-Requested-With": "XMLHttpRequest",
            "MWeibo-Pwa": "1",
        }

    async def _search_posts(self, client, keyword: str, limit: int = 20) -> list[dict]:
        url = f"{self.BASE}/api/container/getIndex"
        posts: list[dict] = []
        for page in range(1, 6):
            payload = await fetch_json(
                client,
                url,
                params={
                    "containerid": f"100103type=1&q={keyword}",
                    "page_type": "searchall",
                    "page": page,
                },
                headers=self._extra_headers(),
            )
            if not payload:
                continue
            cards = (payload.get("data") or {}).get("cards") or []
            for card in cards:
                self._collect_posts(card, posts)
            if len(posts) >= limit:
                break
            await polite_sleep(0.4, 1.0)
        seen: set[str] = set()
        ordered: list[dict] = []
        for post in posts:
            mid = post.get("mid")
            if not mid or mid in seen:
                continue
            seen.add(mid)
            ordered.append(post)
        return ordered[:limit]

    @staticmethod
    def _collect_posts(card: dict, out: list[dict]) -> None:
        if card.get("card_type") == 9:
            WeiboCrawler._append_post(card.get("mblog") or {}, out)
        for inner in card.get("card_group", []) or []:
            if inner.get("card_type") == 9:
                WeiboCrawler._append_post((inner.get("mblog") or {}), out)

    @staticmethod
    def _append_post(mblog: dict, out: list[dict]) -> None:
        mid = str(mblog.get("id") or "").strip()
        if not mid:
            return
        raw_text = mblog.get("text") or ""
        excerpt = BeautifulSoup(raw_text, "html.parser").get_text(" ", strip=True)
        user = (mblog.get("user") or {}).get("screen_name") or ""
        title = excerpt[:60] or ("@" + user if user else f"微博原帖 {mid}")
        subtitle = f"@{user}" if user else ""
        out.append({
            "mid": mid,
            "title": title,
            "subtitle": subtitle,
            "url": f"https://m.weibo.cn/detail/{quote(mid)}",
            "embed_url": "",
            "display_type": "post",
        })

    async def _fetch_comments(
        self, client, mid: str, max_pages: int = 10
    ) -> AsyncIterator[list[str]]:
        url = f"{self.BASE}/comments/hotflow"
        max_id = 0
        max_id_type = 0
        for _ in range(max_pages):
            params: dict[str, object] = {
                "id": mid,
                "mid": mid,
                "max_id_type": max_id_type,
            }
            if max_id:
                params["max_id"] = max_id
            body = await fetch_json(
                client, url, params=params, headers=self._extra_headers()
            )
            if not body or body.get("ok") != 1:
                break
            data = body.get("data") or {}
            comments = data.get("data") or []
            batch: list[str] = []
            for c in comments:
                raw_text = c.get("text", "")
                if not raw_text:
                    continue
                text = BeautifulSoup(raw_text, "html.parser").get_text(strip=True)
                if text:
                    batch.append(text)
            if batch:
                yield batch
            max_id = data.get("max_id", 0) or 0
            max_id_type = data.get("max_id_type", 0) or 0
            if not max_id:
                break
            await polite_sleep(0.5, 1.2)

    async def fetch(
        self,
        keyword: str,
        target_count: int,
        progress_cb: ProgressCallback,
    ) -> AsyncIterator[list[str]]:
        collected = 0
        self.reset_source_items()
        async with make_client(mobile=True, referer=f"{self.BASE}/") as client:
            posts = await self._search_posts(client, keyword)
            used_hot_fallback = False
            if not posts:
                await progress_cb(0, "微博关键词无返回（接口被风控），尝试使用微博热搜榜...")
                hot_items = await weibo_hot(client, limit=10)
                # The hot endpoint only gives us search keywords, not mids,
                # so we re-search each top word and keep the first matching
                # post — that still gives real titles + real comment threads
                # for the words people are actually talking about today.
                for hot in hot_items:
                    refined = await self._search_posts(client, hot["title"], limit=3)
                    posts.extend(refined)
                    if len(posts) >= 6:
                        break
                used_hot_fallback = bool(posts)
            if not posts:
                raise RuntimeError("微博搜索与热搜榜均未返回博文")
            for post in posts[:6]:
                self.record_source_item({
                    "platform": self.name,
                    "title": post["title"],
                    "subtitle": post["subtitle"],
                    "url": post["url"],
                    "embed_url": post["embed_url"],
                    "display_type": post["display_type"],
                })
            prefix = "热搜衍生" if used_hot_fallback else "相关"
            await progress_cb(0, f"找到 {len(posts)} 条{prefix}微博，开始采集评论...")
            for post in posts:
                if collected >= target_count:
                    break
                async for batch in self._fetch_comments(client, post["mid"]):
                    yield batch
                    collected += len(batch)
                    await progress_cb(collected, "")
                    if collected >= target_count:
                        break
        if collected == 0:
            raise RuntimeError("微博候选博文均无可读评论")
