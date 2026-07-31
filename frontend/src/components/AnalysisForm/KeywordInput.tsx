import { forwardRef } from "react";
import { SEARCH_MODES, type SearchMode } from "../../state/analysisForm";

interface Props {
  value: string;
  onChange: (value: string) => void;
  mode: SearchMode;
  onModeChange: (mode: SearchMode) => void;
}

/** 关键词输入 + 检索模式选择：一次任务最核心的两个决定 */
export const KeywordInput = forwardRef<HTMLInputElement, Props>(
  function KeywordInput({ value, onChange, mode, onModeChange }, ref) {
    return (
      <div>
        <label className="form-label fw-semibold" htmlFor="keyword">
          监测关键词
        </label>
        <div className="keyword-field">
          <i className="bi bi-search keyword-field-icon" aria-hidden="true" />
          <input
            id="keyword"
            ref={ref}
            className="form-control form-control-lg keyword-input"
            required
            maxLength={64}
            autoComplete="off"
            placeholder="例如：AI、Agent、多智能体"
            value={value}
            onChange={(e) => onChange(e.target.value)}
          />
        </div>

        <div className="form-label fw-semibold mt-4 mb-2">检索模式</div>
        <div className="mode-grid" role="radiogroup" aria-label="检索模式">
          {SEARCH_MODES.map((item) => {
            const active = item.value === mode;
            return (
              <button
                key={item.value}
                type="button"
                role="radio"
                aria-checked={active}
                className={"mode-card" + (active ? " is-active" : "")}
                onClick={() => onModeChange(item.value)}
              >
                <span className="mode-card-head">
                  <i className={"bi " + item.icon} aria-hidden="true" />
                  <span className="mode-card-title">{item.label}</span>
                  {!item.backed && <span className="badge-soft">前端预设</span>}
                </span>
                <span className="mode-card-hint">{item.hint}</span>
                <span className="mode-card-meta">建议采集 {item.count} 条</span>
              </button>
            );
          })}
        </div>
      </div>
    );
  }
);
