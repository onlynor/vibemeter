"""知乎评论爬虫

知乎对匿名请求关得很死（实测：search_v3 恒返回 400、questions/*/answers
与 api.zhihu.com 返回 403 异常拦截），因此这里分两条路：

* 配置了 ZHIHU_COOKIE：走搜索接口找回答，再读回答下的公开评论；
* 未配置 Cookie：退回到匿名仍可读的知乎热榜，只取标题/摘要里
  真正命中关键词的条目，避免把无关热榜内容混进情感分析。
"""
from __future__ import annotations

import re
from typing import Any, AsyncIterator

from app.crawlers.base import BaseCrawler, PingResult, ProgressCallback
from app.crawlers.http_utils import fetch_json, make_client, polite_sleep


_TAG_RE = re.compile(r"<[^>]+>")


class ZhihuCrawler(BaseCrawler):
    """知乎回答评论爬虫"""

    name = "zhihu"
    label = "知乎"

    SEARCH_URL = "https://www.zhihu.com/api/v4/search_v3"
    COMMENTS_URL = "https://www.zhihu.com/api/v4/comment_v5/answers/{aid}/root_comment"
    HOT_LIST_URL = "https://api.zhihu.com/topstory/hot-lists/total"
    HOME = "https://www.zhihu.com/"

    MAX_ANSWERS = 8
    HOT_LIST_LIMIT = 50

    def _extra_headers(self) -> dict[str, str]:
        headers = {
            "Referer": self.HOME,
            "Accept": "application/json, text/plain, */*",
            "x-requested-with": "fetch",
        }
        if self.cookie:
            headers["Cookie"] = self.cookie
        return headers

    # Cookie 路径：搜索 -> 回答 -> 评论

    async def _search_answers(self, client, keyword: str) -> list[dict]:
        """搜索回答，返回 [{aid, title, url, excerpt}]；需要有效 Cookie"""
        out: list[dict] = []
        for offset in (0, 20):
            if len(out) >= self.MAX_ANSWERS:
                break
            payload = await fetch_json(
                client,
                self.SEARCH_URL,
                params={
                    "t": "general",
                    "q": keyword,
                    "correction": 1,
                    "offset": offset,
                    "limit": 20,
                    "search_source": "Normal",
                },
                headers=self._extra_headers(),
            )
            if not payload:
                break
            for item in payload.get("data") or []:
                obj = item.get("object") or item
                aid = obj.get("id")
                question = obj.get("question") or {}
                title = _clean_html(
                    question.get("title")
                    or question.get("name")
                    or obj.get("title")
                    or ""
                )
                if not aid or not title:
                    continue
                if any(x["aid"] == str(aid) for x in out):
                    continue
                qid = question.get("id") or ""
                out.append({
                    "aid": str(aid),
                    "title": title,
                    "url": obj.get("url") or f"https://www.zhihu.com/question/{qid}/answer/{aid}",
                    "excerpt": _clean_html(obj.get("excerpt") or obj.get("content") or ""),
                })
                if len(out) >= self.MAX_ANSWERS:
                    break
            await polite_sleep()
        return out

    async def _fetch_answer_comments(
        self,
        client,
        aid: str,
        want: int,
        collected: int,
    ) -> list[str]:
        """拉取一个回答下的根评论"""
        comments: list[str] = []
        offset = ""
        for _ in range(3):
            if collected + len(comments) >= want:
                break
            payload = await fetch_json(
                client,
                self.COMMENTS_URL.format(aid=aid),
                params={"order_by": "score", "limit": 20, "offset": offset},
                headers=self._extra_headers(),
            )
            if not payload:
                break
            data = payload.get("data") or []
            if not data:
                break
            for entry in data:
                text = _clean_html(entry.get("content") or "")
                if text:
                    comments.append(text)
            paging = payload.get("paging") or {}
            if paging.get("is_end"):
                break
            offset = _next_offset(paging.get("next") or "")
            if not offset:
                break
            await polite_sleep(0.5, 1.2)
        return comments

    # 无 Cookie 路径：热榜关键词过滤

    async def _hot_list(self, client) -> list[dict[str, Any]]:
        """匿名可读的知乎热榜"""
        payload = await fetch_json(
            client,
            self.HOT_LIST_URL,
            params={"limit": self.HOT_LIST_LIMIT},
            headers={"Accept": "application/json", "x-api-version": "3.0.91"},
        )
        items: list[dict[str, Any]] = []
        for entry in (payload or {}).get("data") or []:
            target = entry.get("target") or {}
            title = ((target.get("title_area") or {}).get("text") or "").strip()
            if not title:
                continue
            items.append({
                "title": title,
                "excerpt": ((target.get("excerpt_area") or {}).get("text") or "").strip(),
                "url": (target.get("link") or {}).get("url") or "",
                "heat": ((target.get("metrics_area") or {}).get("text") or "").strip(),
            })
        return items

    @staticmethod
    def _match_hot_items(items: list[dict], keyword: str) -> list[dict]:
        """只保留标题或摘要真正命中关键词的热榜条目"""
        needle = keyword.strip().lower()
        if not needle:
            return []
        return [
            item for item in items
            if needle in item["title"].lower() or needle in item["excerpt"].lower()
        ]

    async def fetch(
        self,
        keyword: str,
        target_count: int,
        progress_cb: ProgressCallback,
    ) -> AsyncIterator[list[str]]:
        self.reset_source_items()
        async with make_client(referer=self.HOME) as client:
            collected = 0

            if self.has_cookie:
                await progress_cb(0, "知乎：搜索相关回答...")
                answers = await self._search_answers(client, keyword)
                for answer in answers[:6]:
                    self.record_source_item({
                        "platform": self.name,
                        "title": answer["title"],
                        "subtitle": "知乎回答",
                        "url": answer["url"],
                        "embed_url": "",
                        "display_type": "post",
                    })
                for answer in answers:
                    if collected >= target_count:
                        break
                    await progress_cb(
                        collected,
                        f"知乎：抓取「{answer['title'][:20]}」评论... 已收集 {collected} 条",
                    )
                    batch = await self._fetch_answer_comments(
                        client, answer["aid"], target_count, collected
                    )
                    if not batch:
                        # 回答摘要本身也是一条公开文本
                        if not answer["excerpt"]:
                            continue
                        batch = [answer["excerpt"]]
                    collected += len(batch)
                    yield batch
                if collected:
                    return
                await progress_cb(
                    0,
                    "知乎：Cookie 搜索未取到内容（可能已过期），改用热榜匹配...",
                )
            else:
                await progress_cb(
                    0,
                    "知乎：未配置 ZHIHU_COOKIE，匿名搜索不可用，改用热榜匹配...",
                )

            # 回退：热榜里命中关键词的条目
            hot_items = self._match_hot_items(await self._hot_list(client), keyword)
            if not hot_items:
                await progress_cb(
                    collected,
                    "知乎：热榜中没有与该关键词相关的条目（配置 ZHIHU_COOKIE 可开启搜索）",
                )
                return
            for item in hot_items[:6]:
                self.record_source_item({
                    "platform": self.name,
                    "title": item["title"],
                    "subtitle": f"知乎热榜 · {item['heat']}" if item["heat"] else "知乎热榜",
                    "url": item["url"],
                    "embed_url": "",
                    "display_type": "post",
                })
            batch = [item["title"] for item in hot_items]
            batch.extend(item["excerpt"] for item in hot_items if item["excerpt"])
            await progress_cb(
                collected,
                f"知乎：热榜命中 {len(hot_items)} 条相关话题",
            )
            yield batch

    async def ping(self) -> PingResult:
        """有 Cookie 时探搜索接口，否则探匿名可读的热榜"""
        async with make_client(referer=self.HOME) as client:
            if self.has_cookie:
                answers = await self._search_answers(client, "电影")
                if answers:
                    return True, "知乎搜索可用（已配置 Cookie）"
                return False, "ZHIHU_COOKIE 已配置但搜索无返回，Cookie 可能已过期"
            hot = await self._hot_list(client)
        if not hot:
            return False, "知乎热榜接口无响应"
        return False, (
            f"仅热榜可用（{len(hot)} 条），关键词搜索需配置 ZHIHU_COOKIE"
        )


def _clean_html(text: str) -> str:
    """知乎返回的是 HTML 片段，去标签后压平空白"""
    return _TAG_RE.sub("", text or "").replace("\n", " ").strip()


def _next_offset(next_url: str) -> str:
    """从分页 URL 中取出 offset 参数"""
    match = re.search(r"[?&]offset=([^&]*)", next_url)
    return match.group(1) if match else ""
