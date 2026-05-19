"""Pydantic schemas for HTTP / WebSocket payloads."""
from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field


class TaskRequest(BaseModel):
    """Form payload sent when creating a new analysis task."""

    keyword: str = Field(..., min_length=1, max_length=64)
    platform: str = Field(..., pattern="^(auto|bilibili|weibo)$")
    count: int = Field(default=500, ge=300, le=2000)
    llm_base_url: str = Field(default="", max_length=256)
    llm_api_key: str = Field(default="", max_length=256)
    llm_model: str = Field(default="", max_length=128)
    llm_question: str = Field(default="", max_length=240)
    llm_context_format: str = Field(default="xml", pattern="^(xml|markdown)$")


class TaskCreated(BaseModel):
    task_id: str


class LLMTestRequest(BaseModel):
    """Lightweight ping payload for verifying the LLM endpoint."""

    base_url: str = Field(..., min_length=1, max_length=256)
    api_key: str = Field(default="", max_length=256)
    model: str = Field(..., min_length=1, max_length=128)


class LLMChatRequest(BaseModel):
    """Free-form follow-up question against a finished task's context."""

    base_url: str = Field(..., min_length=1, max_length=256)
    api_key: str = Field(default="", max_length=256)
    model: str = Field(..., min_length=1, max_length=128)
    question: str = Field(..., min_length=1, max_length=600)
    context_format: str = Field(default="xml", pattern="^(xml|markdown)$")
    # Each entry is {role: "user"|"assistant", content: str}; capped at 12 turns.
    history: Optional[List[dict]] = None


class LLMConfigPayload(BaseModel):
    """Per-process LLM config, mirrored from the frontend form fields.

    Stored in memory only — cleared when the process exits.
    """

    llm_base_url: str = Field(default="", max_length=512)
    llm_api_key: str = Field(default="", max_length=512)
    llm_model: str = Field(default="", max_length=512)
    llm_question: str = Field(default="", max_length=512)
    llm_context_format: str = Field(default="xml", max_length=32)


class ApiResponse(BaseModel):
    """Envelope wrapping every JSON API response."""

    code: int = 0
    data: Optional[Any] = None
    msg: Optional[str] = None


class ProgressMessage(BaseModel):
    """Single update pushed over the WebSocket connection."""

    status: str
    current: int = 0
    total: int = 0
    message: str = ""
    elapsed: Optional[float] = None
    error: Optional[str] = None
