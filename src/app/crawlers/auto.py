"""All-network aggregator over the available public crawlers.

Walks Bilibili → Weibo in order, accumulating real comments. Each
source gets a short "first-batch" timeout — if a platform is silently
blocked (Weibo's ``ok:-100``, anti-bot challenges, slow network) the
aggregator drops it within ``FIRST_BATCH_TIMEOUT`` seconds rather than
waiting for the source's own retry/backoff to finish. Once a source
produces real data we let it run to completion (or until
``target_count`` is reached).
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

from app.crawlers.base import BaseCrawler, ProgressCallback
from app.crawlers.bilibili import BilibiliCrawler
from app.crawlers.weibo import WeiboCrawler


# Maximum wall-clock seconds we'll wait for a source's *first* batch.
# Once the source has yielded at least one batch we trust it and remove
# the timeout for subsequent batches.
FIRST_BATCH_TIMEOUT: float = 12.0


class AutoCrawler(BaseCrawler):
    """Try every public source in order and stop once enough data is collected."""

    name = "auto"

    def __init__(self) -> None:
        self._sources: list[BaseCrawler] = [BilibiliCrawler(), WeiboCrawler()]

    async def fetch(
        self,
        keyword: str,
        target_count: int,
        progress_cb: ProgressCallback,
    ) -> AsyncIterator[list[str]]:
        collected = 0
        failures: list[str] = []
        self.reset_source_items()

        for crawler in self._sources:
            if collected >= target_count:
                break

            label = self._label(crawler.name)
            base_count = collected
            remaining = target_count - collected

            await progress_cb(collected, f"聚合搜索：尝试 {label}...")

            async def proxy_progress(current: int, message: str = "") -> None:
                shown = base_count + current
                await progress_cb(shown, f"[{label}] {message}" if message else "")

            crawler_yielded = 0
            agen = crawler.fetch(keyword, remaining, proxy_progress)
            got_first_batch = False
            try:
                while True:
                    if got_first_batch:
                        batch = await agen.__anext__()
                    else:
                        # First batch is gated by a short wall-clock timeout
                        # so dead sources don't hold up the pipeline.
                        batch = await asyncio.wait_for(
                            agen.__anext__(),
                            timeout=FIRST_BATCH_TIMEOUT,
                        )
                        got_first_batch = True
                    if not batch:
                        continue
                    collected += len(batch)
                    crawler_yielded += len(batch)
                    yield batch
                    if collected >= target_count:
                        break
            except StopAsyncIteration:
                pass
            except asyncio.TimeoutError:
                failures.append(f"{label}: 首批数据超时（{FIRST_BATCH_TIMEOUT:.0f}s）")
                await progress_cb(
                    collected,
                    f"{label} 在 {FIRST_BATCH_TIMEOUT:.0f}s 内未返回数据，已跳过",
                )
            except Exception as exc:
                failures.append(f"{label}: {exc}")
                await progress_cb(
                    collected,
                    f"{label} 暂不可用（{exc}），切换下一个源...",
                )
            finally:
                # Ensure async generator resources are released even when
                # we abort mid-stream (wait_for cancellation, exceptions).
                try:
                    await agen.aclose()
                except Exception:
                    pass

            if crawler_yielded > 0:
                for item in crawler.get_source_items():
                    self.record_source_item(item)

        if collected == 0:
            detail = "；".join(failures) if failures else "全部公开源都没返回评论"
            raise RuntimeError(f"未能获取真实数据：{detail}")

    @staticmethod
    def _label(name: str) -> str:
        return {
            "weibo": "微博",
            "bilibili": "B站",
        }.get(name, name)
