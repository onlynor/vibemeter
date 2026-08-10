"""provider 注册表与并发聚合

注册表用装饰器 + 包内自动发现：新增一个 provider 只需在 ``app/search/`` 下
放一个文件并给类加 ``@register_provider``，不需要改这里，也不需要改业务代码
（开闭原则）。
"""
from __future__ import annotations

import asyncio
import importlib
import logging
import pkgutil
import re
from typing import Iterable, Sequence
from urllib.parse import urlsplit

from app.search.base import PingResult, SearchProvider, SearchResult


logger = logging.getLogger(__name__)

# 单个 provider 的检索时限。超时只淘汰它自己，其余 provider 照常返回。
PROVIDER_TIMEOUT: float = 12.0
# 短于这个长度的归一化标题不参与去重，避免"官网""首页"之类误伤
TITLE_DEDUP_MIN_LEN: int = 8

_TITLE_NOISE_RE = re.compile(r"[\s\W_]+", re.UNICODE)

_REGISTRY: dict[str, type[SearchProvider]] = {}
_discovered = False


def register_provider(cls: type[SearchProvider]) -> type[SearchProvider]:
    """把 provider 登记进注册表（用作类装饰器）"""
    name = getattr(cls, "name", "")
    if not name or name == "base":
        raise ValueError(f"{cls.__name__} 必须定义唯一的 name")
    if name in _REGISTRY and _REGISTRY[name] is not cls:
        raise ValueError(f"重复注册的 search provider: {name!r}")
    _REGISTRY[name] = cls
    return cls


def _discover() -> None:
    """导入 app.search 包下的所有模块，触发装饰器注册"""
    global _discovered
    if _discovered:
        return
    _discovered = True
    package = importlib.import_module("app.search")
    for module in pkgutil.iter_modules(package.__path__):
        if module.name in {"base", "registry"} or module.name.startswith("_"):
            continue
        importlib.import_module(f"app.search.{module.name}")


def available_providers() -> list[str]:
    """已注册的 provider 名称"""
    _discover()
    return list(_REGISTRY)


def get_provider(name: str) -> SearchProvider:
    """按名称取得 provider 实例"""
    _discover()
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown search provider: {name!r}")
    return cls()


def _instantiate(names: Sequence[str] | None) -> list[SearchProvider]:
    _discover()
    wanted = list(names) if names is not None else list(_REGISTRY)
    providers: list[SearchProvider] = []
    for name in wanted:
        try:
            providers.append(get_provider(name))
        except Exception:
            logger.exception("search provider 实例化失败: %s", name)
    return providers


async def _run_one(
    provider: SearchProvider,
    query: str,
    limit: int,
) -> tuple[list[SearchResult], dict]:
    """跑单个 provider，任何失败都收敛成"该源不可用"，不向上抛"""
    status = {
        "provider": provider.name,
        "label": provider.label,
        "ok": False,
        "count": 0,
        "message": "",
    }
    try:
        results = await asyncio.wait_for(
            provider.search(query, limit=limit),
            timeout=PROVIDER_TIMEOUT,
        )
    except asyncio.TimeoutError:
        status["message"] = f"检索超时（{PROVIDER_TIMEOUT:.0f}s）"
        logger.warning("search provider %s 超时", provider.name)
        return [], status
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        status["message"] = f"检索失败：{exc}"
        logger.exception("search provider %s 失败", provider.name)
        return [], status

    status["ok"] = True
    status["count"] = len(results)
    status["message"] = f"返回 {len(results)} 条结果" if results else "未解析出结果"
    return results, status


def _url_key(url: str) -> str:
    """跨引擎比对用的 URL 归一化：忽略协议、www 前缀与结尾斜杠

    刻意保留 query：不少站点靠 ``?id=`` 区分文章，去掉就会把不同页面
    误判成同一条。
    """
    parts = urlsplit(url.lower())
    host = parts.netloc
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/")
    return f"{host}{path}?{parts.query}"


def _title_key(title: str) -> str:
    """标题归一化，用于识别同一篇稿件的多站转载"""
    return _TITLE_NOISE_RE.sub("", title).lower()


def _interleave(groups: Iterable[list[SearchResult]]) -> list[SearchResult]:
    """跨 provider 轮转合并并去重

    轮转的理由与聚合爬虫相同：直接按 provider 顺序拼接的话，下游一截断就只剩
    排在最前面那个引擎的结果。轮转后每个引擎的高位结果都能留在前面。

    去重是多引擎并联后才出现的问题：同一条新闻在百度和必应都排前列，不去重
    的话检索结果的前几条会成对重复，等于把 LLM 的背景资料预算浪费掉一半。
    URL 之外还比标题，因为同一篇稿件被多站转载时链接并不相同。
    """
    buckets = [list(g) for g in groups if g]
    merged: list[SearchResult] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    for depth in range(max((len(b) for b in buckets), default=0)):
        for bucket in buckets:
            if depth >= len(bucket):
                continue
            item = bucket[depth]
            url_key = _url_key(item.url)
            if url_key in seen_urls:
                continue
            title_key = _title_key(item.title)
            # 短标题太容易撞车（"首页"、"官网"），只对足够长的标题去重
            if len(title_key) >= TITLE_DEDUP_MIN_LEN and title_key in seen_titles:
                continue
            seen_urls.add(url_key)
            seen_titles.add(title_key)
            merged.append(item)
    return merged


async def search_all(
    query: str,
    *,
    limit: int = 10,
    providers: Sequence[str] | None = None,
    total_limit: int | None = None,
) -> tuple[list[SearchResult], list[dict]]:
    """并发跑全部（或指定的）provider，返回 (合并结果, 各源状态)

    ``limit`` 是**单个引擎**的取数上限，``total_limit`` 才是合并去重后的总量
    上限。两者分开是因为引擎越多、重复越多，若只按总量向每个引擎少要，
    去重之后反而凑不满。

    ``providers`` 为 None 表示跑全部；传空列表表示一个都不跑（用户关掉了
    检索增强），两者语义不同，不要合并。

    单个 provider 超时或抛异常都只影响它自己：它的状态被标成不可用，
    其余 provider 的结果照常返回。
    """
    query = (query or "").strip()
    instances = _instantiate(providers)
    if not query or not instances:
        return [], []

    pairs = await asyncio.gather(
        *(_run_one(p, query, limit) for p in instances)
    )
    merged = _interleave([results for results, _ in pairs])
    if total_limit is not None and total_limit >= 0:
        merged = merged[:total_limit]
    return merged, [status for _, status in pairs]


async def search_health() -> list[dict]:
    """探测各 provider 可用性，供前端"检测可用性"展示"""
    instances = _instantiate(None)

    async def probe(provider: SearchProvider) -> dict:
        try:
            ok, message = await asyncio.wait_for(
                provider.ping(), timeout=PROVIDER_TIMEOUT
            )
        except asyncio.TimeoutError:
            ok, message = False, f"探测超时（{PROVIDER_TIMEOUT:.0f}s）"
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            ok, message = False, f"探测失败：{exc}"
        return {
            "platform": provider.name,
            "label": provider.label,
            "kind": "search",
            "ok": ok,
            "message": message,
            "cookie_env": "",
            "cookie_required": False,
            "cookie_configured": False,
        }

    return list(await asyncio.gather(*(probe(p) for p in instances)))
