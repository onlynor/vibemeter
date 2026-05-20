"""FastAPI application entrypoint."""
from __future__ import annotations

import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import CLEANED_DIR, DB_PATH, RAW_DIR, ensure_directories
from app.database import init_db
from app.routers import api, pages, ws
from app.tasks.manager import EXPORTS_DIR


def _purge_previous_runs() -> None:
    """Drop the SQLite DB + exports/ so each launch starts from a clean slate.

    The user wants task history to never survive a process restart, so we
    blow the on-disk state away before ``init_db`` recreates the schema.
    Anything still in-flight in memory is also gone (the OS just killed
    the old process), so nothing to coordinate.
    """
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
            # File may be held open by another process — skip silently.
            pass

    if EXPORTS_DIR.exists():
        shutil.rmtree(EXPORTS_DIR, ignore_errors=True)
    # raw/ and cleaned/ are part of "each run starts clean" too — old runs
    # left behind here would just confuse later submissions.
    if RAW_DIR.exists():
        shutil.rmtree(RAW_DIR, ignore_errors=True)
    if CLEANED_DIR.exists():
        shutil.rmtree(CLEANED_DIR, ignore_errors=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise the on-disk state before serving the first request."""
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
