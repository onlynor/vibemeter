"""REST API routes serving the dashboard's data calls."""
from __future__ import annotations

import asyncio
import base64
import io
import json
from pathlib import Path

import aiosqlite
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from wordcloud import WordCloud

from app.config import DB_PATH, TOP_WORDS_GLOBAL, get_font_path
from app.hotspots import hotspot_service
from app.llm_config_store import get_config as get_llm_config, update_config as update_llm_config
from app.schemas import LLMChatRequest, LLMConfigPayload, LLMTestRequest, TaskRequest
from app.tasks.manager import EXPORTS_DIR
from app.tasks.manager import task_manager
from app.analysis.llm_insight import (
    build_context,
    chat_with_context,
    chat_with_context_stream,
    ping_llm,
)


router = APIRouter(prefix="/api")


def _ok(data) -> dict:
    return {"code": 0, "data": data}


def _err(msg: str) -> dict:
    return {"code": 1, "msg": msg}


# -- internals ------------------------------------------------------------

async def _load_field(task_id: str, field: str):
    """Read one JSON column from the results table for a task."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"SELECT {field} FROM results WHERE task_id = ?",
            (task_id,),
        )
        row = await cursor.fetchone()
    if not row or not row[0]:
        return None
    return json.loads(row[0])


def _render_wordcloud(words: list[tuple[str, float]], *, palette: str) -> str:
    """Render a compact phrase cloud PNG and return it as base64."""
    if not words:
        return ""
    font_path = get_font_path()
    if not font_path:
        raise RuntimeError("未找到可用中文字体，无法生成词云")
    cloud = WordCloud(
        font_path=font_path,
        width=1200,
        height=520,
        background_color="white",
        max_words=80,
        margin=10,
        prefer_horizontal=1.0,
        relative_scaling=0.35,
        min_font_size=12,
        collocations=False,
        colormap=palette,
    )
    image = cloud.generate_from_frequencies(dict(words)).to_image()
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")

# -- endpoints ------------------------------------------------------------

@router.get("/task/{task_id}/status")
async def task_status(task_id: str):
    """Return the lifecycle metadata for one task."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM tasks WHERE task_id = ?",
            (task_id,),
        )
        row = await cursor.fetchone()
    if not row:
        return _err("任务不存在")
    return _ok(dict(row))


@router.get("/tasks/history")
async def task_history():
    """Return the latest stored tasks in newest-first order."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT task_no, task_id, keyword, platform, status,
                      total_count, start_time, end_time, error
               FROM tasks
               ORDER BY task_no DESC
               LIMIT 10"""
        )
        rows = await cursor.fetchall()
    items = []
    for row in rows:
        record = dict(row)
        record["display_no"] = f"#{int(record['task_no']):04d}" if record.get("task_no") else "-"
        record["url"] = f"/result/{record['task_id']}"
        items.append(record)
    return _ok(items)


@router.post("/task")
async def create_task(payload: TaskRequest):
    """Create one analysis task from the classic HTML page."""
    task_id = await task_manager.create_task(
        payload.keyword,
        payload.platform,
        payload.count,
        llm_base_url=payload.llm_base_url,
        llm_api_key=payload.llm_api_key,
        llm_model=payload.llm_model,
        llm_question=payload.llm_question,
        llm_context_format=payload.llm_context_format,
    )
    return _ok({"task_id": task_id})


@router.get("/hotspots")
async def get_hotspots():
    """Return merged homepage hotspots from the live providers."""
    try:
        items = await hotspot_service.get_hotspots()
    except Exception as exc:
        return _err(f"热搜获取失败: {exc}")
    return _ok(items)


@router.get("/result/{task_id}/summary")
async def get_summary(task_id: str):
    summary = await _load_field(task_id, "summary_json")
    if summary is None:
        return _err("结果不存在或尚未完成")
    return _ok(summary)


@router.get("/result/{task_id}/xml-context")
async def get_xml_context(task_id: str):
    """Return the XML-formatted context that would be fed to the LLM.

    Useful as a display panel on the dashboard so the user can see — and
    copy — the structured prompt context generated from the analysis.
    """
    summary = await _load_field(task_id, "summary_json")
    if summary is None:
        return _err("结果不存在或尚未完成")
    return _ok({"xml": build_context(summary, "xml")})


@router.get("/result/{task_id}/sentiment-pie")
async def get_sentiment_pie(task_id: str):
    summary = await _load_field(task_id, "summary_json")
    if summary is None:
        return _err("结果不存在或尚未完成")
    return _ok([
        {"name": "正向", "value": summary["positive"]},
        {"name": "中立", "value": summary["neutral"]},
        {"name": "负向", "value": summary["negative"]},
    ])


@router.get("/result/{task_id}/top-words")
async def get_top_words(task_id: str):
    words = await _load_field(task_id, "all_words_json")
    if words is None:
        return _err("结果不存在或尚未完成")
    return _ok([
        {"name": word, "value": count}
        for word, count in words[:TOP_WORDS_GLOBAL]
    ])


