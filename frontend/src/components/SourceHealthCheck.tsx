import { useState } from "react";
import { api, ApiError } from "../api/client";
import type { SourceHealth } from "../api/types";

type State =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; items: SourceHealth[] };

/** 数据源可用性检测：手动触发，后端结果带 5 分钟缓存 */
export function SourceHealthCheck() {
  const [state, setState] = useState<State>({ kind: "idle" });

  function check() {
    setState({ kind: "loading" });
    api
      .getSourceHealth()
      .then((items) => setState({ kind: "ready", items }))
      .catch((err: ApiError) => setState({ kind: "error", message: err.message }));
  }

  return (
    <>
      <button
        className="btn btn-outline-secondary btn-sm"
        type="button"
        onClick={check}
        disabled={state.kind === "loading"}
        title="对各平台发一次轻量真实请求，确认当前是否被风控"
      >
        <i className="bi bi-activity me-1" />
        {state.kind === "loading" ? "检测中..." : "检测可用性"}
      </button>

      {state.kind === "error" && (
        <div className="text-danger small mt-2">检测失败：{state.message}</div>
      )}

      {state.kind === "ready" && (
        <ul className="source-health-list list-unstyled small mt-2 mb-0">
          {state.items.map((item) => (
            <li key={item.platform} className="d-flex gap-2 align-items-start py-1">
              <i
                className={
                  "bi mt-1 " +
                  (item.ok
                    ? "bi-check-circle-fill text-success"
                    : "bi-exclamation-triangle-fill text-warning")
                }
              />
              <div>
                <span className="fw-semibold">{item.label}</span>
                <span className="text-muted ms-2">{item.message}</span>
                {item.cookie_env && !item.cookie_configured && (
                  <div className="text-muted">
                    可在 .env 配置 <code>{item.cookie_env}</code>
                    {item.cookie_required ? "（该平台必需）" : "（可选，提升稳定性）"}
                  </div>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
