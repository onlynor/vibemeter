"""HTTP 请求体的 Pydantic 模型

响应侧统一走 routers/api.py 里的 ``_ok`` / ``_err`` 信封，不再单独建模。
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


# 与 app.crawlers._REGISTRY 对应；此处独立写一份是为了让 schemas 不反向依赖
# 爬虫包（保持导入方向单一），改动数据源时两边要一起改。
CRAWLER_PLATFORMS: frozenset[str] = frozenset(
    {"bilibili", "weibo", "douban", "zhihu", "tieba"}
)


class TaskRequest(BaseModel):
    """创建分析任务的表单请求体"""

    keyword: str = Field(..., min_length=1, max_length=64)
    platform: str = Field(..., pattern="^(auto|bilibili|weibo|douban|zhihu|tieba)$")
    count: int = Field(default=500, ge=300, le=2000)
    # 仅在 platform=auto 时有意义：限定聚合采集实际启动哪几个源。
    # 省略 / None = 全部，与旧客户端行为一致。
    platforms: Optional[List[str]] = Field(default=None, max_length=8)
    # 检索增强启用哪些搜索引擎。None = 全部；空列表 = 关闭检索增强，
    # 两者语义不同，不要在这里把 [] 归一成 None。
    search_providers: Optional[List[str]] = Field(default=None, max_length=8)
    llm_base_url: str = Field(default="", max_length=256)
    llm_api_key: str = Field(default="", max_length=256)
    llm_model: str = Field(default="", max_length=128)
    llm_question: str = Field(default="", max_length=240)
    llm_context_format: str = Field(default="xml", pattern="^(xml|markdown)$")

    @field_validator("platforms")
    @classmethod
    def _known_platforms(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        """丢掉不认识的平台名而不是报 422

        前端可能比后端新（多勾了一个尚未实现的源）。为此让整个任务创建失败
        对用户毫无帮助，静默忽略并跑其余的源才是有用的行为。
        """
        if value is None:
            return None
        return [p for p in value if p in CRAWLER_PLATFORMS]

    @field_validator("search_providers")
    @classmethod
    def _sane_providers(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        """只做形状校验，具体有哪些 provider 由注册表说了算

        搜索层是开闭的——新增 provider 不必改任何既有代码，这里若写死白名单
        就把那个性质破坏了。未知名字会在注册表里被跳过。
        """
        if value is None:
            return None
        return [p for p in value if p.replace("_", "").isalnum() and len(p) <= 32]


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