@router.get("/result/{task_id}/wordcloud/positive")
async def get_positive_wordcloud(task_id: str):
    words = await _load_field(task_id, "positive_words_json")
    if words is None:
        return _err("结果不存在或尚未完成")
    if not words:
        return _err("无足够正向评论生成观点短语云")
    loop = asyncio.get_running_loop()
    try:
        image = await loop.run_in_executor(
            None,
            lambda: _render_wordcloud(words, palette="Greens"),
        )
    except Exception as exc:
        return _err(f"正向观点短语云生成失败: {exc}")
    return _ok({"image": image})


@router.get("/result/{task_id}/wordcloud/negative")
async def get_negative_wordcloud(task_id: str):
    words = await _load_field(task_id, "negative_words_json")
    if words is None:
        return _err("结果不存在或尚未完成")
    if not words:
        return _err("无足够负向评论生成观点短语云")
    loop = asyncio.get_running_loop()
    try:
        image = await loop.run_in_executor(
            None,
            lambda: _render_wordcloud(words, palette="Reds"),
        )
    except Exception as exc:
        return _err(f"负向观点短语云生成失败: {exc}")
    return _ok({"image": image})


@router.get("/result/{task_id}/export/{kind}")
async def download_export(task_id: str, kind: str):
    """Stream a previously written export artefact back to the client.

    ``kind`` is one of: raw, cleaned, analysed, summary.
    """
    allowed = {"raw", "cleaned", "analysed", "summary"}
    if kind not in allowed:
        raise HTTPException(status_code=400, detail="invalid kind")
    path = EXPORTS_DIR / f"{task_id}_{kind}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="export not found")
    return FileResponse(
        path=str(path),
        media_type="application/json",
        filename=path.name,
    )


@router.get("/result/{task_id}/exports")
async def list_exports(task_id: str):
    """List which export artefacts are available for download."""
    available = []
    for kind in ("raw", "cleaned", "analysed", "summary"):
        candidate = Path(EXPORTS_DIR) / f"{task_id}_{kind}.json"
        if candidate.exists():
            available.append({
                "kind": kind,
                "url": f"/api/result/{task_id}/export/{kind}",
                "size": candidate.stat().st_size,
            })
    return _ok(available)


@router.get("/llm/config")
async def read_llm_config():
    """Return the LLM config currently held in process memory.

    Empty strings when nothing has been entered yet (e.g. fresh process).
    Cleared whenever the server restarts, so this is never persisted.
    """
    return _ok(get_llm_config())


@router.post("/llm/config")
async def write_llm_config(payload: LLMConfigPayload):
    """Replace the in-memory LLM config with the submitted values."""
    updated = update_llm_config(payload.model_dump())
    return _ok(updated)


@router.post("/llm/test")
async def test_llm(payload: LLMTestRequest):
    """Verify the LLM endpoint with a single tiny chat completion call."""
    ok, message = await ping_llm(payload.base_url, payload.api_key, payload.model)
    if not ok:
        return _err(message)
    return _ok({"message": message})


@router.post("/result/{task_id}/llm-chat")
async def llm_chat(task_id: str, payload: LLMChatRequest):
    """Free-form follow-up chat anchored on this task's analysis context."""
    summary = await _load_field(task_id, "summary_json")
    if summary is None:
        return _err("结果不存在或尚未完成，无法进入对话")
    try:
        result = await chat_with_context(
            base_url=payload.base_url,
            api_key=payload.api_key,
            model=payload.model,
            question=payload.question,
            summary=summary,
            context_format=payload.context_format,
            history=payload.history or [],
        )
    except ValueError as exc:
        return _err(str(exc))
    except Exception as exc:  # network / HTTP / parsing
        return _err(f"LLM 调用失败：{exc}")
    return _ok(result)


@router.post("/result/{task_id}/llm-chat-stream")
async def llm_chat_stream(task_id: str, payload: LLMChatRequest):
    """SSE-streamed version of llm_chat — yields content deltas as they arrive.

    Frames:
      data: {"delta": "..."}   incremental text
      data: {"done": true}     normal completion
      data: {"error": "..."}   any upstream / setup error
    """
    summary = await _load_field(task_id, "summary_json")

    async def event_source():
        if summary is None:
            yield 'data: {"error": "结果不存在或尚未完成，无法进入对话"}\n\n'
            return
        try:
            async for delta in chat_with_context_stream(
                base_url=payload.base_url,
                api_key=payload.api_key,
                model=payload.model,
                question=payload.question,
                summary=summary,
                context_format=payload.context_format,
                history=payload.history or [],
            ):
                yield "data: " + json.dumps({"delta": delta}, ensure_ascii=False) + "\n\n"
            yield 'data: {"done": true}\n\n'
        except ValueError as exc:
            yield "data: " + json.dumps({"error": str(exc)}, ensure_ascii=False) + "\n\n"
        except Exception as exc:
            yield "data: " + json.dumps(
                {"error": f"LLM 调用失败：{exc}"}, ensure_ascii=False
            ) + "\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",  # disable Nginx buffering if reverse-proxied
            "Connection": "keep-alive",
        },
    )
