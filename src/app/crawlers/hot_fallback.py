"""各平台热搜回退，关键词无结果时使用公开热搜榜"""
from __future__ import annotations

from typing import Any

from app.crawlers.http_utils import fetch_json


async def bilibili_hot(client, limit: int = 10) -> list[dict[str, Any]]:
    """B站热门视频榜（无需签名）"""
    payload = await fetch_json(
        client,
        "https://api.bilibili.com/x/web-interface/popular",
        params={"ps": limit, "pn": 1},
        headers={"Referer": "https://www.bilibili.com/"},
    )
    if not payload or payload.get("code") != 0:
        return []
    items = (payload.get("data") or {}).get("list") or []
    out: list[dict[str, Any]] = []
    for item in items[:limit]:
        aid = item.get("aid")
        if not aid:
            continue
        bvid = item.get("bvid") or ""
        out.append({
            "aid": int(aid),
            "bvid": bvid,
            "title": item.get("title") or "",
            "subtitle": (item.get("desc") or "")[:80],
            "url": f"https://www.bilibili.com/video/{bvid}/" if bvid else f"https://www.bilibili.com/video/av{aid}/",
            "embed_url": (
                f"https://player.bilibili.com/player.html?bvid={bvid}&page=1&high_quality=1&as_wide=1"
                if bvid else ""
            ),
            "display_type": "video",
            "platform": "bilibili",
        })
    return out


async def weibo_hot(client, limit: int = 10) -> list[dict[str, Any]]:
    """微博移动端热搜列表（仅标题）"""
    payload = await fetch_json(
        client,
        "https://m.weibo.cn/api/container/getIndex",
        params={"containerid": "106003type=25&filter_type=realtimehot"},
        headers={
            "Referer": "https://m.weibo.cn/",
            "accept": "application/json, text/plain, */*",
        },
    )
    if not payload or payload.get("ok") != 1:
        return []
    cards = (payload.get("data") or {}).get("cards") or []
    out: list[dict[str, Any]] = []
    for card in cards:
        for inner in card.get("card_group") or []:
            title = (inner.get("desc") or "").strip()
            scheme = inner.get("scheme") or ""
            if not title or not scheme:
                continue
            out.append({
                "title": title,
                "subtitle": inner.get("desc_extr") or "",
                "url": scheme,
                "embed_url": "",
                "display_type": "post",
                "platform": "weibo",
            })
            if len(out) >= limit:
                return out
    return out
