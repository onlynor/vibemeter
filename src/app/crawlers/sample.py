"""已禁用的合成数据回退，本项目仅使用真实爬取数据"""
from __future__ import annotations


def generate_sample(keyword: str, count: int, *, seed: int | None = None) -> list[str]:
    """始终抛出异常，合成数据回退已被禁用"""
    raise RuntimeError(
        "示例数据兜底已被关闭：本项目要求只使用真实爬取的数据。"
        f"（关键词={keyword!r}，请求数={count}）"
    )
