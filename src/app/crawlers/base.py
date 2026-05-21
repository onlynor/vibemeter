"""所有平台爬虫共享的抽象基类"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, Awaitable, Callable


ProgressCallback = Callable[[int, str], Awaitable[None]]


class BaseCrawler(ABC):
    """平台评论爬虫的抽象接口"""

    name: str = "base"

    def reset_source_items(self) -> None:
        """清除当前抓取运行的缓存源帖/视频元数据"""
        self._source_items = []

    def record_source_item(self, item: dict) -> None:
        """存储一个源帖/视频条目用于仪表板展示"""
        items = getattr(self, "_source_items", [])
        url = str(item.get("url") or "").strip()
        if not url:
            return
        if any(existing.get("url") == url for existing in items):
            self._source_items = items
            return
        items.append(item)
        self._source_items = items[:6]

    def get_source_items(self) -> list[dict]:
        """返回抓取期间收集的源帖/视频元数据"""
        return list(getattr(self, "_source_items", []))

    @abstractmethod
    async def fetch(
        self,
        keyword: str,
        target_count: int,
        progress_cb: ProgressCallback,
    ) -> AsyncIterator[list[str]]:
        """逐批返回原始评论字符串，直到达到目标数量"""
        raise NotImplementedError
        # The yield below is unreachable but makes this an async generator
        # for type-checking purposes.
        yield []  # pragma: no cover
