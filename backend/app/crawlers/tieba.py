"""百度贴吧评论爬虫

桌面端搜索页（tieba.baidu.com/f/search/res）对匿名请求会跳百度安全验证，
移动端接口则可以匿名读取公开主题与楼层：

    关键词 -> /mo/q/search/thread -> 主题列表（JSON）
    主题   -> /mo/q/m?kz={tid}    -> 楼层回复（HTML）

可选通过环境变量 TIEBA_COOKIE 提升稳定性，未配置时依然可用。
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler, PingResult, ProgressCallback
from app.crawlers.http_utils import fetch_json, fetch_text, make_client, polite_sleep


# 被系统折叠/删除的楼层占位文案，纳入分析会污染情感分布
_PLACEHOLDER_MARKERS = (
    "该楼层疑似违规已被系统折叠",
    "内容被自动屏蔽",
    "此楼层已删除",
)


class TiebaCrawler(BaseCrawler):
    """贴吧主题回复爬虫"""

    name = "tieba"
    label = "贴吧"

    SEARCH_URL = "https://tieba.baidu.com/mo/q/search/thread"
    THREAD_URL = "https://tieba.baidu.com/mo/q/m"
    HOME = "https://tieba.baidu.com/"

    # 每个主题最多翻的楼层页数
    MAX_PAGES_PER_THREAD = 3
    MAX_THREADS = 12
    # 同时抓几个主题，理由同豆瓣：串行翻十几个主题的墙钟时间会撞上单源时限
    THREAD_CONCURRENCY = 3

    def _extra_headers(self, *, referer: str | None = None) -> dict[str, str]:
        headers = {
            "Referer": referer or self.HOME,
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        if self.cookie:
            headers["Cookie"] = self.cookie
        return headers

    async def _search_threads(self, client, keyword: str, limit: int = MAX_THREADS) -> list[dict]:
        """按关键词搜索主题，返回 [{tid, title, content, forum, url}]"""
        threads: list[dict] = []
        for page in (1, 2):
            if len(threads) >= limit:
                break
            payload = await fetch_json(
                client,
                self.SEARCH_URL,
                params={"word": keyword, "pn": page},
                headers=self._extra_headers(),
            )
            if not payload or payload.get("no") != 0:
                break
            data = payload.get("data") or {}
            for post in data.get("post_list") or []:
                tid = str(post.get("tid") or "").strip()
                if not tid or any(t["tid"] == tid for t in threads):
                    continue
                forum = (
                    post.get("forum_name")
                    or (post.get("forum_info") or {}).get("forum_name")
                    or ""
                )
                threads.append({
                    "tid": tid,
                    "title": (post.get("title") or "").strip() or f"贴吧主题 {tid}",
                    "content": _strip_markup(post.get("content") or ""),
                    "forum": forum,
                    "url": f"https://tieba.baidu.com/p/{tid}",
                })
                if len(threads) >= limit:
                    break
            if not data.get("has_more"):
                break
            await polite_sleep(0.3, 0.8)
        return threads

    async def _fetch_replies(
        self,
        client,
        thread: dict,
        target: int,
        collected: int,
    ) -> list[str]:
        """抓取一个主题下的楼层文本"""
        replies: list[str] = []
        for page in range(1, self.MAX_PAGES_PER_THREAD + 1):
            if collected + len(replies) >= target:
                break
            html = await fetch_text(
                client,
                self.THREAD_URL,
                params={"kz": thread["tid"], "pn": page},
                headers=self._extra_headers(referer=thread["url"]),
            )
            if not html:
                break
            page_replies = _parse_floor_texts(html)
            if not page_replies:
                break
            replies.extend(page_replies)
            await polite_sleep(0.6, 1.3)
        return replies

    async def fetch(
        self,
        keyword: str,
        target_count: int,
        progress_cb: ProgressCallback,
    ) -> AsyncIterator[list[str]]:
        self.reset_source_items()
        async with make_client(mobile=True, referer=self.HOME) as client:
            await progress_cb(0, "贴吧：搜索相关主题...")
            threads = await self._search_threads(client, keyword)
            if not threads:
                await progress_cb(0, "贴吧：未搜到相关主题")
                return
            for thread in threads[:6]:
                self.record_source_item({
                    "platform": self.name,
                    "title": thread["title"],
                    "subtitle": f"{thread['forum']}吧" if thread["forum"] else "贴吧主题",
                    "url": thread["url"],
                    "embed_url": "",
                    "display_type": "post",
                })
            collected = 0
            for start in range(0, len(threads), self.THREAD_CONCURRENCY):
                if collected >= target_count:
                    break
                chunk = threads[start:start + self.THREAD_CONCURRENCY]
                await progress_cb(
                    collected,
                    f"贴吧：抓取「{chunk[0]['title'][:20]}」等 {len(chunk)} 个主题楼层..."
                    f" 已收集 {collected} 条",
                )
                results = await asyncio.gather(
                    *(
                        self._fetch_replies(client, t, target_count, collected)
                        for t in chunk
                    ),
                    return_exceptions=True,
                )
                batch: list[str] = []
                for thread, result in zip(chunk, results):
                    if isinstance(result, Exception) or not result:
                        # 楼层读不到时，主题正文本身也是一条公开文本
                        if thread["content"]:
                            batch.append(thread["content"])
                        continue
                    batch.extend(result)
                if not batch:
                    continue
                collected += len(batch)
                yield batch
            if collected == 0:
                await progress_cb(collected, "贴吧：主题命中但未读到楼层内容")

    async def ping(self) -> PingResult:
        """搜索一次并试读首个主题的楼层"""
        async with make_client(mobile=True, referer=self.HOME) as client:
            threads = await self._search_threads(client, "电影", limit=1)
            if not threads:
                return False, "贴吧搜索接口无返回（可能触发百度安全验证）"
            html = await fetch_text(
                client,
                self.THREAD_URL,
                params={"kz": threads[0]["tid"], "pn": 1},
                headers=self._extra_headers(referer=threads[0]["url"]),
            )
        if not html:
            return False, "贴吧主题页无响应"
        if not _parse_floor_texts(html):
            return False, "贴吧主题页未解析出楼层内容"
        suffix = "（已配置 Cookie）" if self.has_cookie else "（匿名访问）"
        return True, f"贴吧公开楼层可用{suffix}"


def _strip_markup(raw: str) -> str:
    """搜索接口的 content 是富文本片段，可能带 <img> 等标签

    楼层走的是 ``get_text()``，标签天然不会进正文；但主题正文（楼层读不到
    时的兜底文本）是直接取的原始字段，内联图片会以整段 base64 的形式留在
    里面，既污染分析也会把 raw 导出撑大，所以在入口处就剥掉。
    """
    if not raw:
        return ""
    return BeautifulSoup(raw, "html.parser").get_text(" ", strip=True).replace("\n", " ").strip()


def _parse_floor_texts(html: str) -> list[str]:
    """从移动端主题页 HTML 中提取楼层正文"""
    soup = BeautifulSoup(html, "html.parser")
    texts: list[str] = []
    for node in soup.select("div.list_item_wrapper div.content"):
        text = node.get_text(" ", strip=True)
        if not text:
            continue
        if any(marker in text for marker in _PLACEHOLDER_MARKERS):
            continue
        texts.append(text)
    return texts
