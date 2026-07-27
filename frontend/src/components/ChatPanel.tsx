import { useCallback, useEffect, useRef, useState } from "react";
import type { LLMConfig, ChatMessage, ChatStreamEvent } from "../api/types";
import { renderMarkdown } from "../lib/utils";
import { backfillChatHistory, commitChatHistory, streamChat } from "../api/chat";

interface Props {
  taskId: string;
  config: LLMConfig;
}

/**
 * LLM 流式对话面板。
 *
 * 状态机：与原 result_chat.js 相同的"不留痕"语义——
 *   发送：先把 {user, assistant("")} 入栈，仅在成功后持久化；
 *   失败/中止/空回复：把这一对从历史里 splice 掉，刷不出半截答。
 *
 * 实现：用 React state 管气泡，SSE 解析放在 api/chat.ts 的可复用 async iterator 里。
 */
export function ChatPanel({ taskId, config }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 当前流式请求的 AbortController，用 ref 以便"停止"按钮同步取到
  const abortRef = useRef<AbortController | null>(null);
  // 镜像 messages，用于在 async 流里同步计算最终状态
  const messagesRef = useRef<ChatMessage[]>([]);

  // 同时同步 ref 与 state，避免在 await 之间出现 ref 滞后
  function applyMessages(next: ChatMessage[]) {
    messagesRef.current = next;
    setMessages(next);
  }

  // 首次挂载：从 sessionStorage 恢复对话历史
  useEffect(() => {
    applyMessages(backfillChatHistory(taskId));
  }, [taskId]);

  // 页面关闭时中止进行中的流
  useEffect(() => {
    function onBeforeUnload() {
      if (abortRef.current) {
        try { abortRef.current.abort(); } catch { /* ignore */ }
      }
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, []);

  // 让对话区始终滚到底部
  const historyRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const el = historyRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages]);

  const sendQuestion = useCallback(
    async (question: string) => {
      const baseUrl = config.llm_base_url.trim();
      const model = config.llm_model.trim();
      if (!baseUrl || !model) {
        setError("请先在上方填写 Base URL 和模型名");
        return;
      }
      setError("");

      const historyForUpstream = messagesRef.current.slice();
      const localMessages: ChatMessage[] = [
        ...historyForUpstream,
        { role: "user", content: question },
        { role: "assistant", content: "" },
      ];
      applyMessages(localMessages);
      setInput("");

      const controller = new AbortController();
      abortRef.current = controller;
      setStreaming(true);

      let accumulated = "";
      let errorMessage: string | null = null;
      let succeeded = false;

      try {
        for await (const ev of streamChat(
          taskId,
          {
            base_url: baseUrl,
            api_key: config.llm_api_key.trim(),
            model,
            question,
            context_format: config.llm_context_format,
            history: historyForUpstream,
          },
          controller.signal
        )) {
          const typed = ev as ChatStreamEvent;
          if ("error" in typed && typed.error) {
            errorMessage = typed.error;
            break;
          }
          if ("done" in typed) {
            succeeded = true;
            break;
          }
          if ("delta" in typed && typeof typed.delta === "string") {
            accumulated += typed.delta;
            // 仅替换最后一个 assistant 气泡的内容
            const current = messagesRef.current.slice();
            const lastIdx = current.length - 1;
            if (current[lastIdx]?.role === "assistant") {
              current[lastIdx] = { role: "assistant", content: accumulated };
            }
            applyMessages(current);
          }
        }
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          errorMessage = "连接失败：" + (err as Error).message;
        }
        // AbortError 由下面 discard 分支处理
      }

      // 计算最终消息数组：成功且 assistant 有内容则保留这对，否则删掉这对
      const currentMessages = messagesRef.current;
      const before = currentMessages.slice(0, -2);
      const lastAssistant = currentMessages[currentMessages.length - 1];
      const keepThisTurn =
        succeeded && !!lastAssistant && !!lastAssistant.content;
      const finalized = keepThisTurn ? currentMessages.slice() : before;

      if (errorMessage) {
        setError(errorMessage);
      } else if (!keepThisTurn && succeeded) {
        // 模型返回空回复，视为失败轮次
        setError("模型返回了空回复");
      } else {
        setError(null);
      }

      if (!keepThisTurn) {
        // 失败 / 中止 / 空回复：把这对从历史里丢掉，不留半截
        applyMessages(before);
      }
      commitChatHistory(taskId, finalized);

      abortRef.current = null;
      setStreaming(false);
    },
    [config, taskId]
  );

  function stopActiveStream() {
    if (abortRef.current) {
      try { abortRef.current.abort(); } catch { /* ignore */ }
    }
  }

  function clearChat() {
    if (streaming) stopActiveStream();
    applyMessages([]);
    setError(null);
    commitChatHistory(taskId, []);
  }

  function onInputKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      handleSubmit();
    }
  }

  function handleSubmit() {
    if (streaming) {
      stopActiveStream();
      return;
    }
    const question = input.trim();
    if (!question) return;
    void sendQuestion(question);
  }

  return (
    <>
      <div className="llm-chat-history" ref={historyRef}>
        {messages.length === 0 ? (
          <div className="text-muted small llm-chat-empty">
            分析完成后，在下方输入你想问的问题，我会基于当前任务的数据作答。
          </div>
        ) : (
          messages.map((entry, idx) => {
            const isStreamingBubble =
              streaming && idx === messages.length - 1 && entry.role === "assistant";
            return (
              <div key={idx} className={"chat-message chat-message-" + entry.role}>
                <span className="chat-avatar">
                  {entry.role === "user" ? (
                    <i className="bi bi-person-circle" />
                  ) : (
                    <i className="bi bi-stars" />
                  )}
                </span>
                <div className={"chat-bubble chat-bubble-" + entry.role}>
                  {entry.role === "assistant" ? (
                    entry.content ? (
                      <span
                        dangerouslySetInnerHTML={{
                          __html: renderMarkdown(entry.content),
                        }}
                      />
                    ) : (
                      <span className="chat-typing">
                        <span /><span /><span />
                      </span>
                    )
                  ) : (
                    entry.content
                  )}
                  {isStreamingBubble && entry.content && (
                    <span className="chat-cursor">▍</span>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {error && (
        <div className="llm-chat-error small text-danger mt-2">{error}</div>
      )}

      <form className="mt-2" autoComplete="off"
            onSubmit={(e) => { e.preventDefault(); handleSubmit(); }}>
        <textarea
          className="form-control llm-streamlit-input"
          rows={3}
          placeholder="比如：正向评论里主要讨论了什么？"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onInputKeyDown}
          disabled={streaming}
        />
        <div className="d-flex justify-content-between align-items-center mt-2 gap-2">
          <button
            className="btn btn-link btn-sm p-0 text-muted"
            type="button"
            onClick={clearChat}
          >
            清空对话
          </button>
          {streaming ? (
            <button
              className="btn btn-danger btn-sm"
              type="button"
              onClick={stopActiveStream}
            >
              <i className="bi bi-stop-circle me-1" />停止
            </button>
          ) : (
            <button className="btn btn-primary btn-sm" type="submit">
              <i className="bi bi-send me-1" />发送
            </button>
          )}
        </div>
      </form>
    </>
  );
}