import { SOURCES, type SourceMeta } from "../../state/analysisForm";
import { platformLabel } from "../../lib/utils";
import type { Platform } from "../../api/types";

interface Props {
  selected: string[];
  onToggle: (id: string) => void;
  /** 实际发给后端的 platform，用于向用户说明真实行为 */
  resolvedPlatform: Platform;
  crawlerCount: number;
  searchCount: number;
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
    <div className="source-group">
      <div className="source-group-head">
        <span className="source-group-title">{title}</span>
        <span className="source-group-caption">{caption}</span>
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
              <i className={"bi " + item.icon + " source-chip-icon"} aria-hidden="true" />
              <span className="source-chip-label">{item.label}</span>
              {!item.backed && <span className="badge-soft">待接入</span>}
              <span className="source-chip-hint">{item.hint}</span>
              <span className="source-chip-check" aria-hidden="true">
                <i className="bi bi-check" />
              </span>
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
 * 勾选是真生效的：采集平台随 `platforms[]` 发给后端，聚合爬虫只会启动被勾中
 * 的源；检索源随 `search_providers[]` 发出，一个都不勾就是关掉检索增强。
 */
export function SourceSelector({
  selected,
  onToggle,
  resolvedPlatform,
  crawlerCount,
  searchCount,
}: Props) {
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

      <div className={"notice-inline" + (crawlerCount === 0 ? " is-warning" : "")}>
        <i
          className={"bi " + (crawlerCount === 0 ? "bi-exclamation-triangle" : "bi-info-circle")}
          aria-hidden="true"
        />
        {crawlerCount === 0 ? (
          <span>请至少选择一个采集平台，否则没有评论可供分析</span>
        ) : crawlerCount === 1 ? (
          <span>
            将以 <strong>{platformLabel(resolvedPlatform)}</strong> 单源采集
            {searchCount > 0 ? `，并用 ${searchCount} 个搜索引擎补充背景` : "，不使用检索增强"}
          </span>
        ) : (
          <span>
            将并发抓取 <strong>{crawlerCount} 个平台</strong>并按来源轮转均衡采样
            {searchCount > 0 ? `，另有 ${searchCount} 个搜索引擎补充背景` : "，不使用检索增强"}
          </span>
        )}
      </div>
    </div>
  );
}
