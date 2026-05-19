"""Probe each registered crawler with a fixed keyword and report results.

Run from the repo root:

    cd src
    python -m scripts.smoke_crawlers 流浪地球3
    # or
    python -m scripts.smoke_crawlers 流浪地球3 --platforms tieba bilibili

This bypasses the FastAPI app entirely, so you can see exactly which
endpoints return data right now without going through the dashboard.
"""
from __future__ import annotations

import argparse
import asyncio
import io
import sys
from typing import Iterable

# Force UTF-8 stdout so Chinese prints correctly on Windows cmd
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app.crawlers import SUPPORTED_PLATFORMS, get_crawler


async def _noop_progress(current: int, message: str = "") -> None:
    if message:
        print(f"    · {message}")


async def probe_one(platform: str, keyword: str, target: int) -> dict:
    """Run a single crawler and return a small result summary."""
    crawler = get_crawler(platform)
    collected: list[str] = []
    error: str | None = None
    try:
        async for batch in crawler.fetch(keyword, target, _noop_progress):
            collected.extend(batch)
            if len(collected) >= target:
                break
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    return {
        "platform": platform,
        "count": len(collected),
        "samples": collected[:3],
        "error": error,
    }


async def main(keyword: str, target: int, platforms: Iterable[str]) -> None:
    print(f"keyword = {keyword!r}, target = {target}")
    print(f"probing: {', '.join(platforms)}\n")
    for plat in platforms:
        print(f"=== {plat} ===")
        report = await probe_one(plat, keyword, target)
        if report["error"]:
            print(f"  FAILED  →  {report['error']}")
        else:
            print(f"  OK      →  {report['count']} comments")
        for idx, sample in enumerate(report["samples"], 1):
            preview = sample.replace("\n", " ")[:120]
            print(f"  [{idx}] {preview}")
        print()


def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("keyword", help="Search keyword to probe each crawler with")
    parser.add_argument(
        "--target", type=int, default=30,
        help="Target comment count per platform (default 30, low for a smoke test)",
    )
    parser.add_argument(
        "--platforms", nargs="*", default=None,
        help=f"Subset of platforms to probe. Default: {SUPPORTED_PLATFORMS}",
    )
    args = parser.parse_args()
    chosen = args.platforms or SUPPORTED_PLATFORMS
    unknown = [p for p in chosen if p not in SUPPORTED_PLATFORMS]
    if unknown:
        parser.error(f"unknown platform(s): {unknown}; choices={SUPPORTED_PLATFORMS}")
    asyncio.run(main(args.keyword, args.target, chosen))


if __name__ == "__main__":
    _cli()
