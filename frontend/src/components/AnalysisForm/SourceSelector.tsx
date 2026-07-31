import { SOURCES, type SourceMeta } from "../../state/analysisForm";
import { platformLabel } from "../../lib/utils";
import type { Platform } from "../../api/types";

interface Props {
  selected: string[];
  onToggle: (id: string) => void;
  /** 折叠后实际发给后端的 platform，用于向用户说明真实行为 */
  resolvedPlatform: Platform;
  crawlerCount: number;
}

function Group({
  title,
  caption,
  items,
  selected,
  onToggle,
}: {
  title: string;
  caption: string;
  items: SourceMeta[];
  selected: string[];
  onToggle: (id: string) => void;
}) {
  return (
    <div className="mb-3">
      <div className="d-flex align-items-baseline gap-2 mb-2">
        <span className="fw-semibold small">{title}</span>
        <span className="text-muted" style={{ fontSize: ".78rem" }}>{caption}</span>
      </div>
      <div className="source-grid">
        {items.map((item) => {
          const checked = selected.includes(item.id);
          return (
            <label
              key={item.id}
              className={
                "source-chip" +
                (checked ? " is-checked" : "") +
                (item.backed ? "" : " is-unbacked")
              }
            >
              <input
                type="checkbox"
                className="visually-hidden"
                checked={checked}
                onChange={() => onToggle(item.id)}
              />
              <i className={"bi " + item.icon} aria-hidden="true" />
              <span className="source-chip-label">{item.label}</span>
              {!item.backed && <span className="badge-soft">待接入</span>}
              <span className="source-chip-hint">{item.hint}</span>
            </label>
          );
        })}
      </div>
    </div>
  );
}

/**
 * 数据源多选。
 *
 * 后端 `TaskRequest.platform` 只接受单个值，所以这里明确告诉用户多选会被
 * 折叠成什么——不写清楚的话，用户会以为勾掉某个源就真的不会去抓它。
 */
export function SourceSelector({ selected, onToggle, resolvedPlatform, crawlerCount }: Props) {
  const crawlers = SOURCES.filter((s) => s.kind === "crawler");
  const searches = SOURCES.filter((s) => s.kind === "search");

  return (
    <div>
      <Group
        title="采集平台"
        caption="抓取网友评论，参与情感分析"
        items={crawlers}
        selected={selected}
        onToggle={onToggle}
      />
      <Group
        title="检索增强"
        caption="补充事件背景，仅供 LLM 参考，不计入情感分析"
        items={searches}
        selected={selected}
        onToggle={onToggle}
      />

      <div className="notice-inline">
        <i className="bi bi-info-circle" aria-hidden="true" />
        {crawlerCount === 0 ? (
          <span>未选择任何采集平台，将回退为聚合搜索。</span>
        ) : crawlerCount === 1 ? (
          <span>
            将以 <strong>{platformLabel(resolvedPlatform)}</strong> 单源采集。
          </span>
        ) : (
          <span>
            已选 {crawlerCount} 个平台，后端按 <strong>聚合搜索</strong> 并发抓取并均衡采样。
            {/* TODO(backend): 支持 platforms[] 才能精确只跑所选子集 */}
            精确限定子集需后端支持 <code>platforms[]</code>。
          </span>
        )}
      </div>
    </div>
  );
}
