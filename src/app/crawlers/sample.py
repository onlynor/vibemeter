"""Disabled synthetic fallback.

This module used to return synthetic comments when a crawler failed, so the
rest of the pipeline (sentiment, wordcloud, dashboard) could still be
demonstrated end-to-end. The user has explicitly asked that the application
ONLY surface real crawled data — fake data was misleading.

The function below is preserved so existing imports do not break, but it
always raises. Crawlers that still call into it will surface a clear error
upstream instead of silently fabricating results.
"""
from __future__ import annotations


def generate_sample(keyword: str, count: int, *, seed: int | None = None) -> list[str]:
    """Always raise — synthetic fallback is disabled by project policy."""
    raise RuntimeError(
        "示例数据兜底已被关闭：本项目要求只使用真实爬取的数据。"
        f"（关键词={keyword!r}，请求数={count}）"
    )
