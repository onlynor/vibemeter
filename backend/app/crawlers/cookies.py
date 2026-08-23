"""数据源 Cookie 的统一读取入口

Cookie 只从环境变量（或启动时加载的 .env）读取，进程内使用、不落盘、
不写入数据库，重启即随环境变量变化，与 LLM 配置一致的"不留痕"口径。
"""
from __future__ import annotations

import os


# 平台 -> 环境变量名
COOKIE_ENV: dict[str, str] = {
    "weibo": "WEIBO_COOKIE",
    "bilibili": "BILIBILI_COOKIE",
    "douban": "DOUBAN_COOKIE",
    "zhihu": "ZHIHU_COOKIE",
    "tieba": "TIEBA_COOKIE",
}


def cookie_env_name(platform: str) -> str:
    """返回该平台对应的环境变量名，未定义则返回空串"""
    return COOKIE_ENV.get(platform, "")


def get_cookie(platform: str) -> str:
    """读取该平台的 Cookie，未配置或格式不合法返回空串

    格式不合法的值（见 ``cookie_issue``）直接当成未配置，避免把
    无法编码成 HTTP 头的字符串塞进请求里抛 UnicodeEncodeError ——
    那个异常是 ValueError 的子类，会被 fetch_json 静默吞成"无返回"，
    最后误报成"Cookie 过期"，把人引向错误的方向。
    """
    value = _raw_cookie(platform)
    return "" if _encode_issue(value) else value


def cookie_configured(platform: str) -> bool:
    """该平台是否已配置可用的 Cookie"""
    return bool(get_cookie(platform))


def cookie_issue(platform: str) -> str:
    """返回该平台 Cookie 的格式问题描述，没问题返回空串"""
    return _encode_issue(_raw_cookie(platform))


def _raw_cookie(platform: str) -> str:
    """读取环境变量原始值，不做校验"""
    env_name = COOKIE_ENV.get(platform)
    if not env_name:
        return ""
    return os.environ.get(env_name, "").strip()


def _encode_issue(value: str) -> str:
    """检查 Cookie 能否作为 HTTP 头发送"""
    if not value:
        return ""
    try:
        value.encode("latin-1")
    except UnicodeEncodeError:
        illegal = "".join(sorted({ch for ch in value if ord(ch) > 255}))
        return (
            f"Cookie 含非法字符 {illegal!r}，无法作为请求头发送。"
            "多半是从开发者工具里复制到了被省略号截断的显示值，"
            "请改用右键 Copy value，或在控制台执行 document.cookie 重新复制完整值"
        )
    return ""
