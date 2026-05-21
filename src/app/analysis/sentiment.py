"""基于 SnowNLP 的情感评分与分类"""
from __future__ import annotations

from typing import Iterable

from snownlp import SnowNLP

from app.config import (
    SENTIMENT_NEGATIVE_THRESHOLD,
    SENTIMENT_POSITIVE_THRESHOLD,
)


def score_comment(text: str) -> float:
    """返回 SnowNLP 情感分数 [0, 1]，失败时返回 0.5"""
    if not text:
        return 0.5
    try:
        return float(SnowNLP(text).sentiments)
    except Exception:
        return 0.5


def label_from_score(score: float) -> str:
    """将数值分数转换为情感标签：正向/中立/负向"""
    if score > SENTIMENT_POSITIVE_THRESHOLD:
        return "positive"
    if score < SENTIMENT_NEGATIVE_THRESHOLD:
        return "negative"
    return "neutral"


def analyze_batch(texts: Iterable[str]) -> list[tuple[float, str]]:
    """批量评分并返回 (分数, 标签) 元组列表，保持原始顺序"""
    out: list[tuple[float, str]] = []
    for t in texts:
        score = score_comment(t)
        out.append((score, label_from_score(score)))
    return out
