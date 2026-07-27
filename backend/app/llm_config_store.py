"""LLM 连接配置的内存存储，进程退出即清空"""
from __future__ import annotations

import threading
from typing import Dict

_ALLOWED_KEYS = {
    "llm_base_url",
    "llm_api_key",
    "llm_model",
    "llm_question",
    "llm_context_format",
}
_MAX_VALUE_LEN = 512

_lock = threading.Lock()
_config: Dict[str, str] = {key: "" for key in _ALLOWED_KEYS}
_config["llm_context_format"] = "xml"


def get_config() -> Dict[str, str]:
    """返回当前配置的浅拷贝"""
    with _lock:
        return dict(_config)


def update_config(values: Dict[str, str]) -> Dict[str, str]:
    """用允许的键值更新配置，未知键会被忽略"""
    with _lock:
        for key in _ALLOWED_KEYS:
            if key in values:
                raw = values.get(key)
                text = "" if raw is None else str(raw).strip()
                if len(text) > _MAX_VALUE_LEN:
                    text = text[:_MAX_VALUE_LEN]
                _config[key] = text
        return dict(_config)


def clear_config() -> None:
    with _lock:
        for key in _ALLOWED_KEYS:
            _config[key] = ""
