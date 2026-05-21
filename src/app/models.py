"""SQLite 数据库表对应的类型化行模型"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class TaskRow(BaseModel):
    task_no: Optional[int] = None
    task_id: str
    keyword: str
    platform: str
    target_count: int
    status: str
    current_count: int = 0
    total_count: int = 0
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    error: Optional[str] = None


class CommentRow(BaseModel):
    id: Optional[int] = None
    task_id: str
    content: str
    platform: str
    fetch_time: str
    sentiment_score: Optional[float] = None
    sentiment_label: Optional[str] = None


class ResultRow(BaseModel):
    task_id: str
    summary_json: Optional[str] = None
    positive_words_json: Optional[str] = None
    negative_words_json: Optional[str] = None
    all_words_json: Optional[str] = None
    time_series_json: Optional[str] = None
    heatmap_json: Optional[str] = None
    comparison_words_json: Optional[str] = None
    positive_comments_json: Optional[str] = None
    negative_comments_json: Optional[str] = None
