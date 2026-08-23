import { RANKING_STRATEGIES, type RankingStrategy } from "../../state/analysisForm";

interface Props {
  count: number;
  onCountChange: (value: number) => void;
  ranking: RankingStrategy;
  onRankingChange: (value: RankingStrategy) => void;
}

const MIN = 300;
const MAX = 2000;

/** 高级检索设置：采集量与排序策略 */
export function RetrievalSettings({ count, onCountChange, ranking, onRankingChange }: Props) {
  const active = RANKING_STRATEGIES.find((r) => r.value === ranking);

  return (
    <div className="row g-4">
      <div className="col-lg-6">
        <label className="form-label fw-semibold" htmlFor="count">
          采集数量
          <span className="text-muted fw-normal ms-2">{count} 条</span>
        </label>
        <input
          id="count"
          type="range"
          className="form-range"
          min={MIN}
          max={MAX}
          step={50}
          value={count}
          onChange={(e) => onCountChange(Number(e.target.value) || MIN)}
        />
        <div className="d-flex justify-content-between text-muted" style={{ fontSize: ".75rem" }}>
          <span>{MIN}</span>
          <span>{MAX}</span>
        </div>
        <input
          type="number"
          className="form-control mt-2"
          min={MIN}
          max={MAX}
          step={50}
          value={count}
          aria-label="采集数量精确值"
          onChange={(e) => {
            const raw = Number(e.target.value);
            if (!raw) return onCountChange(MIN);
            onCountChange(Math.min(MAX, Math.max(MIN, raw)));
          }}
        />
      </div>

      <div className="col-lg-6">
        <label className="form-label fw-semibold" htmlFor="ranking">
          结果排序策略
          <span className="badge-soft ms-2">前端预设</span>
        </label>
        <select
          id="ranking"
          className="form-select"
          value={ranking}
          onChange={(e) => onRankingChange(e.target.value as RankingStrategy)}
        >
          {RANKING_STRATEGIES.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
        {active && <div className="text-muted small mt-2">{active.hint}</div>}
        {/* TODO(backend): 排序需要后端在合并结果时实现，当前仅保存偏好 */}
        <div className="notice-inline mt-2">
          <i className="bi bi-hourglass-split" aria-hidden="true" />
          <span>
            后端暂未实现排序策略，当前结果按<strong>来源轮转</strong>合并；此处仅保存偏好
          </span>
        </div>
      </div>
    </div>
  );
}
