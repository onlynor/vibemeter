import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useLlmConfig } from "../state/llmConfig";
import { useAnalysisForm } from "../state/analysisForm";
import { LlmSidebar } from "../components/LlmSidebar";
import { LlmConfigForm } from "../components/LlmConfigForm";
import { SourceHealthCheck } from "../components/SourceHealthCheck";
import { KeywordInput } from "../components/AnalysisForm/KeywordInput";
import { SourceSelector } from "../components/AnalysisForm/SourceSelector";
import { RetrievalSettings } from "../components/AnalysisForm/RetrievalSettings";
import { AnalysisOptions } from "../components/AnalysisForm/AnalysisOptions";
import { HotTopics } from "../components/Dashboard/HotTopics";
import { RecentTasks } from "../components/Dashboard/RecentTasks";

/** 可折叠的设置分区，避免高级选项一次性铺满首屏 */
function Section({
  id,
  icon,
  title,
  caption,
  defaultOpen = false,
  children,
}: {
  id: string;
  icon: string;
  title: string;
  caption: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={"settings-section" + (open ? " is-open" : "")}>
      <button
        type="button"
        className="settings-section-head"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((v) => !v)}
      >
        <i className={"bi " + icon + " settings-section-icon"} aria-hidden="true" />
        <span className="flex-grow-1 text-start">
          <span className="settings-section-title">{title}</span>
          <span className="settings-section-caption">{caption}</span>
        </span>
        <i className={"bi bi-chevron-down settings-chevron"} aria-hidden="true" />
      </button>
      {open && (
        <div className="settings-section-body" id={id}>
          {children}
        </div>
      )}
    </div>
  );
}

export function HomePage() {
  const navigate = useNavigate();
  const { config, updateField } = useLlmConfig();
  const form = useAnalysisForm();
  const keywordRef = useRef<HTMLInputElement | null>(null);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const llmConfigured = Boolean(
    config.llm_base_url?.trim() && config.llm_model?.trim()
  );

  function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = form.state.keyword.trim();
    if (!trimmed) {
      setError("请输入关键词");
      keywordRef.current?.focus();
      return;
    }
    setError(null);
    setSubmitting(true);

    api
      .createTask(form.buildTaskRequest(config))
      .then((data) => {
        if (!data?.task_id) throw new Error("任务创建失败");
        navigate("/result/" + data.task_id);
      })
      .catch((err: ApiError | Error) => {
        setSubmitting(false);
        setError("任务创建失败：" + err.message);
      });
  }

  function pickHotspot(title: string) {
    form.update("keyword", title);
    keywordRef.current?.focus();
    keywordRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  return (
    <LlmSidebar
      title={<><i className="bi bi-stars me-2" />LLM 配置</>}
      sidebar={<LlmConfigForm config={config} updateField={updateField} />}
      main={
        <div className="home-dashboard">
          {/* 主分析面板 */}
          <div className="hero-card card border-0 shadow-lg mb-4">
            <div className="card-body p-4 p-md-5">
              <div className="d-flex align-items-center mb-2">
                <i className="bi bi-broadcast-pin hero-icon" />
                <div className="ms-3">
                  <h2 className="card-title fw-bold mb-0">舆情监测台</h2>
                  <p className="text-muted mb-0 small">
                    输入关键词，跨平台采集评论并完成情感与 LLM 解读
                  </p>
                </div>
              </div>

              <form noValidate onSubmit={onSubmit} className="mt-4">
                <KeywordInput
                  ref={keywordRef}
                  value={form.state.keyword}
                  onChange={(v) => form.update("keyword", v)}
                  mode={form.state.mode}
                  onModeChange={form.setMode}
                />

                <div className="settings-stack mt-4">
                  <Section
                    id="sec-sources"
                    icon="bi-diagram-3"
                    title="数据源"
                    caption={`已启用 ${form.state.sources.length} 个来源`}
                    defaultOpen
                  >
                    <SourceSelector
                      selected={form.state.sources}
                      onToggle={form.toggleSource}
                      resolvedPlatform={form.platform}
                      crawlerCount={form.crawlerCount}
                    />
                  </Section>

                  <Section
                    id="sec-retrieval"
                    icon="bi-sliders"
                    title="高级检索设置"
                    caption={`采集 ${form.state.count} 条`}
                  >
                    <RetrievalSettings
                      count={form.state.count}
                      onCountChange={(v) => form.update("count", v)}
                      ranking={form.state.ranking}
                      onRankingChange={(v) => form.update("ranking", v)}
                    />
                  </Section>

                  <Section
                    id="sec-analysis"
                    icon="bi-graph-up"
                    title="分析选项"
                    caption={form.state.sentimentEnabled ? "情感分析已开启" : "情感分析已关闭"}
                  >
                    <AnalysisOptions
                      sentimentEnabled={form.state.sentimentEnabled}
                      onSentimentEnabledChange={(v) => form.update("sentimentEnabled", v)}
                      granularity={form.state.granularity}
                      onGranularityChange={(v) => form.update("granularity", v)}
                      llmAnalysis={form.state.llmAnalysis}
                      onLlmAnalysisChange={(v) => form.update("llmAnalysis", v)}
                      llmConfigured={llmConfigured}
                    />
                  </Section>

                  <Section
                    id="sec-health"
                    icon="bi-activity"
                    title="数据源可用性"
                    caption="跑之前先确认谁在风控"
                  >
                    <SourceHealthCheck />
                  </Section>
                </div>

                {error && (
                  <div className="alert alert-danger py-2 px-3 small mt-3 mb-0" role="alert">
                    <i className="bi bi-exclamation-triangle me-2" />
                    {error}
                  </div>
                )}

                <button
                  className="btn btn-primary btn-lg w-100 mt-4"
                  type="submit"
                  disabled={submitting}
                >
                  {submitting ? (
                    <>
                      <span className="spinner-border spinner-border-sm me-2" role="status" />
                      正在创建任务...
                    </>
                  ) : (
                    <>
                      <i className="bi bi-graph-up-arrow me-2" />
                      开始分析
                    </>
                  )}
                </button>
              </form>
            </div>
          </div>

          {/* 监测面板 */}
          <div className="row g-4">
            <div className="col-xl-6">
              <HotTopics onPick={pickHotspot} />
            </div>
            <div className="col-xl-6">
              <RecentTasks />
            </div>
          </div>
        </div>
      }
    />
  );
}
