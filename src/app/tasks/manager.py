"""Background task orchestration: crawl, preprocess, analyse, persist, export.

A single ``TaskManager`` instance owns:

* an in-memory ``asyncio.Queue`` per ``task_id`` used to fan progress
  updates out to one or more WebSocket subscribers;
* the SQLite-backed lifecycle records for each task;
* the JSON export artefacts written under ``data/exports``.
"""
from __future__ import annotations

import asyncio
import csv
import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite

from app.config import (
    CLEANED_DIR,
    DATA_DIR,
    DB_PATH,
    MAX_REPRESENTATIVE_COMMENTS,
    OUTPUT_DIR,
    RAW_DIR,
    TOP_WORDS_LIMIT,
    get_font_path,
)
from app.crawlers import get_crawler
from app.analysis.preprocess import preprocess_comments
from app.analysis.llm_insight import LLMConfig, generate_insight
from app.analysis.sentiment import analyze_batch
from app.analysis.word_freq import phrase_frequencies, phrase_or_word_frequencies, word_frequencies


EXPORTS_DIR: Path = DATA_DIR / "exports"
MIN_REQUIRED_COMMENTS = 300
MAX_HISTORY_TASKS = 10

# Characters Windows / Linux file systems both reject inside filenames.
_FILENAME_BANNED = r'<>:"/\\|?*\x00-\x1F'


def _safe_filename(text: str, *, max_len: int = 40) -> str:
    """Strip filename-hostile characters from ``text`` for use in a path.

    Empty / whitespace input returns ``"task"`` so we always have a slug.
    """
    import re

    cleaned = re.sub(rf"[{_FILENAME_BANNED}\s]+", "_", (text or "").strip())
    cleaned = cleaned.strip("._") or "task"
    return cleaned[:max_len]


