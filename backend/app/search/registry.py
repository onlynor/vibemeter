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
from typing import Iterable, Sequence

from app.search.base import PingResult, SearchProvider, SearchResult


logger = logging.getLogger(__name__)

# 单个 provider 的检索时限。超时只淘汰它自己，其余 provider 照常返回。
PROVIDER_TIMEOUT: float = 12.0

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


def _interleave(groups: Iterable[list[SearchResult]]) -> list[SearchResult]:
    """跨 provider 轮转合并

    与聚合爬虫同样的理由：直接按 provider 顺序拼接的话，下游一截断就只剩
    排在最前面那个引擎的结果。轮转后每个引擎的高位结果都能留在前面。
    """
    buckets = [list(g) for g in groups if g]
    merged: list[SearchResult] = []
    for depth in range(max((len(b) for b in buckets), default=0)):
        for bucket in buckets:
            if depth < len(bucket):
                merged.append(bucket[depth])
    return merged


async def search_all(
    query: str,
    *,
    limit: int = 10,
    providers: Sequence[str] | None = None,
) -> tuple[list[SearchResult], list[dict]]:
    """并发跑全部（或指定的）provider，返回 (合并结果, 各源状态)

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
