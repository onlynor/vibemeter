"""全网聚合爬虫，并发运行各公开数据源，按来源均衡合并结果

与早期实现相比有三处关键区别：

1. **均衡采样**：早期把各源的批次按到达顺序直接拼接，谁快谁就把
   ``target_count`` 的名额吃光——豆瓣分页快、单页产出高，很容易出现
   "五源聚合"实际上九成是豆瓣的情况，情感分布也就退化成了豆瓣的分布。
   现在按来源分桶后轮转取样，输出流本身即是均衡的，下游无论在哪里截断
   都不会偏向某一个平台。
2. **整体超时**：早期只有首批 8s 超时，首批之后 ``__anext__`` 是无限等待，
   一个慢源足以把整轮聚合拖成"httpx 超时 × 重试 × 分页 sleep"的叠加。
   现在每个源额外有一个整体 deadline。
3. **跨源去重**：热点内容常被多平台转载，早期这些重复项会先占满配额，
   等 ``preprocess_comments`` 再去重时样本已经缩水了。现在在收集阶段
   就按归一化文本去重，配额只留给真正不同的内容。
4. **可限定子集**：``AutoCrawler(platforms=[...])`` 只启动指定的源，
   前端的数据源多选因此是真生效的，而不是"勾了也照样五个源全跑"。
"""
from __future__ import annotations

import asyncio
from collections import deque
from typing import AsyncIterator, Sequence

from app.config import (
    CRAWL_EMIT_CHUNK,
    CRAWL_FIRST_BATCH_TIMEOUT,
    CRAWL_SOURCE_DEADLINE,
)
from app.crawlers.base import BaseCrawler, ProgressCallback
from app.crawlers.bilibili import BilibiliCrawler
from app.crawlers.douban import DoubanCrawler
from app.crawlers.tieba import TiebaCrawler
from app.crawlers.weibo import WeiboCrawler
from app.crawlers.zhihu import ZhihuCrawler


# 默认值与环境变量覆盖都在 app.config 里；这里保留模块级别名，一是调用点读起来
# 更短，二是测试要按模块属性把它们临时改小（见 tests/test_auto.py 顶部）。
#
# 等待数据源首批数据的最大秒数
FIRST_BATCH_TIMEOUT: float = CRAWL_FIRST_BATCH_TIMEOUT
# 单个数据源从启动到放弃的整体上限，防止慢源拖垮整轮聚合
SOURCE_DEADLINE: float = CRAWL_SOURCE_DEADLINE
# 攒够多少条才做一次均衡切片下发（太小会让轮转退化成"来一条发一条"）
EMIT_CHUNK: int = CRAWL_EMIT_CHUNK


def _normalize(text: str) -> str:
    """用于跨源去重的归一化文本（仅压平空白，不做清洗）

    真正的清洗在 ``analysis.preprocess`` 里做，这里只求"同一条内容在
    不同平台的转载能被认出来"，因此刻意保持轻量。
    """
    return " ".join(text.split())


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
        await result_queue.put(("source_item", crawler.name, item))


