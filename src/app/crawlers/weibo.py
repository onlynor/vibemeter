"""微博评论爬虫，使用 m.weibo.cn 移动端 JSON API，需要登录 Cookie"""
from __future__ import annotations

import os
import random
import re
from typing import AsyncIterator
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler, ProgressCallback
from app.crawlers.hot_fallback import weibo_hot
from app.crawlers.http_utils import make_client, polite_sleep


DESKTOP_EDGE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 Edg/136.0.0.0"
)

UA_POOL = [
    DESKTOP_EDGE_UA,
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
]

REFERER_POOL = [
    "https://m.weibo.cn/",
    "https://weibo.com/",
    "https://www.weibo.com/",
]

_SVS_MARKERS = ("Sina Visitor System", "/visitor/genvisitor")


def _is_visitor_challenge(text: str) -> bool:
    """检测新浪访客系统 HTML 挑战"""
    if not text:
        return False
    head = text[:2048]
    return any(marker in head for marker in _SVS_MARKERS)


def _looks_like_html(text: str) -> bool:
    """检测 JSON 端点是否返回了 HTML 外壳（Cookie 失效的信号）"""
    if not text:
        return False
    head = text.lstrip()[:512].lower()
    return head.startswith("<!doctype") or head.startswith("<html")


def _parse_cookie_string(cookie_str: str) -> dict[str, str]:
    """从浏览器 Cookie 字符串中提取 SUB / _T_WM / XSRF-TOKEN"""
    core: dict[str, str] = {}
    backup: dict[str, str] = {}
    if not cookie_str:
        return core
    cookie_str = cookie_str.strip()
    m = re.search(r"SUB=([^;]+)", cookie_str)
    if m:
        core["SUB"] = m.group(1).strip()
    m = re.search(r"_T_WM=([^;]+)", cookie_str)
    if m:
        backup["_T_WM"] = m.group(1).strip()
    m = re.search(r"XSRF-TOKEN=([^;]+)", cookie_str)
    if m:
        backup["XSRF-TOKEN"] = m.group(1).strip()
    if not core:
        for pair in cookie_str.split(";"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                core[k.strip()] = v.strip()
    return {**core, **backup}


class WeiboCrawler(BaseCrawler):
    """微博爬虫：搜索匹配微博并采集评论，需要 WEIBO_COOKIE 环境变量"""

    name = "weibo"
    BASE = "https://m.weibo.cn"
    SEARCH_PATH = "/api/container/getIndex"
    COMMENT_HOTFLOW = "/comments/hotflow"
    COMMENT_LEGACY = "/api/comments/show"

    def __init__(self) -> None:
        self._cookies = _parse_cookie_string(os.environ.get("WEIBO_COOKIE", ""))

    def _headers(self, referer: str | None = None) -> dict[str, str]:
        ua = random.choice(UA_POOL)
        is_mobile = "Mobile" in ua or "iPhone" in ua
        return {
            "Referer": referer or random.choice(REFERER_POOL),
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "user-agent": ua,
            "sec-ch-ua": (
                '"Chromium";v="136", "Microsoft Edge";v="136", "Not.A/Brand";v="99"'
            ),
            "sec-ch-ua-mobile": "?1" if is_mobile else "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        }

    async def _warm_up(self, client: httpx.AsyncClient) -> None:
        """访问 m.weibo.cn 预热会话指纹"""
        try:
            await client.get(
                f"{self.BASE}/",
                headers={
                    **self._headers(referer="https://m.weibo.cn/"),
                    "accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                    "sec-fetch-mode": "navigate",
                    "sec-fetch-dest": "document",
                    "upgrade-insecure-requests": "1",
                },
            )
        except httpx.HTTPError:
            pass

    async def _api_get(
        self,
        client: httpx.AsyncClient,
        path: str,
        params: dict | None = None,
        *,
        referer: str | None = None,
        retries: int = 2,
    ) -> dict | None:
        """GET 微博 JSON 端点，自动检测访客系统挑战"""
        url = f"{self.BASE}{path}"
        for attempt in range(retries + 1):
            try:
                resp = await client.get(
                    url,
                    params=params,
                    headers=self._headers(referer=referer),
                )
            except httpx.HTTPError:
                if attempt < retries:
                    await polite_sleep(0.3, 0.8)
                    continue
                return None

            if _is_visitor_challenge(resp.text):
                raise RuntimeError(
                    "Sina Visitor System 拦截：cookie 无效或过期，请重新登录 m.weibo.cn 后导出 WEIBO_COOKIE"
                )

            if resp.status_code >= 400:
                if attempt < retries:
                    await polite_sleep(0.3, 0.8)
                    continue
                return None

            try:
                payload = resp.json()
            except ValueError:
                    # 端点返回了 HTML，说明 Cookie 已失效
                if _looks_like_html(resp.text):
                    raise RuntimeError(
                        "微博 API 返回 HTML 而非 JSON：WEIBO_COOKIE 中的 SUB 可能已失效，请重新导出 cookie"
                    )
                if attempt < retries:
                    await polite_sleep(0.3, 0.6)
                    continue
                return None

            ok = payload.get("ok")
            if ok in (1, "1"):
                return payload
            # ok == 0 / -100 → rate limited or backed off; retry once
            if attempt < retries:
                await polite_sleep(0.5, 1.0)
                continue
            # Hand the partial payload back so callers can read the
            # error message if they want to surface it.
            return payload

        return None

    async def _search_posts(
        self,
        client: httpx.AsyncClient,
        keyword: str,
        limit: int = 20,
    ) -> list[dict]:
        posts: list[dict] = []
        seen: set[str] = set()
        encoded = quote(keyword)
        search_referer = (
            f"{self.BASE}/search?containerid=100103type%3D1%26q%3D{encoded}"
        )
        for page in range(1, 6):
            payload = await self._api_get(
                client,
                self.SEARCH_PATH,
                params={
                    "containerid": f"100103type=1&q={keyword}",
                    "page_type": "searchall",
                    "page": page,
                },
                referer=search_referer,
            )
            if not payload or payload.get("ok") not in (1, "1"):
                continue
            cards = (payload.get("data") or {}).get("cards") or []
            for card in cards:
                for mblog in self._iter_mblogs(card):
                    mid = str(mblog.get("id") or "").strip()
                    if not mid or mid in seen:
                        continue
                    seen.add(mid)
                    posts.append(self._make_post_record(mid, mblog))
                    if len(posts) >= limit:
                        return posts
            await polite_sleep(0.2, 0.5)
        return posts

    @staticmethod
    def _iter_mblogs(card: dict):
        ct = card.get("card_type")
        if ct == 9:
            inner = card.get("mblog") or {}
            if inner:
                yield inner
        for sub in card.get("card_group", []) or []:
            if sub.get("card_type") == 9:
                inner = sub.get("mblog") or {}
                if inner:
                    yield inner

    @staticmethod
    def _make_post_record(mid: str, mblog: dict) -> dict:
        raw_text = mblog.get("text") or ""
        excerpt = BeautifulSoup(raw_text, "html.parser").get_text(" ", strip=True)
        user = (mblog.get("user") or {}).get("screen_name") or ""
        title = excerpt[:60] or ("@" + user if user else f"微博原帖 {mid}")
        subtitle = f"@{user}" if user else ""
        return {
            "mid": mid,
            "title": title,
            "subtitle": subtitle,
            "url": f"https://m.weibo.cn/detail/{quote(mid)}",
            "embed_url": "",
            "display_type": "post",
        }

    async def _drain_comments(
        self,
        client: httpx.AsyncClient,
        mid: str,
        path: str,
        max_pages: int,
    ) -> AsyncIterator[list[str]]:
        """通用分页评论拉取器，兼容 hotflow 和 legacy 端点"""
        is_hotflow = path == self.COMMENT_HOTFLOW
        max_id = 0
        max_id_type = 0
        referer = f"{self.BASE}/detail/{mid}"
        for page in range(1, max_pages + 1):
            if is_hotflow:
                params: dict[str, object] = {
                    "id": mid,
                    "mid": mid,
                    "max_id_type": max_id_type,
                }
                if max_id:
                    params["max_id"] = max_id
            else:
                params = {"id": mid, "page": page}
            body = await self._api_get(
                client, path, params=params, referer=referer
            )
            if not body or body.get("ok") not in (1, "1"):
                return
            data = body.get("data") or {}
            comments = data.get("data") or []
            batch: list[str] = []
            for c in comments:
                txt = c.get("text") or ""
                if not txt:
                    continue
                cleaned = BeautifulSoup(txt, "html.parser").get_text(strip=True)
                if cleaned:
                    batch.append(cleaned)
            if batch:
                yield batch
            if is_hotflow:
                max_id = data.get("max_id") or 0
                max_id_type = data.get("max_id_type") or 0
                if not max_id:
                    return
            else:
                max_page = data.get("max") or 0
                if max_page and page >= max_page:
                    return
            await polite_sleep(0.2, 0.6)

    async def _fetch_comments(
        self, client: httpx.AsyncClient, mid: str
    ) -> AsyncIterator[list[str]]:
        """拉取评论，hotflow 无结果时回退到 legacy 端点"""
        yielded = False
        async for batch in self._drain_comments(
            client, mid, self.COMMENT_HOTFLOW, max_pages=10
        ):
            yielded = True
            yield batch
        if not yielded:
            async for batch in self._drain_comments(
                client, mid, self.COMMENT_LEGACY, max_pages=5
            ):
                yield batch

    async def fetch(
        self,
        keyword: str,
        target_count: int,
        progress_cb: ProgressCallback,
    ) -> AsyncIterator[list[str]]:
        if not self._cookies.get("SUB"):
            raise RuntimeError(
                "未配置 WEIBO_COOKIE（或缺少 SUB 字段）。"
                "微博公开搜索现已强制登录态，请登录 m.weibo.cn 后导出整段 Cookie 设到 WEIBO_COOKIE 环境变量。"
            )

        collected = 0
        self.reset_source_items()
        async with make_client(referer=f"{self.BASE}/") as client:
            for k, v in self._cookies.items():
                client.cookies.set(k, v, domain=".weibo.cn")
            await self._warm_up(client)

            posts = await self._search_posts(client, keyword)

            used_hot_fallback = False
            if not posts:
                await progress_cb(
                    0, "微博关键词无返回（接口被风控），尝试使用微博热搜榜..."
                )
                hot_items = await weibo_hot(client, limit=10)
                    # 记录热搜条目，确保即使精搜无结果也能展示
                for hot in hot_items[:3]:
                    self.record_source_item({
                        "platform": self.name,
                        "title": hot["title"],
                        "subtitle": hot.get("subtitle") or "",
                        "url": hot["url"],
                        "embed_url": hot.get("embed_url") or "",
                        "display_type": hot.get("display_type") or "post",
                    })
                for hot in hot_items:
                    refined = await self._search_posts(client, hot["title"], limit=3)
                    posts.extend(refined)
                    if len(posts) >= 6:
                        break
                used_hot_fallback = bool(posts)

            if not posts:
                raise RuntimeError(
                    "微博搜索与热搜榜均未返回博文（cookie 可能已过期或风控触发）"
                )

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
            await progress_cb(
                0, f"找到 {len(posts)} 条{prefix}微博，开始采集评论..."
            )

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
            raise RuntimeError("微博候选博文均无可读评论（cookie 可能已失效）")
