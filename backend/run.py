"""本地开发入口，自动将 backend 目录加入 sys.path。

在项目根目录用 uv 运行：
    uv run --directory backend python run.py
或在 backend 目录内：
    uv run python run.py
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8092,
        reload=True,
        reload_dirs=[str(BACKEND_DIR)],
        log_level="info",
    )