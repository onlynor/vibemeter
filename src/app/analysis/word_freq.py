"""分词、停用词过滤与词频聚合"""
from __future__ import annotations

from collections import Counter
import re
from typing import Iterable, Literal

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
    # Social media noise words
    "知道", "看到", "想到", "发现", "应该", "需要", "希望", "认为",
    "为什么", "怎么样", "越来越", "来说", "其实", "当然", "然后",
    "不过", "只是", "虽然", "但是", "而且", "或者", "任何", "所有",
    "今天", "昨天", "明天", "真的", "确实", "居然", "竟然", "难道",
    "已经", "正在", "开始", "最后", "之后", "之前", "以上", "以下",
    "起来", "下来", "过来", "出去", "回来", "到了", "不到", "到了",
}

# 允许的词性前缀：n=名词，v=动词，a=形容词
_ALLOWED_POS_PREFIXES: tuple[str, ...] = ("n", "v", "a")
_PHRASE_CONTENT_POS_PREFIXES: tuple[str, ...] = ("n", "v", "a")
_PHRASE_FUNCTION_POS_PREFIXES: tuple[str, ...] = ("d",)
_PHRASE_SINGLE_CHAR_KEEP: set[str] = {"不", "没", "无", "太", "很", "挺", "超"}
_PHRASE_BANNED_EDGE_TOKENS: set[str] = {"了", "的", "地", "得", "和", "与", "并", "都"}
_PHRASE_SPLIT_PATTERN = re.compile(r"[，,。！？!；;：:\(\)（）\[\]【】/|]+")


def load_stopwords() -> set[str]:
    """延迟加载停用词表，进程生命周期内复用"""
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


# 预热 jieba 词典，避免首次请求延迟
jieba.initialize()


def _extra_stopwords(keyword: str | None) -> set[str]:
    """根据查询关键词构建任务级排除词集"""
    if not keyword:
        return set()
    # Always exclude the full keyword regardless of length
    candidates = {keyword.strip().lower()}
    # Also exclude individual parts from splitting
    candidates.update(
        part.strip().lower()
        for part in re.split(r"[\s,，、/|:：_\-]+", keyword)
        if part.strip()
    )
    # Exclude jieba-segmented tokens (>= 2 chars to avoid single-letter noise)
    candidates.update(
        token.strip().lower()
        for token in jieba.cut(keyword)
        if token.strip() and len(token.strip()) >= 2
    )
    return {item for item in candidates if item}


def tokenize(text: str, *, extra_stopwords: set[str] | None = None) -> list[str]:
    """对文本分词，仅保留多字符的实义词"""
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


def _phrase_tokens(
    text: str,
    *,
    extra_stopwords: set[str] | None = None,
) -> list[tuple[str, str]]:
    """为短语提取进行分词，保留核心实词和单字修饰词"""
    stopwords = load_stopwords()
    extra_stopwords = extra_stopwords or set()
    tokens: list[tuple[str, str]] = []
    for word, flag in pseg.cut(text):
        word = word.strip()
        if not word or not flag:
            continue
        lowered = word.lower()
        if word in _PHRASE_SINGLE_CHAR_KEEP:
            tokens.append((word, flag))
            continue
        if len(word) < 2:
            continue
        if word in stopwords or lowered in stopwords:
            continue
        if word in extra_stopwords or lowered in extra_stopwords:
            continue
        if any(flag.startswith(prefix) for prefix in (_PHRASE_CONTENT_POS_PREFIXES + _PHRASE_FUNCTION_POS_PREFIXES)):
            tokens.append((word, flag))
    return tokens


def _is_content_token(word: str, flag: str) -> bool:
    return any(flag.startswith(prefix) for prefix in _PHRASE_CONTENT_POS_PREFIXES) and len(word) >= 2


