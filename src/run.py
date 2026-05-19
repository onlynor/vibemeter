"""Local development entrypoint.

Run from anywhere — this script adds ``src/`` to ``sys.path`` so the
``app`` package always resolves, regardless of the caller's cwd.
"""
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import uvicorn  # noqa: E402  (must run after sys.path tweak)


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8092,
        reload=True,
        reload_dirs=[str(SRC_DIR)],
        log_level="info",
    )