class TaskManager:
    """Manages background analysis pipelines and their progress channels."""

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    # -- public API --------------------------------------------------------

    def get_queue(self, task_id: str) -> asyncio.Queue:
        """Return (creating if necessary) the progress queue for a task."""
        if task_id not in self._queues:
            self._queues[task_id] = asyncio.Queue()
        return self._queues[task_id]

    async def create_task(
        self,
        keyword: str,
        platform: str,
        count: int,
        *,
        llm_base_url: str = "",
        llm_api_key: str = "",
        llm_model: str = "",
        llm_question: str = "",
        llm_context_format: str = "xml",
    ) -> str:
        """Persist a task row and schedule the background pipeline."""
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        task_id = str(uuid.uuid4())
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT COALESCE(MAX(task_no), 0) FROM tasks")
            task_no = (await cursor.fetchone())[0] + 1
            await db.execute(
                """INSERT INTO tasks
                   (task_no, task_id, keyword, platform, target_count,
                    status, start_time)
                   VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
                (
                    task_no,
                    task_id,
                    keyword,
                    platform,
                    count,
                    datetime.utcnow().isoformat(timespec="seconds"),
                ),
            )
            await self._prune_history(db, keep=MAX_HISTORY_TASKS)
            await db.commit()
        # Pre-create the queue so a fast-connecting WebSocket client never
        # races ahead of the producer.
        self.get_queue(task_id)
        self._tasks[task_id] = asyncio.create_task(
            self._run(
                task_id,
                keyword,
                platform,
                count,
                LLMConfig(
                    base_url=llm_base_url,
                    api_key=llm_api_key,
                    model=llm_model,
                    question=llm_question,
                    context_format=llm_context_format,
                ),
            )
        )
        return task_id

    # -- pipeline ---------------------------------------------------------

    async def _run(
        self,
        task_id: str,
        keyword: str,
        platform: str,
        count: int,
        llm_config: LLMConfig,
    ) -> None:
        """Main pipeline executed in the background for one task."""
        started = time.time()
        platform_label = self._platform_label(platform)
        try:
            await self._set_status(task_id, "crawling")
            await self._push(
                task_id,
                status="crawling",
                current=0,
                total=count,
                message=f"开始采集 {platform_label} 关于「{keyword}」的评论...",
            )

            raw_comments, source_items = await self._do_crawl(task_id, keyword, platform, count)
            raw_total = len(raw_comments)

            await self._push(
                task_id,
                status="preprocessing",
                current=raw_total,
                total=max(count, raw_total),
                raw_total=raw_total,
                message=f"共搜索到 {raw_total} 条原始评论，正在清洗与去重...",
            )
            await self._set_status(task_id, "preprocessing")
            cleaned = preprocess_comments(raw_comments)
            valid_total = len(cleaned)

            if not cleaned:
                raise RuntimeError("清洗后无有效评论，无法进入分析阶段")

            await self._push(
                task_id,
                status="analyzing",
                current=valid_total,
                total=valid_total,
                raw_total=raw_total,
                message=f"原始评论 {raw_total} 条，清洗后保留 {valid_total} 条，正在进行情感分析...",
            )
            await self._set_status(task_id, "analyzing")

            loop = asyncio.get_running_loop()
            scored = await loop.run_in_executor(None, analyze_batch, cleaned)

            await self._persist_comments(task_id, platform, cleaned, scored)

            buckets = self._bucket_comments(cleaned, scored)

            await self._push(
                task_id,
                status="wordcloud",
                current=valid_total,
                total=valid_total,
                raw_total=raw_total,
                message=f"原始评论 {raw_total} 条，有效评论 {valid_total} 条，正在提取观点短语与代表性评论...",
            )

            raw_positive_words = await loop.run_in_executor(
                None, lambda: word_frequencies(buckets["positive"], TOP_WORDS_LIMIT * 3, keyword=keyword)
            )
            raw_negative_words = await loop.run_in_executor(
                None, lambda: word_frequencies(buckets["negative"], TOP_WORDS_LIMIT * 3, keyword=keyword)
            )
            excluded_words = self._shared_neutral_terms(raw_positive_words, raw_negative_words)

            positive_words = await loop.run_in_executor(
                None, lambda: phrase_or_word_frequencies(
                    cleaned, scored, TOP_WORDS_LIMIT, keyword=keyword, sentiment="positive"
                )
            )
            negative_words = await loop.run_in_executor(
                None, lambda: phrase_or_word_frequencies(
                    cleaned, scored, TOP_WORDS_LIMIT, keyword=keyword, sentiment="negative"
                )
            )

            # P1-3: Differential word frequency — subtract cross-sentiment weight
            pos_map = {w: s for w, s in positive_words}
            neg_map = {w: s for w, s in negative_words}
            diff_positive = sorted(
                [(w, round(s - neg_map.get(w, 0), 3)) for w, s in positive_words if s > neg_map.get(w, 0)],
                key=lambda x: x[1], reverse=True,
            )
            diff_negative = sorted(
                [(w, round(s - pos_map.get(w, 0), 3)) for w, s in negative_words if s > pos_map.get(w, 0)],
                key=lambda x: x[1], reverse=True,
            )
            # Use differential results for persistence and summary
            positive_words = diff_positive
            negative_words = diff_negative
            all_words = await loop.run_in_executor(
                None, lambda: word_frequencies(
                    cleaned, TOP_WORDS_LIMIT, keyword=keyword, excluded_words=excluded_words
                )
            )

            top_positive, top_negative = self._representative_comments(cleaned, scored)
            elapsed = round(time.time() - started, 2)
            summary = {
                "total": valid_total,
                "raw_total": raw_total,
                "positive": len(buckets["positive"]),
                "neutral": len(buckets["neutral"]),
                "negative": len(buckets["negative"]),
                "elapsed": elapsed,
                "keyword": keyword,
                "platform": platform,
                "source_items": source_items,
                "top_positive": top_positive,
                "top_negative": top_negative,
                "top_positive_words": positive_words[:10],
                "top_negative_words": negative_words[:10],
                "llm_insight": None,
            }

            if llm_config.enabled:
                await self._push(
                    task_id,
                    status="llm",
                    current=valid_total,
                    total=valid_total,
                    raw_total=raw_total,
                    message=f"原始评论 {raw_total} 条，有效评论 {valid_total} 条，正在生成分析解读...",
                )
                try:
                    summary["llm_insight"] = await generate_insight(llm_config, summary)
                except Exception as exc:
                    await self._push(
                        task_id,
                        status="llm",
                        current=valid_total,
                        total=valid_total,
                        raw_total=raw_total,
                        message=f"LLM 分析增强未启用: {exc}",
                    )

            await self._persist_results(
                task_id=task_id,
                summary=summary,
                positive_words=positive_words,
                negative_words=negative_words,
                all_words=all_words,
            )

            self._export_artifacts(
                task_id=task_id,
                keyword=keyword,
                platform=platform,
                raw=raw_comments,
                cleaned=cleaned,
                scored=scored,
                summary=summary,
            )

            self._save_output_artifacts(
                task_id=task_id,
                keyword=keyword,
                positive_words=positive_words,
                negative_words=negative_words,
                summary=summary,
            )

            await self._push(
                task_id,
                status="completed",
                current=valid_total,
                total=valid_total,
                raw_total=raw_total,
                message=f"分析完成：共搜索到 {raw_total} 条原始评论，清洗后保留 {valid_total} 条有效评论",
                elapsed=elapsed,
            )

        except Exception as exc:  # surface any failure to the UI
            await self._set_status(task_id, "failed", str(exc))
            await self._push(
                task_id,
                status="failed",
                message=f"任务失败: {exc}",
                raw_total=0,
                error=str(exc),
            )

    # -- helpers ---------------------------------------------------------

    async def _do_crawl(
        self,
        task_id: str,
        keyword: str,
        platform: str,
        count: int,
    ) -> tuple[list[str], list[dict]]:
        """Drive the platform crawler and stream progress to subscribers."""
        crawler = get_crawler(platform)
        collected: list[str] = []

        async def progress_cb(current: int, message: str = "") -> None:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE tasks SET current_count = ? WHERE task_id = ?",
                    (current, task_id),
                )
                await db.commit()
            await self._push(
                task_id,
                status="crawling",
                current=current,
                total=count,
                message=message or f"目前搜索到 {current} 条原始评论",
            )

        try:
            async for batch in crawler.fetch(keyword, count, progress_cb):
                collected.extend(batch)
                if len(collected) >= count:
                    break
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc

        if not collected:
            raise RuntimeError("未抓取到有效评论，请切换公开数据源或更换关键词")
        return collected, crawler.get_source_items()

    async def _persist_comments(
        self,
        task_id: str,
        platform: str,
        cleaned: list[str],
        scored: list[tuple[float, str]],
    ) -> None:
        now = datetime.utcnow().isoformat(timespec="seconds")
        rows = [
            (task_id, text, platform, now, score, label)
            for text, (score, label) in zip(cleaned, scored)
        ]
        async with aiosqlite.connect(DB_PATH) as db:
            await db.executemany(
                """INSERT INTO comments
                   (task_id, content, platform, fetch_time,
                    sentiment_score, sentiment_label)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                rows,
            )
            await db.execute(
                """UPDATE tasks SET total_count = ?, current_count = ?
                   WHERE task_id = ?""",
                (len(cleaned), len(cleaned), task_id),
            )
            await db.commit()

    @staticmethod
    def _platform_label(platform: str) -> str:
        return {
            "auto": "自动聚合公开源",
            "weibo": "微博",
            "bilibili": "B站",
        }.get(platform, platform)

    @staticmethod
    def _bucket_comments(
        cleaned: list[str],
        scored: list[tuple[float, str]],
    ) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {"positive": [], "neutral": [], "negative": []}
        for text, (_score, label) in zip(cleaned, scored):
            out.setdefault(label, []).append(text)
        return out

    @staticmethod
    def _representative_comments(
        cleaned: list[str],
        scored: list[tuple[float, str]],
    ) -> tuple[list[dict], list[dict]]:
        scored_pairs = [(text, score) for text, (score, _) in zip(cleaned, scored)]
        scored_pairs.sort(key=lambda x: x[1])
        bottom = scored_pairs[:MAX_REPRESENTATIVE_COMMENTS]
        top = scored_pairs[-MAX_REPRESENTATIVE_COMMENTS:][::-1]
        return (
            [{"text": t, "score": round(s, 3)} for t, s in top],
            [{"text": t, "score": round(s, 3)} for t, s in bottom],
        )

    @staticmethod
    def _shared_neutral_terms(
        positive_words: list[tuple[str, int]],
        negative_words: list[tuple[str, int]],
    ) -> set[str]:
        """Drop topical words that dominate both sides similarly."""
        positive_map = dict(positive_words)
        negative_map = dict(negative_words)
        excluded: set[str] = set()
        for word in set(positive_map) & set(negative_map):
            pos_count = positive_map[word]
            neg_count = negative_map[word]
            if min(pos_count, neg_count) < 3:
                continue
            if min(pos_count, neg_count) / max(pos_count, neg_count) < 0.35:
                continue
            excluded.add(word)
        return excluded

    async def _persist_results(
        self,
        task_id: str,
        summary: dict,
        positive_words: list[tuple[str, int]],
        negative_words: list[tuple[str, int]],
        all_words: list[tuple[str, int]],
    ) -> None:
        end = datetime.utcnow().isoformat(timespec="seconds")
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """UPDATE tasks
                   SET status = 'completed', end_time = ?
                   WHERE task_id = ?""",
                (end, task_id),
            )
            await db.execute(
                """INSERT OR REPLACE INTO results
                   (task_id, summary_json, positive_words_json,
                    negative_words_json, all_words_json,
                    positive_comments_json, negative_comments_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    json.dumps(summary, ensure_ascii=False),
                    json.dumps(positive_words, ensure_ascii=False),
                    json.dumps(negative_words, ensure_ascii=False),
                    json.dumps(all_words, ensure_ascii=False),
                    json.dumps(summary["top_positive"], ensure_ascii=False),
                    json.dumps(summary["top_negative"], ensure_ascii=False),
                ),
            )
            await db.commit()

    def _export_artifacts(
        self,
        task_id: str,
        keyword: str,
        platform: str,
        raw: list[str],
        cleaned: list[str],
        scored: list[tuple[float, str]],
        summary: dict,
    ) -> None:
        """Persist raw + cleaned + analysed artefacts to disk for submission."""
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        CLEANED_DIR.mkdir(parents=True, exist_ok=True)
        raw_path = EXPORTS_DIR / f"{task_id}_raw.json"
        cleaned_path = EXPORTS_DIR / f"{task_id}_cleaned.json"
        analysed_path = EXPORTS_DIR / f"{task_id}_analysed.json"
        summary_path = EXPORTS_DIR / f"{task_id}_summary.json"

        meta = {
            "task_id": task_id,
            "keyword": keyword,
            "platform": platform,
            "exported_at": datetime.utcnow().isoformat(timespec="seconds"),
        }

        raw_path.write_text(
            json.dumps({**meta, "comments": raw}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        cleaned_path.write_text(
            json.dumps({**meta, "comments": cleaned}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        analysed_path.write_text(
            json.dumps(
                {
                    **meta,
                    "records": [
                        {"text": text, "score": round(score, 4), "label": label}
                        for text, (score, label) in zip(cleaned, scored)
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # ----- data/raw + data/cleaned: csv + json per task --------------
        # These mirror the export files but live in the rubric-mandated
        # ``raw/`` and ``cleaned/`` folders, in both csv and json so
        # downstream tools (Excel, pandas) can pick whichever they prefer.
        name_base = f"{task_id}_{platform}_{_safe_filename(keyword)}"
        self._dump_dataset(RAW_DIR / f"{name_base}.json",
                           RAW_DIR / f"{name_base}.csv",
                           raw, meta, header="raw_comment")
        self._dump_dataset(CLEANED_DIR / f"{name_base}.json",
                           CLEANED_DIR / f"{name_base}.csv",
                           cleaned, meta, header="cleaned_comment")

    @staticmethod
    def _dump_dataset(
        json_path: Path,
        csv_path: Path,
        comments: list[str],
        meta: dict,
        *,
        header: str,
    ) -> None:
        """Write a comment list in both json and csv at the given paths.

        - JSON keeps the task meta + comment array, easy for programmatic use.
        - CSV is utf-8-sig (Excel-friendly) with a single column and a header.
        """
        json_path.write_text(
            json.dumps(
                {**meta, "count": len(comments), "comments": comments},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        with csv_path.open("w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.writer(fp)
            writer.writerow([header])
            for line in comments:
                writer.writerow([line])

    def _save_output_artifacts(
        self,
        task_id: str,
        keyword: str,
        positive_words: list[tuple[str, float]],
        negative_words: list[tuple[str, float]],
        summary: dict,
    ) -> None:
        """Save pie chart, word clouds, and representative comments to output/."""
        import io

        from wordcloud import WordCloud

        out_dir = OUTPUT_DIR / f"{task_id}_{_safe_filename(keyword)}"
        out_dir.mkdir(parents=True, exist_ok=True)
        font_path = get_font_path()

        # --- Pie chart ---
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            labels = ["正向", "中立", "负向"]
            sizes = [summary.get("positive", 0), summary.get("neutral", 0), summary.get("negative", 0)]
            colors = ["#2eb872", "#f0b400", "#e64545"]
            fig, ax = plt.subplots(figsize=(6, 4))
            ax.pie(sizes, labels=labels, colors=colors, autopct="%1.1f%%",
                   startangle=90, textprops={"fontsize": 12})
            ax.set_title(f"情感分布 · {keyword}", fontsize=14, fontweight="bold")
            fig.tight_layout()
            fig.savefig(out_dir / "sentiment_pie.png", dpi=150)
            plt.close(fig)
        except Exception:
            pass

        # --- Word clouds ---
        if font_path:
            for name, words, palette in [
                ("wordcloud_positive", positive_words, "Greens"),
                ("wordcloud_negative", negative_words, "Reds"),
            ]:
                if not words:
                    continue
                try:
                    cloud = WordCloud(
                        font_path=font_path, width=1200, height=800,
                        background_color="white", max_words=200,
                        margin=2, prefer_horizontal=0.85,
                        relative_scaling=0.2, min_font_size=10,
                        max_font_size=120, collocations=False,
                        colormap=palette,
                    )
                    cloud.generate_from_frequencies(dict(words))
                    cloud.to_file(str(out_dir / f"{name}.png"))
                except Exception:
                    pass

        # --- Representative comments ---
        comments_data = {
            "keyword": keyword,
            "top_positive": summary.get("top_positive", []),
            "top_negative": summary.get("top_negative", []),
        }
        (out_dir / "representative_comments.json").write_text(
            json.dumps(comments_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def _set_status(
        self,
        task_id: str,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        async with aiosqlite.connect(DB_PATH) as db:
            if error is None:
                await db.execute(
                    "UPDATE tasks SET status = ? WHERE task_id = ?",
                    (status, task_id),
                )
            else:
                await db.execute(
                    "UPDATE tasks SET status = ?, error = ? WHERE task_id = ?",
                    (status, error, task_id),
                )
            await db.commit()

    async def _push(self, task_id: str, **payload) -> None:
        await self.get_queue(task_id).put(payload)

    async def _prune_history(self, db: aiosqlite.Connection, *, keep: int) -> None:
        """Keep only the latest N tasks plus their related artefacts."""
        cursor = await db.execute(
            """SELECT task_id
               FROM tasks
               WHERE task_no NOT IN (
                   SELECT task_no FROM tasks
                   ORDER BY task_no DESC
                   LIMIT ?
               )""",
            (keep,),
        )
        old_task_ids = [row[0] for row in await cursor.fetchall()]
        if not old_task_ids:
            return
        for old_task_id in old_task_ids:
            await db.execute("DELETE FROM comments WHERE task_id = ?", (old_task_id,))
            await db.execute("DELETE FROM results WHERE task_id = ?", (old_task_id,))
            await db.execute("DELETE FROM tasks WHERE task_id = ?", (old_task_id,))
            for path in EXPORTS_DIR.glob(f"{old_task_id}_*.json"):
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
            self._queues.pop(old_task_id, None)
            task = self._tasks.get(old_task_id)
            if task and task.done():
                self._tasks.pop(old_task_id, None)


task_manager = TaskManager()
