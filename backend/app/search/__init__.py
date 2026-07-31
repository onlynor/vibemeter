"""搜索引擎检索层

对外只暴露注册表与聚合入口；具体 provider 由 ``registry`` 自动发现。
"""
from app.search.base import (
    PingResult,
    ResultSpec,
    SearchProvider,
    SearchResult,
    parse_results,
)
from app.search.registry import (
    PROVIDER_TIMEOUT,
    available_providers,
    get_provider,
    register_provider,
    search_all,
    search_health,
)


__all__ = [
    "PingResult",
    "PROVIDER_TIMEOUT",
    "ResultSpec",
    "SearchProvider",
    "SearchResult",
    "available_providers",
    "get_provider",
    "parse_results",
    "register_provider",
    "search_all",
    "search_health",
]
