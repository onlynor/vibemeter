"""FastAPI application entrypoint.

后端只负责提供 API + WebSocket，不再 serve 前端静态文件。
前端是独立的 Vite / Nginx 服务，通过 HTTP 调用 /api、/ws。
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from app.config import DB_PATH, ensure_directories
from app.database import init_db
from app.routers import api, ws


def _purge_previous_runs() -> None:
    """删除旧的 SQLite 数据库，确保每次启动都从干净状态开始"""
    for path in (
        DB_PATH,
        DB_PATH.with_suffix(DB_PATH.suffix + "-journal"),
        DB_PATH.with_suffix(DB_PATH.suffix + "-wal"),
        DB_PATH.with_suffix(DB_PATH.suffix + "-shm"),
    ):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理，启动时初始化磁盘状态"""
    ensure_directories()
    _purge_previous_runs()
    await init_db()
    yield


app = FastAPI(
    title="舆情洞察员",
    description="微博/B站评论情感分析平台 API",
    version="0.1.0",
    lifespan=lifespan,
)

# 前后端分离：允许前端开发服务器（:5173）与生产部署域名访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api.router)
app.include_router(ws.router)