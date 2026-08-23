"""应用配置与运行时常量"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from matplotlib import font_manager


BASE_DIR: Path = Path(__file__).resolve().parent.parent


# 运行时只保留一个数据目录，里面仅放 SQLite 与词典等静态资源；
# 原始/清洗/分析结果一律留在 SQLite，不再单独落盘半结构化文件。
DATA_DIR: Path = BASE_DIR / "data"
FONTS_DIR: Path = BASE_DIR / "fonts"

DB_PATH: Path = DATA_DIR / "sentiment.db"
STOPWORDS_PATH: Path = DATA_DIR / "stopwords.txt"
HOTSPOTS_CACHE_SECONDS: int = 300

# 情感阈值（SnowNLP 分数范围 [0, 1]）
SENTIMENT_POSITIVE_THRESHOLD: float = 0.6
SENTIMENT_NEGATIVE_THRESHOLD: float = 0.4

# 结果数量限制
MAX_REPRESENTATIVE_COMMENTS: int = 3
TOP_WORDS_LIMIT: int = 50
TOP_WORDS_GLOBAL: int = 15

# 爬虫配置
DEFAULT_CRAWL_TIMEOUT: int = 15


def _env_float(name: str, default: float) -> float:
    """读环境变量里的浮点值，缺失或非法一律退回默认值"""
    try:
        return float(os.environ[name])
    except (KeyError, TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# 检索与采集的调优参数
#
# 这些值原先散落在 auto.py / registry.py / manager.py 里，各自写死。集中到这里
# 有两个好处：一是"这次跑得慢是哪个时限卡住的"只需看一个文件；二是全部支持
# 环境变量覆盖，换网络环境（家宽 / 机房 / 容器）时不必改代码重新构建。
#
# 名字都以 VIBE_ 开头，避免和系统里同名变量撞车。
# ---------------------------------------------------------------------------

# --- 检索增强（app/search）---
# 单个 provider 的检索时限，超时只淘汰它自己
SEARCH_PROVIDER_TIMEOUT: float = _env_float("VIBE_SEARCH_TIMEOUT", 12.0)
# 百度预热（拿 BAIDUID）的时限。必须远小于上面的检索时限：预热只是为了拿
# 一个 Cookie，卡在这一步等于整次检索白等
SEARCH_WARMUP_TIMEOUT: float = _env_float("VIBE_SEARCH_WARMUP_TIMEOUT", 6.0)
# 预热拿到的 Cookie 复用多久。每次检索都重新预热等于凭空多一个串行往返
SEARCH_COOKIE_TTL: float = _env_float("VIBE_SEARCH_COOKIE_TTL", 900.0)
# 单个引擎取多少条
SEARCH_RESULT_LIMIT: int = _env_int("VIBE_SEARCH_LIMIT", 8)
# 跨引擎合并去重后保留多少条作为 LLM 背景资料。比 limit×引擎数 小得多是有意的：
# 背景资料只用来交代"这件事是什么"，条数再多也只是挤占上下文预算
SEARCH_TOTAL_LIMIT: int = _env_int("VIBE_SEARCH_TOTAL_LIMIT", 12)
# 短于这个长度的归一化标题不参与去重，避免"官网""首页"之类误伤
SEARCH_TITLE_DEDUP_MIN_LEN: int = _env_int("VIBE_SEARCH_TITLE_DEDUP_MIN_LEN", 8)
# 向引擎多要几条：广告与非结果容器会在解析阶段被剔掉，只要 limit 条会不够
SEARCH_OVERFETCH: int = _env_int("VIBE_SEARCH_OVERFETCH", 10)

# --- 聚合采集（app/crawlers）---
# 单源首批数据的宽限期，用于快速识别"这个源今天不可用"
CRAWL_FIRST_BATCH_TIMEOUT: float = _env_float("VIBE_CRAWL_FIRST_BATCH_TIMEOUT", 8.0)
# 单源总时限，防止分页阶段无限拖
CRAWL_SOURCE_DEADLINE: float = _env_float("VIBE_CRAWL_SOURCE_DEADLINE", 60.0)
# 轮转合并后每次向前端推送的条数
CRAWL_EMIT_CHUNK: int = _env_int("VIBE_CRAWL_EMIT_CHUNK", 40)
# 可用性探测的时限（比检索宽松：探测本身就是在等风控回应）
CRAWL_PING_TIMEOUT: float = _env_float("VIBE_CRAWL_PING_TIMEOUT", 25.0)

# --- 任务流水线（app/tasks）---
# 低于这个条数就在结果里提示样本偏少
MIN_REQUIRED_COMMENTS: int = _env_int("VIBE_MIN_REQUIRED_COMMENTS", 300)
# 只保留最近多少个任务（更早的连同 comments/results 一起删）
MAX_HISTORY_TASKS: int = _env_int("VIBE_MAX_HISTORY_TASKS", 10)

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
    """创建运行时所需的目录（仅 SQLite 与词典所在的 data 目录）"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
