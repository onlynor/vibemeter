"""Application configuration and runtime constants."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from matplotlib import font_manager


BASE_DIR: Path = Path(__file__).resolve().parent.parent


DATA_DIR: Path = BASE_DIR / "data"
FONTS_DIR: Path = BASE_DIR / "fonts"
# Raw crawled comments (one file per task, as csv + json) — required by the
# project rubric ("数据文件夹：爬取到的原始数据、清洗后的数据").
RAW_DIR: Path = DATA_DIR / "raw"
CLEANED_DIR: Path = DATA_DIR / "cleaned"

DB_PATH: Path = DATA_DIR / "sentiment.db"
STOPWORDS_PATH: Path = DATA_DIR / "stopwords.txt"
USER_DICT_PATH: Path = DATA_DIR / "user_dict.txt"
HOTSPOTS_CACHE_SECONDS: int = 300

# Sentiment thresholds (SnowNLP score is in [0, 1]).
SENTIMENT_POSITIVE_THRESHOLD: float = 0.6
SENTIMENT_NEGATIVE_THRESHOLD: float = 0.4

# Result limits
MAX_REPRESENTATIVE_COMMENTS: int = 3
TOP_WORDS_LIMIT: int = 50
TOP_WORDS_GLOBAL: int = 15
HOTWORDS_HEATMAP_LIMIT: int = 10

# Crawler tunables
DEFAULT_CRAWL_TIMEOUT: int = 15
MAX_CRAWL_PAGES: int = 30

# Font candidates searched in priority order for wordcloud rendering.
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
    """Return the first available Chinese font path, or None."""
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
    """Create runtime directories if they don't exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CLEANED_DIR.mkdir(parents=True, exist_ok=True)
