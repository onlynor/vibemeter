"""Shared HTTP utilities for crawlers: User-Agent rotation + retry."""
from __future__ import annotations

import asyncio
import random
from typing import Any, Optional

import httpx

from app.config import DEFAULT_CRAWL_TIMEOUT


DESKTOP_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

MOBILE_UAS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36",
]


def pick_ua(mobile: bool = False) -> str:
    """Return a random User-Agent string."""
    return random.choice(MOBILE_UAS if mobile else DESKTOP_UAS)


def default_headers(*, mobile: bool = False, referer: str | None = None) -> dict[str, str]:
    """Return a header dict that mimics a real browser request."""
    headers = {
        "User-Agent": pick_ua(mobile=mobile),
        "Accept": "application/json, text/plain, text/html, */*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }
    if referer:
        headers["Referer"] = referer
    return headers


def make_client(*, mobile: bool = False, referer: str | None = None) -> httpx.AsyncClient:
    """Build an httpx.AsyncClient with sensible defaults for crawling."""
    return httpx.AsyncClient(
        follow_redirects=True,
        timeout=DEFAULT_CRAWL_TIMEOUT,
        headers=default_headers(mobile=mobile, referer=referer),
        http2=False,
    )


async def fetch_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
    retries: int = 3,
    base_delay: float = 0.6,
) -> Optional[Any]:
    """GET ``url`` and parse as JSON. Returns None on persistent failure.

    Implements exponential backoff with jitter; retries on 5xx / 429 /
    JSON-decode failures. Network-layer errors raise after the final try
    but are caught here so the caller can decide whether to fall back.
    """
    delay = base_delay
    for attempt in range(retries):
        try:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise httpx.HTTPStatusError(
                    "retryable status",
                    request=resp.request,
                    response=resp,
                )
            return resp.json()
        except (httpx.HTTPError, ValueError):
            if attempt == retries - 1:
                return None
            await asyncio.sleep(delay + random.uniform(0, delay * 0.5))
            delay *= 1.8
    return None


async def fetch_text(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
    retries: int = 3,
    base_delay: float = 0.6,
) -> Optional[str]:
    """Same as fetch_json but returns the raw response body as text."""
    delay = base_delay
    for attempt in range(retries):
        try:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise httpx.HTTPStatusError(
                    "retryable status",
                    request=resp.request,
                    response=resp,
                )
            if resp.status_code >= 400:
                return None
            return resp.text
        except httpx.HTTPError:
            if attempt == retries - 1:
                return None
            await asyncio.sleep(delay + random.uniform(0, delay * 0.5))
            delay *= 1.8
    return None


async def polite_sleep(low: float = 0.4, high: float = 1.1) -> None:
    """Random short sleep between requests."""
    await asyncio.sleep(random.uniform(low, high))
