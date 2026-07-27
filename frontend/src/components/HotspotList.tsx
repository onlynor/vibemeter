import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { Hotspot } from "../api/types";
import { escapeHtml, platformLabel } from "../lib/utils";

interface Props {
  onPick: (title: string) => void;
}

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "empty" }
  | { kind: "ready"; items: Hotspot[] };

const EMPTY_STATE = (
  <div className="text-muted small py-4 text-center">暂无热搜</div>
);

export function HotspotList({ onPick }: Props) {
  const [state, setState] = useState<State>({ kind: "loading" });
  // 标记首屏是否已加载过，避免外层卡片忽显忽隐
  const loadedRef = useRef(false);

  function load() {
    setState({ kind: "loading" });
    api
      .getHotspots()
      .then((items) => {
        const filtered = items.filter((x) => x && x.title);
        loadedRef.current = true;
        if (!filtered.length) setState({ kind: "empty" });
        else setState({ kind: "ready", items: filtered });
      })
      .catch((err: ApiError) => setState({ kind: "error", message: err.message }));
  }

  useEffect(load, []);

  function renderBody() {
    switch (state.kind) {
      case "loading":
        return <div className="text-muted small py-4 text-center">正在获取热搜...</div>;
      case "empty":
        return EMPTY_STATE;
      case "error":
        return <div className="text-danger small py-3">热搜加载失败：{state.message}</div>;
      case "ready":
        return state.items.map((item) => {
          const jumpLabel = item.is_mock ? "打开搜索页" : "打开来源页";
          // 仅允许 http(s) 外链
          const safeUrl =
            item.url && /^https?:\/\//i.test(item.url) ? item.url : "";
          return (
            <button
              key={String(item.rank) + item.title}
              type="button"
              className="hotspot-item"
              onClick={(event) => {
                if ((event.target as HTMLElement).closest("a")) return;
                onPick(item.title);
              }}
              title="点击填入关键词"
            >
              <div className="d-flex gap-3">
                <span
                  className="hotspot-rank"
                  dangerouslySetInnerHTML={{ __html: escapeHtml(item.rank) }}
                />
                <div className="flex-grow-1">
                  <div className="d-flex justify-content-between gap-2">
                    <div className="hotspot-title">
                      <span dangerouslySetInnerHTML={{ __html: escapeHtml(item.title) }} />
                    </div>
                    <span className="hotspot-source">
                      <i className="bi bi-fire" />
                      <span dangerouslySetInnerHTML={{ __html: escapeHtml(platformLabel(item.source)) }} />
                    </span>
                  </div>
                  <div
                    className="text-muted small mt-1"
                    dangerouslySetInnerHTML={{ __html: escapeHtml(item.subtitle || "暂无摘要") }}
                  />
                  <div className="d-flex justify-content-between align-items-center gap-2 mt-2">
                    <div className="hotspot-meta">
                      热度值：
                      <span dangerouslySetInnerHTML={{ __html: escapeHtml(item.score || "—") }} />
                    </div>
                    {safeUrl && (
                      <a
                        className="hotspot-jump"
                        href={safeUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {jumpLabel}
                      </a>
                    )}
                  </div>
                </div>
              </div>
            </button>
          );
        });
    }
  }

  return (
    <div className="hotspot-card card border-0 shadow-sm">
      <div className="card-body p-4">
        <div className="d-flex justify-content-between align-items-center mb-3">
          <h4 className="fw-bold mb-0">实时热搜</h4>
          <button className="btn btn-outline-secondary btn-sm" type="button" title="刷新" onClick={load}>
            <i className="bi bi-arrow-clockwise" />
          </button>
        </div>
        {renderBody()}
      </div>
    </div>
  );
}