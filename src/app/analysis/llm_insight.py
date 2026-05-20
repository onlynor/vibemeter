"""LLM-powered dialogue using structured post-analysis context."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx


CHAT_SYSTEM_PROMPT = (
    "你是中文舆情分析助手。你只能基于给定上下文回答用户问题，"
    "不能编造未出现的事实，不能扩写国际政治内幕，不能输出图表建议。"
    "如果上下文不足，直接回答“基于当前采集数据，暂时无法判断”。\n"
    "\n"
    "排版要求（必须严格遵守）：\n"
    "- 使用 Markdown 语法回答\n"
    "- 多个要点用 `-` 无序列表，每条 1-2 行\n"
    "- 关键结论用 `**加粗**` 标出\n"
    "- 段落之间用空行分隔\n"
    "- 数据对比适合用表格时使用 Markdown 表格\n"
    "- 引用原评论时用 `> ` 引用块\n"
    "- 不要输出代码块，除非用户明确要求\n"
    "\n"
    "长度建议在 600 字以内；若用户明确要求“详细 / 展开 / 全面”，可以更长，"
    "但务必保证回答完整收尾，不要中途断句。"
)


@dataclass(slots=True)
class LLMConfig:
    """Runtime config for an OpenAI-compatible chat completion endpoint."""

    base_url: str = ""
    api_key: str = ""
    model: str = ""
    question: str = ""
    context_format: str = "xml"

    @property
    def enabled(self) -> bool:
        return bool(
            self.base_url.strip()
            and self.model.strip()
            and self.question.strip()
        )


def _safe_text(value: Any) -> str:
    text = str(value or "").strip()
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _as_xml(summary: dict[str, Any]) -> str:
    pos_comments = "\n".join(
        f'    <comment score="{item["score"]}">{_safe_text(item["text"])}</comment>'
        for item in summary.get("top_positive", [])[:3]
    ) or "    <comment score=\"0\">暂无</comment>"
    neg_comments = "\n".join(
        f'    <comment score="{item["score"]}">{_safe_text(item["text"])}</comment>'
        for item in summary.get("top_negative", [])[:3]
    ) or "    <comment score=\"0\">暂无</comment>"
    pos_words = "\n".join(
        f'    <word count="{count}">{_safe_text(word)}</word>'
        for word, count in summary.get("top_positive_words", [])[:8]
    ) or "    <word count=\"0\">暂无</word>"
    neg_words = "\n".join(
        f'    <word count="{count}">{_safe_text(word)}</word>'
        for word, count in summary.get("top_negative_words", [])[:8]
    ) or "    <word count=\"0\">暂无</word>"
    return (
        "<analysis_context>\n"
        f"  <keyword>{_safe_text(summary.get('keyword'))}</keyword>\n"
        f"  <platform>{_safe_text(summary.get('platform'))}</platform>\n"
        f"  <total_comments>{summary.get('total', 0)}</total_comments>\n"
        "  <sentiment>\n"
        f"    <positive>{summary.get('positive', 0)}</positive>\n"
        f"    <neutral>{summary.get('neutral', 0)}</neutral>\n"
        f"    <negative>{summary.get('negative', 0)}</negative>\n"
        "  </sentiment>\n"
        "  <positive_words>\n"
        f"{pos_words}\n"
        "  </positive_words>\n"
        "  <negative_words>\n"
        f"{neg_words}\n"
        "  </negative_words>\n"
        "  <representative_positive_comments>\n"
        f"{pos_comments}\n"
        "  </representative_positive_comments>\n"
        "  <representative_negative_comments>\n"
        f"{neg_comments}\n"
        "  </representative_negative_comments>\n"
        "</analysis_context>"
    )


def _as_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# 舆情分析上下文",
        f"- 关键词: {summary.get('keyword', '')}",
        f"- 平台: {summary.get('platform', '')}",
        f"- 评论总数: {summary.get('total', 0)}",
        f"- 情感分布: 正向 {summary.get('positive', 0)} / 中立 {summary.get('neutral', 0)} / 负向 {summary.get('negative', 0)}",
        "",
        "## 正向高频短语",
    ]
    pos_words = summary.get("top_positive_words", [])[:8]
    neg_words = summary.get("top_negative_words", [])[:8]
    lines.extend(
        [f"- {word}: {count}" for word, count in pos_words] or ["- 暂无"]
    )
    lines.extend(["", "## 负向高频短语"])
    lines.extend(
        [f"- {word}: {count}" for word, count in neg_words] or ["- 暂无"]
    )
    lines.extend(["", "## 代表性正向评论"])
    lines.extend(
        [f"- ({item['score']}) {item['text']}" for item in summary.get("top_positive", [])[:3]]
        or ["- 暂无"]
    )
    lines.extend(["", "## 代表性负向评论"])
    lines.extend(
        [f"- ({item['score']}) {item['text']}" for item in summary.get("top_negative", [])[:3]]
        or ["- 暂无"]
    )
    return "\n".join(lines)


def build_context(summary: dict[str, Any], context_format: str) -> str:
    """Render summary data into LLM-friendly XML or Markdown."""
    return _as_markdown(summary) if context_format == "markdown" else _as_xml(summary)


async def generate_insight(
    config: LLMConfig,
    summary: dict[str, Any],
) -> dict[str, str] | None:
    """Run a compact Q&A call against structured analysis context."""
    if not config.enabled:
        return None

    context_format = config.context_format if config.context_format in {"xml", "markdown"} else "xml"
    context_text = build_context(summary, context_format)
    system_prompt = (
        "你是中文舆情分析助手。你只能基于给定上下文回答用户问题，"
        "不能编造未出现的事实，不能扩写国际政治内幕，不能输出图表建议。"
        "如果上下文不足，直接回答“基于当前采集数据，暂时无法判断”。"
    )
    user_prompt = (
        f"用户问题：{config.question.strip()}\n\n"
        f"下面是分析后整理出的 {context_format.upper()} 上下文，请据此作答：\n"
        f"{context_text}\n\n"
        "输出严格 JSON 对象，字段只有 title, answer。"
        "title 12字以内，抓住回答主结论；"
        "answer 90到220字，可以分段，但不要使用列表。"
    )

    headers = {"Content-Type": "application/json"}
    if config.api_key.strip():
        headers["Authorization"] = f"Bearer {config.api_key.strip()}"

    base = config.base_url.strip().rstrip("/")
    endpoint = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
    payload = {
        "model": config.model.strip(),
        "temperature": 0.3,
        "max_tokens": 420,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    async with httpx.AsyncClient(timeout=40.0) as client:
        response = await client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    content = (
        (((data.get("choices") or [{}])[0]).get("message") or {}).get("content") or "{}"
    )
    parsed = json.loads(content)
    title = str(parsed.get("title", "")).strip()
    answer = str(parsed.get("answer", "")).strip()
    if not (title or answer):
        return None
    return {
        "question": config.question.strip(),
        "context_format": context_format,
        "context_text": context_text,
        "title": title,
        "answer": answer,
    }


def _resolve_endpoint(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    return base if base.endswith("/chat/completions") else f"{base}/chat/completions"


def _auth_headers(api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    key = (api_key or "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


async def ping_llm(base_url: str, api_key: str, model: str) -> tuple[bool, str]:
    """Send the smallest possible request to verify the LLM endpoint.

    Returns ``(ok, message)``. ``message`` carries either the model's
    reply preview on success or the failure reason on error.
    """
    base_url = (base_url or "").strip()
    model = (model or "").strip()
    if not base_url or not model:
        return False, "Base URL 和模型名都必须填写"

    payload = {
        "model": model,
        "max_tokens": 16,
        "temperature": 0,
        "messages": [
            {"role": "user", "content": "ping"},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                _resolve_endpoint(base_url),
                headers=_auth_headers(api_key),
                json=payload,
            )
    except httpx.HTTPError as exc:
        return False, f"网络错误：{exc.__class__.__name__}"

    if response.status_code >= 400:
        try:
            body = response.json()
            err = (body.get("error") or {}).get("message") or response.text[:200]
        except Exception:
            err = response.text[:200] or response.reason_phrase
        return False, f"HTTP {response.status_code}：{err}"

    try:
        data = response.json()
    except Exception:
        return False, "返回内容不是合法 JSON"

    reply = (
        (((data.get("choices") or [{}])[0]).get("message") or {}).get("content") or ""
    ).strip()
    preview = reply[:60] if reply else "(空响应)"
    return True, f"连接成功 · 模型回复：{preview}"


async def chat_with_context(
    *,
    base_url: str,
    api_key: str,
    model: str,
    question: str,
    summary: dict[str, Any],
    context_format: str = "xml",
    history: list[dict[str, str]] | None = None,
) -> dict[str, str]:
    """Run a free-form chat turn anchored on the analysis context.

    Differs from :func:`generate_insight` in that:
    * No JSON-mode constraint — the model can answer in plain text.
    * Conversation ``history`` is forwarded so multi-turn chats work.
    * Only the first turn carries the (potentially large) context block;
      subsequent turns reuse the same system message but skip the
      context payload to keep token usage reasonable.
    """
    base_url = (base_url or "").strip()
    model = (model or "").strip()
    question = (question or "").strip()
    if not (base_url and model and question):
        raise ValueError("base_url / model / question 都不能为空")

    ctx_fmt = context_format if context_format in {"xml", "markdown"} else "xml"
    context_text = build_context(summary, ctx_fmt)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"下面是分析后整理出的 {ctx_fmt.upper()} 上下文，请以此为依据回答后续提问：\n"
                f"{context_text}"
            ),
        },
        {"role": "assistant", "content": "好的，请提问。"},
    ]
    for entry in (history or [])[-12:]:
        role = entry.get("role")
        content = (entry.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})

    payload = {
        "model": model,
        "temperature": 0.4,
        "max_tokens": 1500,
        "messages": messages,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            _resolve_endpoint(base_url),
            headers=_auth_headers(api_key),
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    answer = (
        (((data.get("choices") or [{}])[0]).get("message") or {}).get("content") or ""
    ).strip()
    return {
        "answer": answer or "(模型返回了空回复)",
        "context_format": ctx_fmt,
    }


async def chat_with_context_stream(
    *,
    base_url: str,
    api_key: str,
    model: str,
    question: str,
    summary: dict[str, Any],
    context_format: str = "xml",
    history: list[dict[str, str]] | None = None,
) -> AsyncIterator[str]:
    """Streaming variant of :func:`chat_with_context`.

    Yields incremental text deltas from the upstream OpenAI-compatible
    chat completion. Caller is responsible for SSE framing.
    """
    base_url = (base_url or "").strip()
    model = (model or "").strip()
    question = (question or "").strip()
    if not (base_url and model and question):
        raise ValueError("base_url / model / question 都不能为空")

    ctx_fmt = context_format if context_format in {"xml", "markdown"} else "xml"
    context_text = build_context(summary, ctx_fmt)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"下面是分析后整理出的 {ctx_fmt.upper()} 上下文，请以此为依据回答后续提问：\n"
                f"{context_text}"
            ),
        },
        {"role": "assistant", "content": "好的，请提问。"},
    ]
    for entry in (history or [])[-12:]:
        role = entry.get("role")
        content = (entry.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})

    payload = {
        "model": model,
        "temperature": 0.4,
        "max_tokens": 1500,
        "stream": True,
        "messages": messages,
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=None)) as client:
        async with client.stream(
            "POST",
            _resolve_endpoint(base_url),
            headers=_auth_headers(api_key),
            json=payload,
        ) as response:
            if response.status_code >= 400:
                # Drain so the error body is available, then raise.
                body = await response.aread()
                raise httpx.HTTPStatusError(
                    f"HTTP {response.status_code}: {body[:200].decode('utf-8', 'replace')}",
                    request=response.request,
                    response=response,
                )
            async for raw_line in response.aiter_lines():
                if not raw_line:
                    continue
                line = raw_line.strip()
                if not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if not data_str or data_str == "[DONE]":
                    if data_str == "[DONE]":
                        break
                    continue
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                delta = (
                    (((chunk.get("choices") or [{}])[0]).get("delta") or {}).get("content")
                )
                if delta:
                    yield delta
