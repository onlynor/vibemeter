"""本地开发入口，自动将 src 目录加入 sys.path"""
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8092,
        reload=True,
        reload_dirs=[str(SRC_DIR)],
        log_level="info",
    )
