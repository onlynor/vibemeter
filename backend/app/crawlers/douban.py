"""豆瓣评论爬虫

豆瓣的网页端（www.douban.com/search、movie.douban.com/subject/*/comments）
对匿名访问会返回反爬校验页，HTML 选择器拿不到任何内容；而移动端 rexxar
接口在带正确 Referer 时可以匿名读取公开短评，因此这里走 rexxar：

    关键词 -> /rexxar/api/v2/search/subjects  -> 影视/图书条目
    条目   -> /rexxar/api/v2/{type}/{id}/interests -> 公开短评

可选通过环境变量 DOUBAN_COOKIE 提升可读分页深度，未配置时依然可用。
"""
from __future__ import annotations

from typing import AsyncIterator

from app.crawlers.base import BaseCrawler, PingResult, ProgressCallback
from app.crawlers.http_utils import fetch_json, make_client, polite_sleep


class DoubanCrawler(BaseCrawler):
    """豆瓣短评爬虫（影视 + 图书）"""

    name = "douban"
    label = "豆瓣"

    SEARCH_URL = "https://m.douban.com/rexxar/api/v2/search/subjects"
    INTERESTS_URL = "https://m.douban.com/rexxar/api/v2/{kind}/{sid}/interests"
    HOME = "https://m.douban.com/movie/"

    # rexxar 接口只按 movie / book 两类归档短评
    SUBJECT_TYPES: tuple[str, ...] = ("movie", "book")
    # 每个条目最多翻的页数（每页 20 条）
    MAX_PAGES_PER_SUBJECT = 8
    PAGE_SIZE = 20

    def _extra_headers(self, *, referer: str | None = None) -> dict[str, str]:
        """rexxar 接口强依赖 m.douban.com 的 Referer，缺失会被拒绝"""
        headers = {
            "Referer": referer or self.HOME,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        if self.cookie:
            headers["Cookie"] = self.cookie
        return headers

    async def _search_subjects(self, client, keyword: str, limit: int = 8) -> list[dict]:
        """按关键词搜索影视与图书条目，返回 [{kind, sid, title, subtitle, url}]"""
        subjects: list[dict] = []
        for kind in self.SUBJECT_TYPES:
            if len(subjects) >= limit:
                break
            payload = await fetch_json(
                client,
                self.SEARCH_URL,
                params={"q": keyword, "type": kind, "count": 10, "start": 0},
                headers=self._extra_headers(),
            )
            items = ((payload or {}).get("subjects") or {}).get("items") or []
            for item in items:
                target = item.get("target") or {}
                sid = str(target.get("id") or "").strip()
                title = (target.get("title") or "").strip()
                if not sid or not title:
                    continue
                target_kind = item.get("target_type") or kind
                if target_kind not in self.SUBJECT_TYPES:
                    continue
                if any(s["sid"] == sid and s["kind"] == target_kind for s in subjects):
                    continue
                subjects.append({
                    "kind": target_kind,
                    "sid": sid,
                    "title": title,
                    "subtitle": (target.get("card_subtitle") or "")[:80],
                    "url": f"https://{target_kind}.douban.com/subject/{sid}/",
                })
            await polite_sleep(0.3, 0.8)
        return subjects[:limit]

    async def _fetch_comments(
        self,
        client,
        subject: dict,
        target: int,
        collected: int,
    ) -> list[str]:
        """分页抓取一个条目的公开短评"""
        comments: list[str] = []
        url = self.INTERESTS_URL.format(kind=subject["kind"], sid=subject["sid"])
        referer = f"https://m.douban.com/{subject['kind']}/subject/{subject['sid']}/"
        for page in range(self.MAX_PAGES_PER_SUBJECT):
            if collected + len(comments) >= target:
                break
            payload = await fetch_json(
                client,
                url,
                params={
                    "count": self.PAGE_SIZE,
                    "start": page * self.PAGE_SIZE,
                    "order_by": "hot",
                },
                headers=self._extra_headers(referer=referer),
            )
            if not payload:
                break
            interests = payload.get("interests") or []
            if not interests:
                break
            for entry in interests:
                text = (entry.get("comment") or "").replace("\n", " ").strip()
                if text:
                    comments.append(text)
            await polite_sleep(0.6, 1.4)
        return comments

    async def fetch(
        self,
        keyword: str,
        target_count: int,
        progress_cb: ProgressCallback,
    ) -> AsyncIterator[list[str]]:
        self.reset_source_items()
        async with make_client(mobile=True, referer=self.HOME) as client:
            await progress_cb(0, "豆瓣：搜索相关条目...")
            subjects = await self._search_subjects(client, keyword)
            if not subjects:
                await progress_cb(0, "豆瓣：未搜到相关影视或图书条目")
                return
            for subject in subjects[:5]:
                self.record_source_item({
                    "platform": self.name,
                    "title": subject["title"],
                    "subtitle": subject["subtitle"] or (
                        "豆瓣电影短评" if subject["kind"] == "movie" else "豆瓣读书短评"
                    ),
                    "url": subject["url"],
                    "embed_url": "",
                    "display_type": "post",
                })
            collected = 0
            for subject in subjects[:5]:
                if collected >= target_count:
                    break
                await progress_cb(
                    collected,
                    f"豆瓣：抓取「{subject['title']}」短评... 已收集 {collected} 条",
                )
                batch = await self._fetch_comments(
                    client, subject, target_count, collected
                )
                if not batch:
                    continue
                collected += len(batch)
                yield batch
            if collected == 0:
                await progress_cb(collected, "豆瓣：条目命中但未读到公开短评")

    async def ping(self) -> PingResult:
        """搜索一次并试读第一条目的短评，覆盖真正会被拦的那个接口"""
        async with make_client(mobile=True, referer=self.HOME) as client:
            subjects = await self._search_subjects(client, "电影", limit=1)
            if not subjects:
                return False, "豆瓣搜索接口无返回（可能正在风控）"
            subject = subjects[0]
            payload = await fetch_json(
                client,
                self.INTERESTS_URL.format(kind=subject["kind"], sid=subject["sid"]),
                params={"count": 1, "start": 0, "order_by": "hot"},
                headers=self._extra_headers(
                    referer=f"https://m.douban.com/{subject['kind']}/subject/{subject['sid']}/"
                ),
            )
        if payload is None:
            return False, "豆瓣短评接口无响应"
        if not (payload.get("interests") or []):
            return False, "豆瓣短评接口返回空数据"
        suffix = "（已配置 Cookie）" if self.has_cookie else "（匿名访问）"
        return True, f"豆瓣公开短评可用{suffix}"
