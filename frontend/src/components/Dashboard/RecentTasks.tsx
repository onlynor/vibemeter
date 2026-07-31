import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../../api/client";
import type { TaskHistoryItem } from "../../api/types";
import { formatDateTime, formatTaskNo, platformLabel } from "../../lib/utils";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; items: TaskHistoryItem[] };

const HIDDEN_KEY = "vibe.home.hiddenTasks.v1";

const STATUS_META: Record<string, { label: string; cls: string; icon: string }> = {
  completed: { label: "已完成", cls: "status-done", icon: "bi-check-circle-fill" },
  failed: { label: "失败", cls: "status-failed", icon: "bi-x-circle-fill" },
  pending: { label: "排队中", cls: "status-running", icon: "bi-hourglass" },
  crawling: { label: "采集中", cls: "status-running", icon: "bi-arrow-repeat" },
  preprocessing: { label: "清洗中", cls: "status-running", icon: "bi-arrow-repeat" },
  analyzing: { label: "分析中", cls: "status-running", icon: "bi-arrow-repeat" },
  wordcloud: { label: "生成中", cls: "status-running", icon: "bi-arrow-repeat" },
  llm: { label: "解读中", cls: "status-running", icon: "bi-arrow-repeat" },
};

function statusOf(status: string) {
  return STATUS_META[status] || { label: status || "未知", cls: "status-running", icon: "bi-circle" };
}

function loadHidden(): string[] {
  try {
    const raw = localStorage.getItem(HIDDEN_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

/**
 * 最近分析任务。
 *
 * “删除”只在前端隐藏并记进 localStorage —— 后端没有删除任务的接口，且
 * 每次重启会清库、运行期只保留最近 10 条。做成本地隐藏而不是假装调用了
 * 删除接口，用户在别的浏览器仍能看到该任务，这一点在 UI 上写明了。
 *
 * TODO(backend): 需要 DELETE /api/task/{id} 才能做成真正的删除。
 */
export function RecentTasks() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [hidden, setHidden] = useState<string[]>(loadHidden);

  const load = useCallback(() => {
    setState({ kind: "loading" });
    api
      .getHistory()
      .then((items) => setState({ kind: "ready", items: items || [] }))
      .catch((err: ApiError) => setState({ kind: "error", message: err.message }));
  }, []);

  useEffect(load, [load]);

  useEffect(() => {
    try {
      localStorage.setItem(HIDDEN_KEY, JSON.stringify(hidden));
    } catch {
      /* ignore */
    }
  }, [hidden]);

  const visible = useMemo(() => {
    if (state.kind !== "ready") return [];
    return state.items.filter((t) => !hidden.includes(t.task_id));
  }, [state, hidden]);

  const hiddenCount =
    state.kind === "ready" ? state.items.length - visible.length : 0;

  function renderBody() {
    if (state.kind === "loading") {
      return (
        <div className="skeleton-list" aria-busy="true" aria-label="正在加载任务">
          {Array.from({ length: 3 }).map((_, i) => (
            <div className="skeleton-row" key={i}>
              <div className="flex-grow-1">
                <div className="skeleton-box" style={{ width: "45%", height: 14 }} />
                <div className="skeleton-box mt-2" style={{ width: "70%", height: 12 }} />
              </div>
            </div>
          ))}
        </div>
      );
    }
    if (state.kind === "error") {
      return (
        <div className="empty-state">
          <i className="bi bi-cloud-slash empty-state-icon" />
          <div className="fw-semibold">任务列表加载失败</div>
          <div className="text-muted small mb-3">{state.message}</div>
          <button className="btn btn-outline-primary btn-sm" type="button" onClick={load}>
            重试
          </button>
        </div>
      );
    }
    if (!visible.length) {
      return (
        <div className="empty-state">
          <i className="bi bi-clock-history empty-state-icon" />
          <div className="fw-semibold">还没有分析任务</div>
          <div className="text-muted small">
            在上方输入关键词并点击「开始分析」，任务会出现在这里
          </div>
        </div>
      );
    }
    return (
      <div className="task-list">
        {visible.map((task) => {
          const meta = statusOf(task.status);
          const running = meta.cls === "status-running";
          return (
            <div className="task-row" key={task.task_id}>
              <div className="min-w-0 flex-grow-1">
                <div className="d-flex align-items-center gap-2 flex-wrap">
                  <span className="task-no">{formatTaskNo(task.task_no)}</span>
                  <span className="task-keyword text-break">{task.keyword}</span>
                  <span className={"status-pill " + meta.cls}>
                    <i className={"bi " + meta.icon + (running ? " spin" : "")} />
                    {meta.label}
                  </span>
                </div>
                <div className="text-muted small mt-1 d-flex gap-3 flex-wrap">
                  <span>
                    <i className="bi bi-diagram-3 me-1" />
                    {platformLabel(task.platform)}
                  </span>
                  <span>
                    <i className="bi bi-clock me-1" />
                    {formatDateTime(task.start_time) || "—"}
                  </span>
                  {task.total_count > 0 && (
                    <span>
                      <i className="bi bi-list-ul me-1" />
                      {task.total_count} 条
                    </span>
                  )}
                </div>
                {task.status === "failed" && task.error && (
                  <div className="text-danger small mt-1 text-truncate-2">{task.error}</div>
                )}
              </div>
              <div className="d-flex align-items-center gap-1 flex-shrink-0">
                <Link
                  className="btn btn-sm btn-outline-primary"
                  to={"/result/" + task.task_id}
                  title="查看结果"
                >
                  查看
                </Link>
                <button
                  className="btn btn-sm btn-outline-secondary"
                  type="button"
                  title="从本机列表中隐藏"
                  aria-label={"隐藏任务 " + task.keyword}
                  onClick={() => setHidden((prev) => [...prev, task.task_id])}
                >
                  <i className="bi bi-x-lg" />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div className="hotspot-card card border-0 shadow-sm h-100">
      <div className="card-body p-4">
        <div className="d-flex justify-content-between align-items-start gap-2 mb-3">
          <div>
            <h4 className="fw-bold mb-0">
              <i className="bi bi-clock-history text-primary me-2" />最近分析任务
            </h4>
            <div className="text-muted" style={{ fontSize: ".78rem" }}>
              服务端仅保留最近 10 个任务，重启后清空
            </div>
          </div>
          <button
            className="btn btn-outline-secondary btn-sm"
            type="button"
            title="刷新"
            aria-label="刷新任务列表"
            onClick={load}
          >
            <i className="bi bi-arrow-clockwise" />
          </button>
        </div>
        {renderBody()}
        {hiddenCount > 0 && (
          <div className="text-muted small mt-3 d-flex align-items-center gap-2">
            <span>已在本机隐藏 {hiddenCount} 个任务</span>
            <button
              className="btn btn-link btn-sm p-0"
              type="button"
              onClick={() => setHidden([])}
            >
              恢复显示
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
