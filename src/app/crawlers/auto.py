"""全网聚合爬虫，并发运行 B站和微博，超时自动跳过"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

from app.crawlers.base import BaseCrawler, ProgressCallback
from app.crawlers.bilibili import BilibiliCrawler
from app.crawlers.weibo import WeiboCrawler


# 等待数据源首批数据的最大秒数
FIRST_BATCH_TIMEOUT: float = 8.0


async def _flush_source_items(
    crawler: BaseCrawler,
    result_queue: asyncio.Queue,
    emitted_urls: set[str],
) -> None:
    """将新发现的源条目推入共享队列（仅一次）"""
    for item in crawler.get_source_items():
        url = str(item.get("url") or "").strip()
        if not url or url in emitted_urls:
            continue
        emitted_urls.add(url)
        await result_queue.put(("source_item", item))


async def _drain_source(
    crawler: BaseCrawler,
    keyword: str,
    target_count: int,
    progress_cb: ProgressCallback,
    label: str,
    result_queue: asyncio.Queue,
    collected_ref: list[int],
    failures: list[str],
) -> None:
    """驱动单个爬虫并将批次数据推入共享队列"""
    agen = crawler.fetch(keyword, target_count, progress_cb)
    got_first_batch = False
    emitted_source_urls: set[str] = set()
    try:
        while True:
            if got_first_batch:
                batch = await agen.__anext__()
            else:
                batch = await asyncio.wait_for(
                    agen.__anext__(),
                    timeout=FIRST_BATCH_TIMEOUT,
                )
                got_first_batch = True
            await _flush_source_items(crawler, result_queue, emitted_source_urls)
            if not batch:
                continue
            collected_ref[0] += len(batch)
            await result_queue.put(("batch", batch))
            if collected_ref[0] >= target_count:
                break
    except StopAsyncIteration:
        pass
    except asyncio.TimeoutError:
        failures.append(f"{label}: 首批数据超时（{FIRST_BATCH_TIMEOUT:.0f}s）")
        await progress_cb(
            collected_ref[0],
            f"{label} 在 {FIRST_BATCH_TIMEOUT:.0f}s 内未返回数据，已跳过",
        )
    except Exception as exc:
        failures.append(f"{label}: {exc}")
        await progress_cb(
            collected_ref[0],
            f"{label} 暂不可用（{exc}），已跳过",
        )
    finally:
        try:
            await agen.aclose()
        except Exception:
            pass
    # 始终传播源条目，即使没有返回评论
    await _flush_source_items(crawler, result_queue, emitted_source_urls)


class AutoCrawler(BaseCrawler):
    """并发尝试所有公开数据源，收集足够数据后停止"""

    name = "auto"

    def __init__(self) -> None:
        self._sources: list[BaseCrawler] = [BilibiliCrawler(), WeiboCrawler()]

    def record_source_item(self, item: dict) -> None:
        """记录源条目，每个平台最多 3 个"""
        items = getattr(self, "_source_items", [])
        url = str(item.get("url") or "").strip()
        if not url:
            return
        if any(existing.get("url") == url for existing in items):
            return
        platform = item.get("platform", "")
        platform_count = sum(1 for i in items if i.get("platform") == platform)
        if platform_count >= 3:
            return
        items.append(item)
        self._source_items = items

    def get_source_items(self) -> list[dict]:
        """返回排序后的源条目：B站在前，微博在后"""
        items = list(getattr(self, "_source_items", []))
        ordered: list[dict] = []
        for platform in ("bilibili", "weibo"):
            ordered.extend(item for item in items if item.get("platform") == platform)
        ordered.extend(item for item in items if item.get("platform") not in {"bilibili", "weibo"})
        return ordered[:6]

    async def fetch(
        self,
        keyword: str,
        target_count: int,
        progress_cb: ProgressCallback,
    ) -> AsyncIterator[list[str]]:
        self.reset_source_items()
        result_queue: asyncio.Queue = asyncio.Queue()
        collected_ref = [0]
        failures: list[str] = []

        tasks = []
        for crawler in self._sources:
            label = self._label(crawler.name)
            await progress_cb(0, f"聚合搜索：启动 {label}...")

            async def make_progress(lb: str, base: list[int]):
                async def cb(current: int, message: str = "") -> None:
                    # ``base[0]`` is already the shared aggregate count.
                    # Adding the child crawler's cumulative ``current``
                    # double-counts batches in the UI.
                    shown = base[0]
                    await progress_cb(shown, f"[{lb}] {message}" if message else "")
                return cb

            cb = await make_progress(label, collected_ref)
            task = asyncio.create_task(
                _drain_source(
                    crawler, keyword, target_count, cb,
                    label, result_queue, collected_ref, failures,
                )
            )
            tasks.append(task)

        # 所有爬虫任务完成后发送结束信号
        async def _wait_and_signal():
            await asyncio.gather(*tasks, return_exceptions=True)
            await result_queue.put(("done", None))

        asyncio.create_task(_wait_and_signal())

        stop_yielding_batches = False
        while True:
            kind, payload = await result_queue.get()
            if kind == "done":
                break
            if kind == "batch":
                if stop_yielding_batches:
                    continue
                yield payload
                if collected_ref[0] >= target_count:
                    stop_yielding_batches = True
            elif kind == "source_item":
                self.record_source_item(payload)

        if collected_ref[0] == 0:
            detail = "；".join(failures) if failures else "全部公开源都没返回评论"
            raise RuntimeError(f"未能获取真实数据：{detail}")

    @staticmethod
    def _label(name: str) -> str:
        return {
            "weibo": "微博",
            "bilibili": "B站",
        }.get(name, name)
