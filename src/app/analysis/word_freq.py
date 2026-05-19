"""Tokenization, stopword filtering, and word frequency aggregation."""
from __future__ import annotations

from collections import Counter
import re
from typing import Iterable

import jieba
import jieba.posseg as pseg

from app.config import STOPWORDS_PATH


_STOPWORDS: set[str] | None = None

_BUILTIN_STOPWORDS: set[str] = {
    "大家", "东西", "这个", "那个", "一些", "一种", "一直", "已经",
    "还是", "如果", "因为", "所以", "而且", "然后", "但是", "就是",
    "还有", "没有", "什么", "怎么", "真的", "感觉", "觉得", "可以",
    "直接", "现在", "里面", "出来", "这样", "那种", "这种", "很多",
    "一下", "一点", "一次", "一个", "我们", "你们", "他们", "自己",
    "不是", "不会", "不要", "而已", "而是", "作为", "可能", "非常",
    "比较", "确实", "完全", "一直", "免费",
}

# Allowed POS prefixes from jieba's tagging scheme:
# n* = nouns, v* = verbs, a* = adjectives.
_ALLOWED_POS_PREFIXES: tuple[str, ...] = ("n", "v", "a")


def load_stopwords() -> set[str]:
    """Load stopwords from disk lazily; reused for the lifetime of the process."""
    global _STOPWORDS
    if _STOPWORDS is None:
        words: set[str] = set(_BUILTIN_STOPWORDS)
        if STOPWORDS_PATH.exists():
            with STOPWORDS_PATH.open("r", encoding="utf-8") as fh:
                for line in fh:
                    word = line.strip()
                    if word and not word.startswith("#"):
                        words.add(word)
        _STOPWORDS = words
    return _STOPWORDS


# Pre-warm jieba's main dictionary so the first request isn't slow.
jieba.initialize()


def _extra_stopwords(keyword: str | None) -> set[str]:
    """Build per-task exclusions from the query keyword itself."""
    if not keyword:
        return set()
    candidates = {keyword.strip().lower()}
    candidates.update(
        part.strip().lower()
        for part in re.split(r"[\s,，、/|:：_\-]+", keyword)
        if part.strip()
    )
    candidates.update(
        token.strip().lower()
        for token in jieba.cut(keyword)
        if token.strip()
    )
    return {item for item in candidates if len(item) >= 2}


def tokenize(text: str, *, extra_stopwords: set[str] | None = None) -> list[str]:
    """Tokenize ``text`` keeping only multi-character content words."""
    stopwords = load_stopwords()
    extra_stopwords = extra_stopwords or set()
    tokens: list[str] = []
    for word, flag in pseg.cut(text):
        word = word.strip()
        if len(word) < 2:
            continue
        lowered = word.lower()
        if word in stopwords or lowered in stopwords:
            continue
        if word in extra_stopwords or lowered in extra_stopwords:
            continue
        if not flag:
            continue
        if not any(flag.startswith(prefix) for prefix in _ALLOWED_POS_PREFIXES):
            continue
        tokens.append(word)
    return tokens


def word_frequencies(
    texts: Iterable[str],
    top_n: int = 50,
    *,
    keyword: str | None = None,
    excluded_words: set[str] | None = None,
) -> list[tuple[str, int]]:
    """Compute the top-N most common content words across ``texts``."""
    counter: Counter[str] = Counter()
    extra_stopwords = _extra_stopwords(keyword)
    if excluded_words:
        extra_stopwords.update({word.lower() for word in excluded_words if word})
    for text in texts:
        counter.update(tokenize(text, extra_stopwords=extra_stopwords))
    return counter.most_common(top_n)
