"""WebSocket 路由，向仪表板推送任务进度"""
from __future__ import annotations

import asyncio

import aiosqlite
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import DB_PATH
from app.tasks.manager import task_manager


router = APIRouter()


@router.websocket("/ws/task/{task_id}")
async def task_progress(websocket: WebSocket, task_id: str) -> None:
    """将队列中的进度消息转发给已连接的仪表板客户端"""
    await websocket.accept()

    # 如果任务已完成，立即通知客户端并关闭连接
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM tasks WHERE task_id = ?",
            (task_id,),
        )
        row = await cursor.fetchone()

    if row is None:
        await websocket.send_json({"status": "failed", "message": "任务不存在"})
        await websocket.close()
        return

    if row["status"] == "completed":
        await websocket.send_json({
            "status": "completed",
            "current": row["total_count"],
            "total": max(1, row["total_count"]),
            "message": "任务已完成",
        })
        await websocket.close()
        return

    if row["status"] == "failed":
        await websocket.send_json({
            "status": "failed",
            "message": row["error"] or "任务失败",
        })
        await websocket.close()
        return

    queue = task_manager.get_queue(task_id)
    try:
        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=60)
            except asyncio.TimeoutError:
                await websocket.send_json({"status": "keepalive"})
                continue
            await websocket.send_json(payload)
            if payload.get("status") in {"completed", "failed"}:
                break
    except WebSocketDisconnect:
        return
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
