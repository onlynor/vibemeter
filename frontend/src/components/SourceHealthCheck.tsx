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
        className="btn btn-outline-primary btn-sm"
        type="button"
        onClick={check}
        disabled={state.kind === "loading"}
        title="对各平台发一次轻量真实请求，确认当前是否被风控"
      >
        <i className="bi bi-activity me-1" />
        {state.kind === "loading" ? "检测中..." : "检测可用性"}
      </button>

      {state.kind === "error" && (
        <div className="alert alert-danger mt-3 mb-0">检测失败：{state.message}</div>
      )}

      {state.kind === "ready" && state.items.length > 0 && (
        <>
          <HealthList items={state.items.filter((i) => i.kind !== "search")} />
          {/* 搜索引擎不是可选的采集平台，单独分组，避免被误认为能在下拉框里选 */}
          {state.items.some((i) => i.kind === "search") && (
            <>
              <div className="source-health-group-title">检索增强（背景资料）</div>
              <HealthList items={state.items.filter((i) => i.kind === "search")} />
            </>
          )}
        </>
      )}
    </>
  );
}

function HealthList({ items }: { items: SourceHealth[] }) {
  if (items.length === 0) return null;
  return (
    <ul className="source-health-list list-unstyled mb-0">
      {items.map((item) => (
        <li key={item.platform} className="d-flex gap-2 align-items-start">
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
            <span className="ms-2">{item.message}</span>
            {item.cookie_env && !item.cookie_configured && (
              <div className="text-muted mt-1">
                可在 .env 配置 <code>{item.cookie_env}</code>
                {item.cookie_required ? "（该平台必需）" : "（可选，提升稳定性）"}
              </div>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
