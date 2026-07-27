"""所有平台爬虫共享的抽象基类"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, Awaitable, Callable

from app.crawlers.cookies import (
    cookie_configured,
    cookie_env_name,
    cookie_issue,
    get_cookie,
)


ProgressCallback = Callable[[int, str], Awaitable[None]]

# ping() 的返回：(是否可用, 面向用户的中文说明)
PingResult = tuple[bool, str]


class BaseCrawler(ABC):
    """平台评论爬虫的抽象接口"""

    name: str = "base"
    label: str = "基础"
    # 无 Cookie 时该平台是否完全不可用（微博即属此类）
    cookie_required: bool = False

    # Cookie 辅助

    @property
    def cookie_env(self) -> str:
        """该平台可选 Cookie 对应的环境变量名"""
        return cookie_env_name(self.name)

    @property
    def cookie(self) -> str:
        """当前进程环境里配置的 Cookie，未配置或格式非法为空串"""
        return get_cookie(self.name)

    @property
    def has_cookie(self) -> bool:
        return cookie_configured(self.name)

    @property
    def cookie_issue(self) -> str:
        """Cookie 的格式问题描述，没问题返回空串"""
        return cookie_issue(self.name)

    # 源条目

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
        """返回抓取期间收集的源条目元数据"""
        return list(getattr(self, "_source_items", []))

    # 抓取与探活

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

    async def ping(self) -> PingResult:
        """轻量探测该数据源当前是否可用

        子类应当探测真正会被风控的那个接口，而不只是首页，
        否则健康检查会给出过于乐观的结论。
        """
        return True, "未实现可用性探测"
