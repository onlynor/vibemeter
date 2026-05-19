"""In-memory store for the active LLM connection config.

Lives only inside the process — no disk, no env, no cookies. When the
server stops the api key is gone with it. Cleared on first startup so a
restart always begins blank.

Keys mirror the form field ids on the frontend so the JSON can be
round-tripped without translation:
    llm_base_url, llm_api_key, llm_model, llm_question, llm_context_format
"""
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


def get_config() -> Dict[str, str]:
    """Return a shallow copy of the current config."""
    with _lock:
        return dict(_config)


def update_config(values: Dict[str, str]) -> Dict[str, str]:
    """Replace stored values with the allowed keys from ``values``.

    Unknown keys are silently dropped. Each value is coerced to a stripped
    string and capped at ``_MAX_VALUE_LEN`` to defend against accidentally
    sending a massive payload.
    """
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
