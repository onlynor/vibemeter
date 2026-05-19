"""Abstract base class shared by every platform crawler."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, Awaitable, Callable


ProgressCallback = Callable[[int, str], Awaitable[None]]


class BaseCrawler(ABC):
    """Contract for platform-specific comment crawlers.

    Implementations must yield lists of raw comment strings via an async
    generator. Yielding in batches lets the task manager update progress
    incrementally and persist partial results if needed.
    """

    name: str = "base"

    def reset_source_items(self) -> None:
        """Clear cached source post/video metadata for the current fetch run."""
        self._source_items = []

    def record_source_item(self, item: dict) -> None:
        """Store one source post/video entry for later dashboard display."""
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
        """Return source post/video metadata collected during fetch."""
        return list(getattr(self, "_source_items", []))

    @abstractmethod
    async def fetch(
        self,
        keyword: str,
        target_count: int,
        progress_cb: ProgressCallback,
    ) -> AsyncIterator[list[str]]:
        """Yield batches of raw comment strings until target_count reached."""
        raise NotImplementedError
        # The yield below is unreachable but makes this an async generator
        # for type-checking purposes.
        yield []  # pragma: no cover
