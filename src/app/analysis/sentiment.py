"""SnowNLP-based sentiment scoring and bucketing."""
from __future__ import annotations

from typing import Iterable

from snownlp import SnowNLP

from app.config import (
    SENTIMENT_NEGATIVE_THRESHOLD,
    SENTIMENT_POSITIVE_THRESHOLD,
)


def score_comment(text: str) -> float:
    """Return a SnowNLP sentiment score in [0, 1]. Defaults to 0.5 on failure."""
    if not text:
        return 0.5
    try:
        return float(SnowNLP(text).sentiments)
    except Exception:
        return 0.5


def label_from_score(score: float) -> str:
    """Bucket a numeric score into one of: positive / neutral / negative."""
    if score > SENTIMENT_POSITIVE_THRESHOLD:
        return "positive"
    if score < SENTIMENT_NEGATIVE_THRESHOLD:
        return "negative"
    return "neutral"


def analyze_batch(texts: Iterable[str]) -> list[tuple[float, str]]:
    """Score every text and return (score, label) tuples preserving order."""
    out: list[tuple[float, str]] = []
    for t in texts:
        score = score_comment(t)
        out.append((score, label_from_score(score)))
    return out
