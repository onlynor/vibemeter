"""HTML page routes for the classic server-rendered UI."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parents[2] / "frontend" / "templates")
)
_STATIC_DIR = Path(__file__).resolve().parents[2] / "frontend" / "static"


def _asset_version(relative_path: str) -> str:
    """Use file mtime as a lightweight cache-busting token for static assets."""
    try:
        return str(int((_STATIC_DIR / relative_path).stat().st_mtime))
    except OSError:
        return "0"


@router.get("/", response_class=HTMLResponse)
async def index_page(request: Request):
    """Render the homepage form and hotspot panel."""
    return templates.TemplateResponse(
        request,
        "index.html",
        {"request": request},
    )


@router.get("/result/{task_id}", response_class=HTMLResponse)
async def result_page(request: Request, task_id: str):
    """Render the dashboard page shell for one task."""
    return templates.TemplateResponse(
        request,
        "result.html",
        {
            "request": request,
            "task_id": task_id,
            "dashboard_js_v": _asset_version("js/dashboard.js"),
            "result_chat_js_v": _asset_version("js/result_chat.js"),
        },
    )
