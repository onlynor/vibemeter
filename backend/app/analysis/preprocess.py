"""Comment cleaning, normalization, and deduplication."""
from __future__ import annotations

import re
from typing import Iterable


# 去除标准 Unicode 表情符号，不会误伤中文字符
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
# 微博风格表情，如 [二哈] 或 [doge]
_WEIBO_EMOJI_PATTERN = re.compile(r"\[[^\[\]]{1,10}\]")
_REPLY_PREFIX_PATTERN = re.compile(r"^回复\s*[^:：]{0,30}[:：]\s*")

# 饭圈噪音过滤：短评论中含这些词的视为噪音
_FAN_CIRCLE_WORDS: set[str] = {
    "哥哥", "宝宝", "老公", "老婆", "姐姐", "妹妹", "弟弟",
    "哥哥好", "宝贝", "崽崽", "乖乖", "亲亲", "么么",
    "心动", "好帅", "好美", "好帅啊", "好美啊",
}

# 微博界面文字噪音
_WEIBO_UI_NOISE: list[re.Pattern] = [
    re.compile(r"展开全文[ac]?"),
    re.compile(r"收起$"),
    re.compile(r"查看最新(?:博智)?"),
    re.compile(r"转发微博"),
    re.compile(r"博智"),
]


def clean_comment(text: str) -> str:
    """去除评论中的噪音（链接、@、话题、表情、重复字符）"""
    if not text:
        return ""
    text = _REPLY_PREFIX_PATTERN.sub("", text)
    text = _URL_PATTERN.sub("", text)
    text = _MENTION_PATTERN.sub("", text)
    text = _HASHTAG_PATTERN.sub("", text)
    text = _WEIBO_EMOJI_PATTERN.sub("", text)
    text = _EMOJI_PATTERN.sub("", text)
    # 去除微博界面文字噪音
    for pattern in _WEIBO_UI_NOISE:
        text = pattern.sub("", text)
    text = _collapse_repeats(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_fan_circle_noise(text: str) -> bool:
    """判断是否为饭圈噪音评论（含饭圈关键词的短评论）"""
    if len(text) >= 10:
        return False
    return any(word in text for word in _FAN_CIRCLE_WORDS)


def _collapse_repeats(text: str) -> str:
    """将连续 3 个以上相同字符压缩为 1 个"""
    return re.sub(r"(.)\1{2,}", r"\1", text)


def is_meaningful(text: str) -> bool:
    """判断评论是否有效（至少包含 2 个中文或字母数字字符）"""
    if not text or len(text) < 2:
        return False
    significant = re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE)
    return len(significant) >= 2


def preprocess_comments(comments: Iterable[str]) -> list[str]:
    """批量清洗、去重、过滤原始评论"""
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
