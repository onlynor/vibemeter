import {
  LLM_ANALYSIS_TYPES,
  SENTIMENT_GRANULARITIES,
  type LlmAnalysisType,
  type SentimentGranularity,
} from "../../state/analysisForm";

interface Props {
  sentimentEnabled: boolean;
  onSentimentEnabledChange: (value: boolean) => void;
  granularity: SentimentGranularity;
  onGranularityChange: (value: SentimentGranularity) => void;
  llmAnalysis: LlmAnalysisType;
  onLlmAnalysisChange: (value: LlmAnalysisType) => void;
  /** LLM 未配置时提示用户分析类型不会生效 */
  llmConfigured: boolean;
}

/** 分析选项：情感分析与 LLM 解读方式 */
export function AnalysisOptions({
  sentimentEnabled,
  onSentimentEnabledChange,
  granularity,
  onGranularityChange,
  llmAnalysis,
  onLlmAnalysisChange,
  llmConfigured,
}: Props) {
  const activeType = LLM_ANALYSIS_TYPES.find((t) => t.value === llmAnalysis);

  return (
    <div className="row g-4">
      <div className="col-lg-6">
        <div className="d-flex align-items-center justify-content-between">
          <label className="form-label fw-semibold mb-0" htmlFor="sentiment-toggle">
            情感分析
          </label>
          <div className="form-check form-switch mb-0">
            <input
              id="sentiment-toggle"
              className="form-check-input"
              type="checkbox"
              role="switch"
              checked={sentimentEnabled}
              onChange={(e) => onSentimentEnabledChange(e.target.checked)}
            />
          </div>
        </div>
        <div className="text-muted small mt-1">
          {sentimentEnabled
            ? "对清洗后的评论逐条打分并统计分布"
            : "关闭后仅采集与检索，不做情感统计"}
        </div>
        {/* TODO(backend): 关闭开关需要后端支持跳过 analyze_batch，当前流水线恒执行 */}
        {!sentimentEnabled && (
          <div className="notice-inline mt-2">
            <i className="bi bi-exclamation-circle" aria-hidden="true" />
            <span>后端目前恒执行情感分析，此开关仅影响本页展示偏好。</span>
          </div>
        )}

        <label className="form-label fw-semibold mt-3" htmlFor="granularity">
          情感粒度
        </label>
        <select
          id="granularity"
          className="form-select"
          value={granularity}
          disabled={!sentimentEnabled}
          onChange={(e) => onGranularityChange(e.target.value as SentimentGranularity)}
        >
          {SENTIMENT_GRANULARITIES.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
              {item.backed ? "" : "（待接入）"}
            </option>
          ))}
        </select>
        <div className="text-muted small mt-2">
          {SENTIMENT_GRANULARITIES.find((g) => g.value === granularity)?.hint}
        </div>
      </div>

      <div className="col-lg-6">
        <label className="form-label fw-semibold">LLM 分析类型</label>
        <div className="option-list" role="radiogroup" aria-label="LLM 分析类型">
          {LLM_ANALYSIS_TYPES.map((item) => {
            const active = item.value === llmAnalysis;
            return (
              <button
                key={item.value}
                type="button"
                role="radio"
                aria-checked={active}
                className={"option-row" + (active ? " is-active" : "")}
                onClick={() => onLlmAnalysisChange(item.value)}
              >
                <span className="option-row-title">{item.label}</span>
                <span className="option-row-hint">{item.hint}</span>
              </button>
            );
          })}
        </div>
        {activeType && (
          <div className="notice-inline mt-2">
            <i className={llmConfigured ? "bi bi-check2-circle" : "bi bi-info-circle"} aria-hidden="true" />
            <span>
              {llmConfigured ? (
                <>将作为提问模板：「{activeType.template}」</>
              ) : (
                <>未配置 LLM，本项不会生效；可在左侧侧栏填写 Base URL 与模型。</>
              )}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
