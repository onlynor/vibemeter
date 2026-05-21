"""REST API 路由，为仪表板提供数据接口"""
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


# 内部工具函数

async def _load_field(task_id: str, field: str):
    """从结果表中读取指定 JSON 列"""
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
    """渲染短语云 PNG 并返回 base64 编码"""
    if not words:
        return ""
    font_path = get_font_path()
    if not font_path:
        raise RuntimeError("未找到可用中文字体，无法生成词云")
    cloud = WordCloud(
        font_path=font_path,
        width=1200,
        height=800,
        background_color="white",
        max_words=200,
        margin=2,
        prefer_horizontal=0.85,
        relative_scaling=0.2,
        min_font_size=10,
        max_font_size=120,
        collocations=False,
        colormap=palette,
    )
    image = cloud.generate_from_frequencies(dict(words)).to_image()
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")

# API 端点

@router.get("/task/{task_id}/status")
async def task_status(task_id: str):
    """返回单个任务的生命周期元数据"""
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
    """返回最新的任务历史记录（按时间倒序）"""
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
    """创建一个分析任务"""
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
    """返回合并后的首页热搜数据"""
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
    """返回将喂给 LLM 的 XML 格式上下文，供仪表板展示"""
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
    """返回之前导出的数据文件，kind 为 raw/cleaned/analysed/summary 之一"""
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
    """列出可下载的导出文件"""
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
    """返回进程内存中当前的 LLM 配置"""
    return _ok(get_llm_config())


@router.post("/llm/config")
async def write_llm_config(payload: LLMConfigPayload):
    """用提交的值替换内存中的 LLM 配置"""
    updated = update_llm_config(payload.model_dump())
    return _ok(updated)


@router.post("/llm/test")
async def test_llm(payload: LLMTestRequest):
    """用一次小型聊天请求验证 LLM 端点"""
    ok, message = await ping_llm(payload.base_url, payload.api_key, payload.model)
    if not ok:
        return _err(message)
    return _ok({"message": message})


@router.post("/result/{task_id}/llm-chat")
async def llm_chat(task_id: str, payload: LLMChatRequest):
    """基于任务分析上下文的自由对话"""
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
    """llm_chat 的 SSE 流式版本，逐块返回内容增量"""
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
