import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { Hotspot } from "../../api/types";
import { platformLabel } from "../../lib/utils";

interface Props {
  onPick: (title: string) => void;
}

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; items: Hotspot[] };

type Trend = "up" | "down" | "flat" | "new";

const INTERVALS = [
  { value: 0, label: "手动" },
  { value: 5 * 60_000, label: "5 分钟" },
  { value: 15 * 60_000, label: "15 分钟" },
  { value: 60 * 60_000, label: "1 小时" },
];

const TREND_META: Record<Trend, { icon: string; cls: string; text: string }> = {
  up: { icon: "bi-arrow-up", cls: "trend-up", text: "上升" },
  down: { icon: "bi-arrow-down", cls: "trend-down", text: "下降" },
  flat: { icon: "bi-dash", cls: "trend-flat", text: "持平" },
  new: { icon: "bi-asterisk", cls: "trend-new", text: "新上榜" },
};

function toRank(value: number | string): number {
  const n = typeof value === "number" ? value : parseInt(String(value), 10);
  return Number.isFinite(n) ? n : 0;
}

/** 把 "7904456" 之类的热度值压成 790.4万，纯数字读起来太费劲 */
function formatHeat(score?: string): string {
  if (!score) return "";
  const digits = String(score).replace(/[^\d.]/g, "");
  const n = Number(digits);
  if (!digits || !Number.isFinite(n) || n <= 0) return String(score);
  if (n >= 100_000_000) return (n / 100_000_000).toFixed(1) + "亿";
  if (n >= 10_000) return (n / 10_000).toFixed(1) + "万";
  return String(n);
}

/**
 * 实时热搜监测组件。
 *
 * 趋势方向后端没有提供，这里由**前端跨刷新对比排名**得出：记住上一轮
 * 每个标题的名次，新一轮名次前移即为上升。这样不必改后端，也不会凭空
 * 编造一个看起来像真数据的指标——首轮加载全部标记为“新上榜”。
 */
