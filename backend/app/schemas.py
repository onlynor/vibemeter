"""HTTP 请求体的 Pydantic 模型

响应侧统一走 routers/api.py 里的 ``_ok`` / ``_err`` 信封，不再单独建模。
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class TaskRequest(BaseModel):
    """创建分析任务的表单请求体"""

    keyword: str = Field(..., min_length=1, max_length=64)
    platform: str = Field(..., pattern="^(auto|bilibili|weibo|douban|zhihu|tieba)$")
    count: int = Field(default=500, ge=300, le=2000)
    llm_base_url: str = Field(default="", max_length=256)
    llm_api_key: str = Field(default="", max_length=256)
    llm_model: str = Field(default="", max_length=128)
    llm_question: str = Field(default="", max_length=240)
    llm_context_format: str = Field(default="xml", pattern="^(xml|markdown)$")


class LLMTestRequest(BaseModel):
    """验证 LLM 端点的轻量级测试请求"""

    base_url: str = Field(..., min_length=1, max_length=256)
    api_key: str = Field(default="", max_length=256)
    model: str = Field(..., min_length=1, max_length=128)


class LLMChatRequest(BaseModel):
    """基于已完成任务上下文的自由对话请求"""

    base_url: str = Field(..., min_length=1, max_length=256)
    api_key: str = Field(default="", max_length=256)
    model: str = Field(..., min_length=1, max_length=128)
    question: str = Field(..., min_length=1, max_length=600)
    context_format: str = Field(default="xml", pattern="^(xml|markdown)$")
    # 对话历史记录，每项包含 role 和 content 字段，最多 12 轮
    history: Optional[List[dict]] = None


class LLMConfigPayload(BaseModel):
    """进程级 LLM 配置，与前端表单字段镜像，仅内存存储"""

    llm_base_url: str = Field(default="", max_length=512)
    llm_api_key: str = Field(default="", max_length=512)
    llm_model: str = Field(default="", max_length=512)
    llm_question: str = Field(default="", max_length=512)
    llm_context_format: str = Field(default="xml", max_length=32)