def _valid_phrase(parts: list[tuple[str, str]]) -> bool:
    words = [word for word, _ in parts]
    if len(words) < 2:
        return False
    if words[0] in _PHRASE_BANNED_EDGE_TOKENS or words[-1] in _PHRASE_BANNED_EDGE_TOKENS:
        return False
    if not any(_is_content_token(word, flag) for word, flag in parts):
        return False
    content_count = sum(1 for word, flag in parts if _is_content_token(word, flag))
    if content_count < 2:
        return False
    if not any(
        any(flag.startswith(prefix) for prefix in ("a", "v"))
        or word in _PHRASE_SINGLE_CHAR_KEEP
        for word, flag in parts
    ):
        return False
    if all(flag.startswith("d") or word in _PHRASE_SINGLE_CHAR_KEEP for word, flag in parts):
        return False
    return True


def _phrase_candidates(
    text: str,
    *,
    extra_stopwords: set[str] | None = None,
) -> set[str]:
    phrases: set[str] = set()
    units = [unit.strip() for unit in _PHRASE_SPLIT_PATTERN.split(text) if unit.strip()]
    for unit in units or [text]:
        tokens = _phrase_tokens(unit, extra_stopwords=extra_stopwords)
        for size in (2, 3):
            if len(tokens) < size:
                continue
            for start in range(0, len(tokens) - size + 1):
                if (
                    start > 0
                    and tokens[start - 1][0] in {"不", "没", "无"}
                    and any(flag.startswith("v") for _, flag in tokens[start:start + size])
                ):
                    continue
                chunk = tokens[start:start + size]
                if not _valid_phrase(chunk):
                    continue
                phrases.add(" ".join(word for word, _ in chunk))
    if not phrases:
        # 句子太短无法形成短语时，回退到单个高频词
        for unit in units or [text]:
            for word, flag in _phrase_tokens(unit, extra_stopwords=extra_stopwords):
                if _is_content_token(word, flag):
                    phrases.add(word)
    return phrases


def phrase_frequencies(
    texts: Iterable[str],
    scores: Iterable[tuple[float, str]],
    top_n: int = 50,
    *,
    keyword: str | None = None,
    sentiment: Literal["positive", "negative"] | None = None,
) -> list[tuple[str, float]]:
    """从情感评分评论中计算加权观点短语"""
    counter: Counter[str] = Counter()
    extra_stopwords = _extra_stopwords(keyword)
    for text, (score, label) in zip(texts, scores):
        if sentiment and label != sentiment:
            continue
        phrases = _phrase_candidates(text, extra_stopwords=extra_stopwords)
        if not phrases:
            continue
        # 强烈观点应在短语云中更突出
        weight = 0.5 + abs(float(score) - 0.5) * 2.0
        for phrase in phrases:
            counter[phrase] += weight
    return [(phrase, round(weight, 3)) for phrase, weight in counter.most_common(top_n)]


def phrase_or_word_frequencies(
    texts: Iterable[str],
    scores: Iterable[tuple[float, str]],
    top_n: int = 50,
    *,
    keyword: str | None = None,
    sentiment: Literal["positive", "negative"] | None = None,
    min_phrases: int = 5,
) -> list[tuple[str, float]]:
    """计算短语频率，短语不足时回退到词频"""
    texts_list = list(texts)
    scores_list = list(scores)
    phrases = phrase_frequencies(
        texts_list, scores_list, top_n,
        keyword=keyword, sentiment=sentiment,
    )
    if len(phrases) >= min_phrases:
        return phrases
    # 回退：使用单字词频
    if sentiment:
        bucket = [t for t, (_, lbl) in zip(texts_list, scores_list) if lbl == sentiment]
    else:
        bucket = texts_list
    words = word_frequencies(bucket, top_n, keyword=keyword)
    return [(word, float(count)) for word, count in words]


def word_frequencies(
    texts: Iterable[str],
    top_n: int = 50,
    *,
    keyword: str | None = None,
    excluded_words: set[str] | None = None,
) -> list[tuple[str, int]]:
    """统计文本中最常见的前 N 个实义词"""
    counter: Counter[str] = Counter()
    extra_stopwords = _extra_stopwords(keyword)
    if excluded_words:
        extra_stopwords.update({word.lower() for word in excluded_words if word})
    for text in texts:
        counter.update(tokenize(text, extra_stopwords=extra_stopwords))
    return counter.most_common(top_n)