export function HotTopics({ onPick }: Props) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [source, setSource] = useState("all");
  const [intervalMs, setIntervalMs] = useState(0);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  // 上一轮的 标题 -> 名次，用于计算趋势
  const prevRanks = useRef<Map<string, number>>(new Map());
  const [trends, setTrends] = useState<Map<string, Trend>>(new Map());

  const load = useCallback((isAuto = false) => {
    setRefreshing(true);
    setState((prev) => (prev.kind === "ready" && isAuto ? prev : { kind: "loading" }));
    api
      .getHotspots()
      .then((items) => {
        const filtered = (items || []).filter((x) => x && x.title);
        const nextTrends = new Map<string, Trend>();
        const nextRanks = new Map<string, number>();
        filtered.forEach((item, index) => {
          const rank = toRank(item.rank) || index + 1;
          nextRanks.set(item.title, rank);
          const before = prevRanks.current.get(item.title);
          if (before === undefined) nextTrends.set(item.title, "new");
          else if (rank < before) nextTrends.set(item.title, "up");
          else if (rank > before) nextTrends.set(item.title, "down");
          else nextTrends.set(item.title, "flat");
        });
        prevRanks.current = nextRanks;
        setTrends(nextTrends);
        setState({ kind: "ready", items: filtered });
        setUpdatedAt(new Date());
      })
      .catch((err: ApiError) => setState({ kind: "error", message: err.message }))
      .finally(() => setRefreshing(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // 自动刷新
  useEffect(() => {
    if (!intervalMs) return;
    const timer = window.setInterval(() => load(true), intervalMs);
    return () => window.clearInterval(timer);
  }, [intervalMs, load]);

  const items = state.kind === "ready" ? state.items : [];

  const sources = useMemo(() => {
    const set = new Set(items.map((i) => i.source).filter(Boolean));
    return Array.from(set);
  }, [items]);

  const visible = useMemo(
    () => (source === "all" ? items : items.filter((i) => i.source === source)),
    [items, source]
  );

  function renderBody() {
    if (state.kind === "loading") {
      return (
        <div className="skeleton-list" aria-busy="true" aria-label="正在加载热搜">
          {Array.from({ length: 5 }).map((_, i) => (
            <div className="skeleton-row" key={i}>
              <div className="skeleton-box" style={{ width: 32, height: 32 }} />
              <div className="flex-grow-1">
                <div className="skeleton-box" style={{ width: "60%", height: 14 }} />
                <div className="skeleton-box mt-2" style={{ width: "35%", height: 12 }} />
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
          <div className="fw-semibold">热搜加载失败</div>
          <div className="text-muted small mb-3">{state.message}</div>
          <button className="btn btn-outline-primary btn-sm" type="button" onClick={() => load()}>
            重试
          </button>
        </div>
      );
    }
    if (!visible.length) {
      return (
        <div className="empty-state">
          <i className="bi bi-inbox empty-state-icon" />
          <div className="fw-semibold">暂无热搜条目</div>
          <div className="text-muted small">
            {source === "all" ? "稍后再试" : `“${platformLabel(source)}”下暂无数据，试试切换来源`}
          </div>
        </div>
      );
    }
    return (
      <div className="hotspot-list">
        {visible.map((item, index) => {
          const trend = TREND_META[trends.get(item.title) || "new"];
          const heat = formatHeat(item.score);
          const safeUrl = item.url && /^https?:\/\//i.test(item.url) ? item.url : "";
          return (
            <div key={String(item.rank) + item.title} className="hotspot-item">
              <div className="d-flex gap-3">
                <span className={"hotspot-rank" + (index < 3 ? " is-top" : "")}>
                  {toRank(item.rank) || index + 1}
                </span>
                <div className="flex-grow-1 min-w-0">
                  <button
                    type="button"
                    className="hotspot-title-btn"
                    title="点击填入关键词"
                    onClick={() => onPick(item.title)}
                  >
                    {item.title}
                  </button>
                  {item.subtitle && (
                    <div className="section-caption mt-1 text-truncate-2">{item.subtitle}</div>
                  )}
                  <div className="hotspot-tags">
                    {heat && (
                      <span className="hotspot-meta">
                        <i className="bi bi-fire" /> {heat}
                      </span>
                    )}
                    <span className={"hotspot-trend " + trend.cls}>
                      <i className={"bi " + trend.icon} /> {trend.text}
                    </span>
                    <span className="hotspot-source">{platformLabel(item.source)}</span>
                    {safeUrl && (
                      <a
                        className="hotspot-jump ms-auto"
                        href={safeUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {item.is_mock ? "打开搜索页" : "打开来源"}
                      </a>
                    )}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div className="hotspot-card card h-100">
      <div className="card-body">
        <div className="d-flex justify-content-between align-items-start gap-2 flex-wrap">
          <div>
            <h4 className="mb-0">实时热搜</h4>
            <div className="section-caption mt-1">
              {updatedAt
                ? `更新于 ${updatedAt.toLocaleTimeString("zh-CN", { hour12: false })}`
                : "尚未更新"}
              {intervalMs > 0 && " · 自动刷新中"}
            </div>
          </div>
          <button
            className="icon-btn"
            type="button"
            title="立即刷新"
            aria-label="立即刷新"
            disabled={refreshing}
            onClick={() => load()}
          >
            <i className={"bi bi-arrow-clockwise" + (refreshing ? " spin" : "")} />
          </button>
        </div>

        <div className="widget-toolbar">
          <select
            className="form-select form-select-sm"
            aria-label="来源筛选"
            value={source}
            onChange={(e) => setSource(e.target.value)}
          >
            <option value="all">全部来源</option>
            {sources.map((s) => (
              <option key={s} value={s}>
                {platformLabel(s)}
              </option>
            ))}
          </select>
          <select
            className="form-select form-select-sm"
            aria-label="刷新间隔"
            value={intervalMs}
            onChange={(e) => setIntervalMs(Number(e.target.value))}
          >
            {INTERVALS.map((i) => (
              <option key={i.value} value={i.value}>
                {i.label}刷新
              </option>
            ))}
          </select>
        </div>

        {renderBody()}
      </div>
    </div>
  );
}
