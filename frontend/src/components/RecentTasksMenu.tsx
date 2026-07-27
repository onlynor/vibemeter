import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { TaskHistoryItem } from "../api/types";
import { formatDateTime, formatTaskNo, platformLabel } from "../lib/utils";
import { useClickAway } from "./useClickAway";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "empty" }
  | { kind: "ready"; items: TaskHistoryItem[] };

/**
 * 顶部导航中的「最近任务」下拉菜单。点击展开后会拉取历史并展示，
 * 选中任意一项跳转到该任务结果页。跨页面共用，是唯一的最近任务入口。
 */
export function RecentTasksMenu() {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<State>({ kind: "loading" });
  const containerRef = useRef<HTMLDivElement | null>(null);
  const location = useLocation();

  // 当前路径决定是否高亮某条任务
  const currentTaskId = location.pathname.startsWith("/result/")
    ? location.pathname.slice("/result/".length)
    : "";

  // 关闭下拉后跳路由时不再悬停
  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  // 打开时拉取一次最新历史；之后保持缓存，再次打开若超 15s 则刷新
  const lastFetchRef = useRef(0);
  useEffect(() => {
    if (!open) return;
    const now = Date.now();
    if (now - lastFetchRef.current < 15_000 && state.kind === "ready") return;
    lastFetchRef.current = now;
    setState({ kind: "loading" });
    api
      .getHistory()
      .then((items) => {
        if (!items.length) setState({ kind: "empty" });
        else setState({ kind: "ready", items });
      })
      .catch((err: ApiError) => setState({ kind: "error", message: err.message }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const onClickAway = () => setOpen(false);
  useClickAway(containerRef, onClickAway, open);

  return (
    <div className="recent-tasks-menu" ref={containerRef}>
      <button
        type="button"
        className={"recent-tasks-toggle" + (open ? " open" : "")}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <i className="bi bi-clock-history me-1" />
        最近任务
        <i className="bi bi-chevron-down ms-1 recent-tasks-caret" />
      </button>
      {open && (
        <div className="recent-tasks-dropdown shadow" role="menu">
          {state.kind === "loading" && (
            <div className="recent-tasks-hint">正在加载...</div>
          )}
          {state.kind === "error" && (
            <div className="recent-tasks-hint text-danger">加载失败：{state.message}</div>
          )}
          {state.kind === "empty" && (
            <div className="recent-tasks-hint">还没有历史任务</div>
          )}
          {state.kind === "ready" &&
            state.items.map((item) => (
              <Link
                key={item.task_id}
                to={item.url}
                className={
                  "recent-tasks-item" +
                  (item.task_id === currentTaskId ? " current" : "")
                }
                role="menuitem"
              >
                <div className="recent-tasks-item-top">
                  <span className="recent-tasks-item-no">
                    {item.display_no || formatTaskNo(item.task_no)}
                  </span>
                  <span className="recent-tasks-item-status">
                    {item.status === "completed" ? (
                      <span className="badge bg-success-subtle text-success-emphasis">完成</span>
                    ) : item.status === "failed" ? (
                      <span className="badge bg-danger-subtle text-danger-emphasis">失败</span>
                    ) : (
                      <span className="badge bg-secondary-subtle text-secondary-emphasis">
                        {item.status || ""}
                      </span>
                    )}
                  </span>
                </div>
                <div className="recent-tasks-item-keyword">{item.keyword || "(无关键词)"}</div>
                <div className="recent-tasks-item-meta">
                  {platformLabel(item.platform || "")} · {formatDateTime(item.start_time || "")}
                  {" · "}
                  {String(item.total_count || 0)}条
                </div>
              </Link>
            ))}
          {state.kind === "ready" && (
            <Link to="/" className="recent-tasks-footer">
              <i className="bi bi-plus-circle me-1" />新建任务
            </Link>
          )}
        </div>
      )}
    </div>
  );
}