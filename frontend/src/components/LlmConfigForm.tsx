import { useState } from "react";
import { api } from "../api/client";
import type { LLMConfig } from "../api/types";

interface Props {
  config: LLMConfig;
  updateField: (field: keyof LLMConfig, value: string) => void;
  /** 结果页紧凑显示：把问题输入框也隐藏 */
  variant?: "default" | "compact";
}

/** LLM 连接配置子表单：Base URL / API Key / 模型名 + 测试连接 */
export function LlmConfigForm({ config, updateField, variant = "default" }: Props) {
  const [testing, setTesting] = useState(false);
  const [testStatus, setTestStatus] = useState<{ text: string; kind: "ok" | "err" | "muted" } | null>(null);

  function runTest() {
    const baseUrl = config.llm_base_url.trim();
    const model = config.llm_model.trim();
    if (!baseUrl || !model) {
      setTestStatus({ text: "请先填写 Base URL 和模型名", kind: "err" });
      return;
    }
    setTesting(true);
    setTestStatus({ text: "正在测试...", kind: "muted" });
    api
      .testLlm({ base_url: baseUrl, api_key: config.llm_api_key.trim(), model })
      .then((data) => setTestStatus({ text: data.message || "连接成功", kind: "ok" }))
      .catch((err: Error) => setTestStatus({ text: "测试失败：" + err.message, kind: "err" }))
      .finally(() => setTesting(false));
  }

  return (
    <div className={"llm-streamlit-panel" + (variant === "compact" ? " mt-2" : "")}>
      {variant === "default" && (
        <div className="mb-3">
          <label className="form-label fw-semibold" htmlFor="llm_question">提问</label>
          <textarea
            id="llm_question"
            className="form-control llm-streamlit-input"
            rows={5}
            placeholder="例如：针对这个热点的舆情分歧你怎么看？"
            value={config.llm_question}
            onChange={(e) => updateField("llm_question", e.target.value)}
          />
          <div className="llm-streamlit-preview mt-2">
            {config.llm_question.trim() || "留空则不调用"}
          </div>
        </div>
      )}

      <div className={variant === "compact" ? "mb-2" : "mb-3"}>
        <label className="form-label fw-semibold" htmlFor="llm_model">模型名</label>
        <input
          id="llm_model"
          className={"form-control llm-streamlit-input" + (variant === "compact" ? " form-control-sm" : "")}
          placeholder="例如：gpt-4o-mini"
          value={config.llm_model}
          onChange={(e) => updateField("llm_model", e.target.value)}
        />
      </div>

      <div className={variant === "compact" ? "mb-2" : "mb-3"}>
        <label className="form-label fw-semibold" htmlFor="llm_base_url">Base URL</label>
        <input
          id="llm_base_url"
          className={"form-control llm-streamlit-input" + (variant === "compact" ? " form-control-sm" : "")}
          placeholder="例如：https://api.example.com/v1"
          value={config.llm_base_url}
          onChange={(e) => updateField("llm_base_url", e.target.value)}
        />
      </div>

      <div className="mb-0">
        <label className="form-label fw-semibold" htmlFor="llm_api_key">API Key</label>
        <input
          id="llm_api_key"
          type="password"
          autoComplete="off"
          className={"form-control llm-streamlit-input" + (variant === "compact" ? " form-control-sm" : "")}
          placeholder="留空则不附带 Authorization 头"
          value={config.llm_api_key}
          onChange={(e) => updateField("llm_api_key", e.target.value)}
        />
      </div>

      <div className="d-flex align-items-center gap-2 mt-3">
        <button
          className="btn btn-outline-primary btn-sm"
          type="button"
          onClick={runTest}
          disabled={testing}
        >
          <i className="bi bi-check2-circle me-1" />测试连接
        </button>
        {testStatus && (
          <span className={"llm-test-status small " + (
            testStatus.kind === "ok" ? "text-success" :
            testStatus.kind === "err" ? "text-danger" : "text-muted"
          )}>
            {testStatus.text}
          </span>
        )}
      </div>
    </div>
  );
}