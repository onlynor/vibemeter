"""HTML page routes for the classic server-rendered UI."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parents[2] / "templates")
)


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
        {"request": request, "task_id": task_id},
    )
