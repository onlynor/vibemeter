"""应用配置与运行时常量"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from matplotlib import font_manager


BASE_DIR: Path = Path(__file__).resolve().parent.parent


DATA_DIR: Path = BASE_DIR / "data"
FONTS_DIR: Path = BASE_DIR / "fonts"
# 原始爬取评论（每个任务一个文件，csv + json 格式）
RAW_DIR: Path = DATA_DIR / "raw"
CLEANED_DIR: Path = DATA_DIR / "cleaned"
OUTPUT_DIR: Path = DATA_DIR / "output"

DB_PATH: Path = DATA_DIR / "sentiment.db"
STOPWORDS_PATH: Path = DATA_DIR / "stopwords.txt"
USER_DICT_PATH: Path = DATA_DIR / "user_dict.txt"
HOTSPOTS_CACHE_SECONDS: int = 300

# 情感阈值（SnowNLP 分数范围 [0, 1]）
SENTIMENT_POSITIVE_THRESHOLD: float = 0.6
SENTIMENT_NEGATIVE_THRESHOLD: float = 0.4

# 结果数量限制
MAX_REPRESENTATIVE_COMMENTS: int = 3
TOP_WORDS_LIMIT: int = 50
TOP_WORDS_GLOBAL: int = 15
HOTWORDS_HEATMAP_LIMIT: int = 10

# 爬虫配置
DEFAULT_CRAWL_TIMEOUT: int = 15
MAX_CRAWL_PAGES: int = 30

# 词云渲染字体候选列表（按优先级排列）
FONT_CANDIDATES: list[str] = [
    str(FONTS_DIR / "SimHei.ttf"),
    str(FONTS_DIR / "simhei.ttf"),
    str(FONTS_DIR / "wqy-zenhei.ttc"),
    str(FONTS_DIR / "NotoSansCJK-Regular.ttc"),
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
]


def get_font_path() -> Optional[str]:
    """返回第一个可用的中文字体路径，无可用则返回 None"""
    env_path = os.environ.get("SENTIMENT_FONT_PATH")
    if env_path and Path(env_path).exists():
        return env_path
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    for candidate in font_manager.findSystemFonts():
        name = Path(candidate).name.lower()
        if any(token in name for token in ("simhei", "msyh", "noto", "pingfang", "heiti", "wqy", "sourcehansans")):
            return candidate
    return None


def ensure_directories() -> None:
    """创建运行时所需的目录"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CLEANED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
