import type { ChatMessage, ChatStreamEvent } from "./types";

const CHAT_HISTORY_PREFIX = "vibe.llm.chat.history.";

interface ChatStreamPayload {
  base_url: string;
  api_key: string;
  model: string;
  question: string;
  context_format: "xml" | "markdown";
  history: ChatMessage[];
}

/** 把缓冲区解析为完整的 SSE 事件，剩下的尾巴还回缓冲区 */
function parseSseBuffer(buf: string): { events: any[]; rest: string } {
  const events: any[] = [];
  let rest = buf;
  while (true) {
    const sep = rest.indexOf("\n\n");
    if (sep === -1) break;
    const rawEvent = rest.slice(0, sep);
    rest = rest.slice(sep + 2);
    const lines = rawEvent.split("\n");
    const dataLines: string[] = [];
    for (const line of lines) {
      if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trim());
      }
    }
    if (!dataLines.length) continue;
    try {
      events.push(JSON.parse(dataLines.join("\n")));
    } catch {
      /* skip malformed frame */
    }
  }
  return { events, rest };
}

/**
 * 调用后端 /api/result/{taskId}/llm-chat-stream 并以 async iterator 形式
 * 产出 ChatStreamEvent。中止时抛 AbortError（交由调用方处理）。
 *
 * 注意：后端是自定义 SSE 协议（{delta} / {error} / {done}），
 * 非 OpenAI 标准，所以这里不能直接用 Vercel AI SDK 的 useChat，
 * 而 env 这次先用这个薄封装。后续若后端切换成 OpenAI 兼容流式协议，
 * 此函数可整体替换为 AI SDK 的 streamText。
 */
export async function* streamChat(
  taskId: string,
  payload: ChatStreamPayload,
  signal?: AbortSignal
): AsyncGenerator<ChatStreamEvent, void, unknown> {
  const response = await fetch(
    `/api/result/${taskId}/llm-chat-stream`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({
        base_url: payload.base_url,
        api_key: payload.api_key,
        model: payload.model,
        question: payload.question,
        context_format: payload.context_format,
        history: payload.history,
      }),
      signal,
    }
  );

  if (!response.ok || !response.body) {
    throw new Error("HTTP " + response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buf = "";
  let closed = false;

  try {
    while (!closed) {
      const chunk = await reader.read();
      if (chunk.done) break;
      buf += decoder.decode(chunk.value, { stream: true });
      const parsed = parseSseBuffer(buf);
      buf = parsed.rest;
      for (const ev of parsed.events) {
        if (ev && typeof ev === "object") {
          if (typeof ev.error === "string") {
            yield { error: ev.error } as ChatStreamEvent;
            closed = true;
            break;
          }
          if (ev.done === true) {
            yield { done: true } as ChatStreamEvent;
            closed = true;
            break;
          }
          if (typeof ev.delta === "string") {
            yield { delta: ev.delta } as ChatStreamEvent;
          }
        }
      }
    }
  } finally {
    try { reader.releaseLock(); } catch { /* ignore */ }
  }
}

function key(taskId: string): string {
  return CHAT_HISTORY_PREFIX + taskId;
}

/** 从 sessionStorage 恢复某任务的对话历史 */
export function backfillChatHistory(taskId: string): ChatMessage[] {
  try {
    const raw = sessionStorage.getItem(key(taskId));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as ChatMessage[]) : [];
  } catch {
    return [];
  }
}

/** 把对话历史写回 sessionStorage */
export function commitChatHistory(taskId: string, messages: ChatMessage[]): void {
  try {
    sessionStorage.setItem(key(taskId), JSON.stringify(messages));
  } catch {
    /* ignore */
  }
}