async def _drain_source(
    crawler: BaseCrawler,
    keyword: str,
    target_count: int,
    progress_cb: ProgressCallback,
    label: str,
    result_queue: asyncio.Queue,
    failures: list[str],
) -> None:
    """驱动单个爬虫并将批次数据推入共享队列

    每个源有两重时限：首批 ``FIRST_BATCH_TIMEOUT``（快速识别"这个源
    今天不可用"），以及整体 ``SOURCE_DEADLINE``（防止分页阶段无限拖）。
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + SOURCE_DEADLINE
    agen = crawler.fetch(keyword, target_count, progress_cb)
    got_first_batch = False
    settled = False
    emitted_source_urls: set[str] = set()

    def settle() -> None:
        """告诉消费者"这个源已有定论"（拿到首批 或 判定不可用）

        用 put_nowait：队列无界，不会阻塞，也就不会在取消路径上多出一个
        可被打断的 await 点。
        """
        nonlocal settled
        if settled:
            return
        settled = True
        result_queue.put_nowait(("settled", crawler.name, None))

    try:
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                failures.append(f"{label}: 超过单源总时限（{SOURCE_DEADLINE:.0f}s）")
                await progress_cb(0, f"{label} 已达单源时限，停止继续翻页")
                break
            budget = remaining if got_first_batch else min(FIRST_BATCH_TIMEOUT, remaining)
            batch = await asyncio.wait_for(agen.__anext__(), timeout=budget)
            got_first_batch = True
            settle()
            await _flush_source_items(crawler, result_queue, emitted_source_urls)
            if not batch:
                continue
            await result_queue.put(("batch", crawler.name, batch))
    except StopAsyncIteration:
        settle()
    except asyncio.CancelledError:
        # 配额已满时由消费者主动取消，属正常路径，不记为失败
        raise
    except asyncio.TimeoutError:
        settle()
        if got_first_batch:
            failures.append(f"{label}: 翻页阶段超时")
        else:
            failures.append(f"{label}: 首批数据超时（{FIRST_BATCH_TIMEOUT:.0f}s）")
            await progress_cb(
                0,
                f"{label} 在 {FIRST_BATCH_TIMEOUT:.0f}s 内未返回数据，已跳过",
            )
    except Exception as exc:
        settle()
        failures.append(f"{label}: {exc}")
        await progress_cb(0, f"{label} 暂不可用（{exc}），已跳过")
    finally:
        # 走到这里无论成败都已有定论；break 出循环（超时限）也要放行闸门
        settle()
        try:
            await agen.aclose()
        except Exception:
            pass
    # 始终传播源条目，即使没有返回评论
    try:
        await _flush_source_items(crawler, result_queue, emitted_source_urls)
    except Exception:
        pass


class AutoCrawler(BaseCrawler):
    """并发尝试所有公开数据源，按来源均衡地凑够目标数量"""

    name = "auto"
    label = "聚合搜索"

    # 顺序影响 dashboard 原帖展示、进度展示以及均衡取样的轮转顺序
    PLATFORM_ORDER: tuple[str, ...] = ("bilibili", "weibo", "douban", "zhihu", "tieba")
    # 原帖列表展示上限
    MAX_SOURCE_ITEMS: int = 10

    SOURCE_CLASSES: dict[str, type[BaseCrawler]] = {
        "bilibili": BilibiliCrawler,
        "weibo": WeiboCrawler,
        "douban": DoubanCrawler,
        "zhihu": ZhihuCrawler,
        "tieba": TiebaCrawler,
    }

    def __init__(self, platforms: Sequence[str] | None = None) -> None:
        """``platforms`` 限定本轮只跑哪几个源，None / 空表示全部

        前端的数据源多选此前只能折叠成"单选某个源"或"全都跑"，勾掉一个平台
        并不会真的不去抓它。这里接受子集后那个多选才名副其实。未知名字直接
        忽略而不是报错：调用方可能来自更新过的前端，多传一个源不该让整轮采集
        失败。
        """
        wanted = [p for p in (platforms or []) if p in self.SOURCE_CLASSES]
        # 保持 PLATFORM_ORDER 的顺序，轮转与原帖展示的次序才稳定
        names = [p for p in self.PLATFORM_ORDER if p in wanted] or list(self.PLATFORM_ORDER)
        self._sources: list[BaseCrawler] = [self.SOURCE_CLASSES[n]() for n in names]
        self._stats: dict[str, int] = {}

    @property
    def platforms(self) -> list[str]:
        """本实例实际启用的采集源"""
        return [c.name for c in self._sources]

    def get_source_stats(self) -> dict[str, int]:
        """返回本轮各来源实际贡献的评论条数

        聚合结果里"哪个平台占了多少"是判断样本是否有代表性的关键信息，
        单看总数看不出来，所以单独暴露给上层写进 summary。
        """
        return dict(self._stats)

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
        """按平台轮转取样，保证每个有产出的源都能出现在原帖列表里

        早先的实现是"按平台优先级拼接后直接截断"：只要排在前面的
        两个源各贡献 3 条就把名额吃光，后面的源哪怕抓到了数据，
        原帖列表里也一条都看不到。改成轮转后先给每个源各一条，
        再回头补第二条，名额在各源之间摊平。
        """
        items = list(getattr(self, "_source_items", []))
        buckets: dict[str, list[dict]] = {}
        for item in items:
            buckets.setdefault(item.get("platform", ""), []).append(item)
        if not buckets:
            return []

        # 已知平台按既定优先级排，未知平台缀在后面并保持出现顺序
        known = set(self.PLATFORM_ORDER)
        order = [p for p in self.PLATFORM_ORDER if p in buckets]
        order += [p for p in buckets if p not in known]

        ordered: list[dict] = []
        for depth in range(max(len(b) for b in buckets.values())):
            for platform in order:
                bucket = buckets[platform]
                if depth < len(bucket):
                    ordered.append(bucket[depth])
        return ordered[:self.MAX_SOURCE_ITEMS]

    def _bucket_order(self, buckets: dict[str, deque]) -> list[str]:
        """轮转顺序：已知平台按既定优先级，未知平台缀在后面"""
        known = set(self.PLATFORM_ORDER)
        order = [p for p in self.PLATFORM_ORDER if p in buckets]
        order += [p for p in buckets if p not in known]
        return order

    def _take_balanced(self, buckets: dict[str, deque], limit: int) -> list[str]:
        """跨来源轮转取出至多 limit 条，并记录各来源贡献

        轮转而不是顺序拼接，是为了让输出流在任意前缀上都保持均衡：
        上层 ``TaskManager`` 一旦收够就会截断，若流本身有偏，截断后的
        样本同样有偏。
        """
        out: list[str] = []
        order = self._bucket_order(buckets)
        while len(out) < limit:
            progressed = False
            for platform in order:
                bucket = buckets.get(platform)
                if not bucket:
                    continue
                out.append(bucket.popleft())
                self._stats[platform] = self._stats.get(platform, 0) + 1
                progressed = True
                if len(out) >= limit:
                    break
            if not progressed:
                break
        return out

    async def fetch(
        self,
        keyword: str,
        target_count: int,
        progress_cb: ProgressCallback,
    ) -> AsyncIterator[list[str]]:
        self.reset_source_items()
        self._stats = {}
        result_queue: asyncio.Queue = asyncio.Queue()
        failures: list[str] = []
        seen: set[str] = set()
        buckets: dict[str, deque[str]] = {}
        buffered = 0
        emitted = 0
        emitted_ref = [0]

        tasks: list[asyncio.Task] = []
        for crawler in self._sources:
            label = crawler.label
            await progress_cb(0, f"聚合搜索：启动 {label}...")
            cb = self._make_progress(label, progress_cb, emitted_ref)
            tasks.append(
                asyncio.create_task(
                    _drain_source(
                        crawler, keyword, target_count, cb,
                        label, result_queue, failures,
                    )
                )
            )

        # 所有爬虫任务完成后发送结束信号
        async def _wait_and_signal() -> None:
            await asyncio.gather(*tasks, return_exceptions=True)
            await result_queue.put(("done", None, None))

        signal_task = asyncio.create_task(_wait_and_signal())
        loop = asyncio.get_running_loop()
        started = loop.time()

        settled = 0
        try:
            while emitted < target_count:
                kind, platform, payload = await result_queue.get()
                if kind == "done":
                    break
                if kind == "source_item":
                    self.record_source_item(payload)
                    continue
                if kind == "settled":
                    settled += 1
                    continue
                # kind == "batch"
                for text in payload:
                    key = _normalize(text)
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    buckets.setdefault(platform, deque()).append(text)
                    buffered += 1

                # 轮转只有在"每个还活着的源都已有机会填过桶"之后才是公平的：
                # 抢跑的源若在别人首批返回前就把缓冲区掏空，均衡就白做了。
                #
                # 开闸条件是"所有源都已有定论"，而不是死等满 FIRST_BATCH_TIMEOUT：
                # 各源都在 1s 内返回时，按时间等就是白白多花 7s 才推出第一批，
                # 前端的进度条也就卡在 0 不动。时间上限只作为兜底——万一某个源
                # 既不产出也不抛错（比如 TCP 连接挂住），闸门不能永远关着。
                if settled < len(self._sources) and loop.time() - started < FIRST_BATCH_TIMEOUT:
                    continue
                if buffered < EMIT_CHUNK:
                    continue
                chunk = self._take_balanced(
                    buckets, min(EMIT_CHUNK, target_count - emitted)
                )
                if chunk:
                    buffered -= len(chunk)
                    emitted += len(chunk)
                    emitted_ref[0] = emitted
                    yield chunk

            # 收尾：把缓冲区里剩下的按同样的轮转规则补齐
            while emitted < target_count and buffered > 0:
                chunk = self._take_balanced(buckets, target_count - emitted)
                if not chunk:
                    break
                buffered -= len(chunk)
                emitted += len(chunk)
                emitted_ref[0] = emitted
                yield chunk
        finally:
            for task in tasks:
                task.cancel()
            signal_task.cancel()
            await asyncio.gather(*tasks, signal_task, return_exceptions=True)

        if emitted == 0:
            detail = "；".join(failures) if failures else "全部公开源都没返回评论"
            raise RuntimeError(f"未能获取真实数据：{detail}")

    @staticmethod
    def _make_progress(
        label: str,
        progress_cb: ProgressCallback,
        emitted_ref: list[int],
    ) -> ProgressCallback:
        """把子爬虫的进度回调改写成"聚合口径"的进度

        子爬虫报的是它自己的累计条数，直接透传会与其它源的计数叠加，
        在 UI 上表现为进度反复跳变，因此这里一律用聚合后的已发送条数。
        """
        async def cb(current: int, message: str = "") -> None:
            await progress_cb(emitted_ref[0], f"[{label}] {message}" if message else "")
        return cb
