import type { ReactNode } from "react";
import { useLlmSidebar } from "../state/sidebar";

interface LlmSidebarProps {
  /** 侧栏内的主体内容（配置面板 / 对话面板） */
  sidebar: ReactNode;
  /** 侧栏顶部的标题与图标 */
  title: ReactNode;
  /** 主内容区 */
  main: ReactNode;
}

/**
 * LLM 侧边栏共享外壳：折叠/展开 rail、拖拽调宽、宽度持久化、双击重置。
 * 首页与结果页共用此壳，消除原本两页之间整段重复的 aside 结构。
 */
export function LlmSidebar({ sidebar, title, main }: LlmSidebarProps) {
  const { collapsed, setCollapsed, width, sidebarRef, startResize, resetWidth } =
    useLlmSidebar();

  return (
    <div className={"streamlit-shell" + (collapsed ? " sidebar-collapsed" : "")} id="llm-shell">
      <aside
        ref={sidebarRef}
        className="llm-streamlit-sidebar"
        style={{ width: width + "px", flexBasis: width + "px" }}
      >
        <div className="llm-sidebar-body">
          <div className="llm-sidebar-header">
            <h3 className="llm-streamlit-title mb-0">{title}</h3>
            <button
              className="btn btn-sm btn-light llm-sidebar-close"
              type="button"
              aria-label="收起侧栏"
              onClick={() => setCollapsed(true)}
            >
              <i className="bi bi-chevron-double-left" />
            </button>
          </div>
          {sidebar}
        </div>
        <div
          className="llm-sidebar-resizer"
          title="拖拽调整宽度，双击重置"
          aria-hidden="true"
          onPointerDown={startResize}
          onDoubleClick={resetWidth}
        />
      </aside>

      <button
        className="llm-sidebar-rail"
        type="button"
        aria-label="展开 LLM 侧栏"
        onClick={() => setCollapsed(false)}
      >
        <i className="bi bi-chevron-double-right" />
        <span className="llm-rail-text">LLM</span>
      </button>

      <main className="llm-streamlit-main">{main}</main>
    </div>
  );
}