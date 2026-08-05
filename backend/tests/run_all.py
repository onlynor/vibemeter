"""跑完 tests/ 下的全部测试。

    backend/.venv/bin/python tests/run_all.py

这些测试是自包含的脚本（项目没有引入 pytest），逐个子进程执行，
任何一个非零退出即整体失败。除 test_sources 外都不依赖网络。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


TESTS = [
    "test_search.py",          # 检索层：解析 / 模型 / 注册 / 聚合 / 跨源去重
    "test_preprocess.py",      # 评论清洗：标记剥离、近似去重、广告过滤
    "test_auto.py",            # 聚合爬虫：均衡、去重、超时、子集、取消
    "test_sources.py",         # 豆瓣 / 贴吧 抓取流程
    "test_pipeline.py",        # TaskManager 全链路
    "test_search_pipeline.py", # 检索结果接入 summary 与 LLM 上下文
]


def main() -> int:
    here = Path(__file__).resolve().parent
    failed: list[str] = []
    for name in TESTS:
        print(f"\n{'=' * 60}\n{name}\n{'=' * 60}")
        proc = subprocess.run([sys.executable, str(here / name)])
        if proc.returncode != 0:
            failed.append(name)
    print(f"\n{'=' * 60}")
    if failed:
        print("FAILED: " + ", ".join(failed))
        return 1
    print(f"ALL {len(TESTS)} TEST MODULES PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
