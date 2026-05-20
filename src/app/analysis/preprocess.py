"""Comment cleaning, normalization, and deduplication."""
from __future__ import annotations

import re
from typing import Iterable


# Strip standard unicode emoji blocks. Each range is bounded so CJK ideographs
# (U+4E00–U+9FFF) and other useful BMP characters are *never* swallowed.
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001F5FF"  # Misc Symbols and Pictographs
    "\U0001F600-\U0001F64F"  # Emoticons
    "\U0001F680-\U0001F6FF"  # Transport and Map
    "\U0001F700-\U0001F77F"  # Alchemical
    "\U0001F780-\U0001F7FF"  # Geometric Shapes Ext
    "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
    "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
    "\U0001FA00-\U0001FA6F"  # Chess Symbols
    "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Ext-A
    "\U0001F1E6-\U0001F1FF"  # Regional Indicator (flags)
    "☀-⛿"           # Misc symbols ☀-⛿
    "✀-➿"           # Dingbats
    "️"                 # Variation selector-16
    "‍"                 # Zero-width joiner
    "]+",
    flags=re.UNICODE,
)

_URL_PATTERN = re.compile(r"https?://\S+|www\.\S+")
_MENTION_PATTERN = re.compile(r"@[^\s@:：，,。.！!？?]+")
_HASHTAG_PATTERN = re.compile(r"#[^#]+#")
# Weibo-style emoticons such as [二哈] or [doge].
_WEIBO_EMOJI_PATTERN = re.compile(r"\[[^\[\]]{1,10}\]")
_REPLY_PREFIX_PATTERN = re.compile(r"^回复\s*[^:：]{0,30}[:：]\s*")

# --- P0-1: Fan-circle noise filter ---
# Short comments (< 10 chars) containing these words are fan-circle noise.
_FAN_CIRCLE_WORDS: set[str] = {
    "哥哥", "宝宝", "老公", "老婆", "姐姐", "妹妹", "弟弟",
    "哥哥好", "宝贝", "崽崽", "乖乖", "亲亲", "么么",
    "心动", "好帅", "好美", "好帅啊", "好美啊",
}

# --- P0-2: Weibo UI text noise ---
_WEIBO_UI_NOISE: list[re.Pattern] = [
    re.compile(r"展开全文[ac]?"),
    re.compile(r"收起$"),
    re.compile(r"查看最新(?:博智)?"),
    re.compile(r"转发微博"),
    re.compile(r"博智"),
]


def clean_comment(text: str) -> str:
    """Strip noise (URLs, mentions, hashtags, emoji, repeats) from a comment."""
    if not text:
        return ""
    text = _REPLY_PREFIX_PATTERN.sub("", text)
    text = _URL_PATTERN.sub("", text)
    text = _MENTION_PATTERN.sub("", text)
    text = _HASHTAG_PATTERN.sub("", text)
    text = _WEIBO_EMOJI_PATTERN.sub("", text)
    text = _EMOJI_PATTERN.sub("", text)
    # P0-2: Remove Weibo UI text noise
    for pattern in _WEIBO_UI_NOISE:
        text = pattern.sub("", text)
    text = _collapse_repeats(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_fan_circle_noise(text: str) -> bool:
    """P0-1: Drop short fan-circle comments (< 10 chars with fan keywords)."""
    if len(text) >= 10:
        return False
    return any(word in text for word in _FAN_CIRCLE_WORDS)


def _collapse_repeats(text: str) -> str:
    """Collapse 3+ identical consecutive characters down to a single one."""
    return re.sub(r"(.)\1{2,}", r"\1", text)


def is_meaningful(text: str) -> bool:
    """A comment is meaningful when it has >= 2 word characters (CJK or alnum)."""
    if not text or len(text) < 2:
        return False
    significant = re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE)
    return len(significant) >= 2


def preprocess_comments(comments: Iterable[str]) -> list[str]:
    """Clean, deduplicate, and filter a batch of raw comments.

    Returns a list in original arrival order, with duplicates removed
    (first occurrence wins) and items shorter than two chars dropped.
    """
    seen: set[str] = set()
    out: list[str] = []
    for raw in comments:
        cleaned = clean_comment(raw)
        if not is_meaningful(cleaned):
            continue
        if _is_fan_circle_noise(cleaned):
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
    return out
