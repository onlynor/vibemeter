"""FastAPI application entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import DB_PATH, ensure_directories
from app.database import init_db
from app.routers import api, pages, ws


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
    description="微博/B站评论情感分析平台",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = Path(__file__).resolve().parent.parent / "frontend" / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

app.include_router(pages.router)
app.include_router(api.router)
app.include_router(ws.router)
