import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useLlmConfig } from "../state/llmConfig";
import { SEARCH_MODES, SOURCES, useAnalysisForm } from "../state/analysisForm";
import { LlmSidebar } from "../components/LlmSidebar";
import { LlmConfigForm } from "../components/LlmConfigForm";
import { SourceHealthCheck } from "../components/SourceHealthCheck";
import { KeywordInput } from "../components/AnalysisForm/KeywordInput";
import { SourceSelector } from "../components/AnalysisForm/SourceSelector";
import { RetrievalSettings } from "../components/AnalysisForm/RetrievalSettings";
import { AnalysisOptions } from "../components/AnalysisForm/AnalysisOptions";
import { HotTopics } from "../components/Dashboard/HotTopics";
import { RecentTasks } from "../components/Dashboard/RecentTasks";

/** 各类来源的总数，用于「已选 n / 共 m」的分母，避免写死数字 */
const CRAWLER_TOTAL = SOURCES.filter((s) => s.kind === "crawler").length;
const SEARCH_TOTAL = SOURCES.filter((s) => s.kind === "search" && s.provider).length;

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
        <i className="bi bi-chevron-down settings-chevron" aria-hidden="true" />
      </button>
      {open && (
        <div className="settings-section-body" id={id}>
          {children}
        </div>
      )}
    </div>
  );
}

/** 本次任务的「执行计划」小卡：全部取自当前表单状态，不是装饰性数字 */
function PlanTile({
  icon,
  label,
  value,
  hint,
  tone,
}: {
  icon: string;
  label: string;
  value: string;
  hint: string;
  tone?: "muted";
}) {
  return (
    <div className={"plan-tile" + (tone === "muted" ? " is-muted" : "")}>
      <div className="plan-tile-label">
        <i className={"bi " + icon} aria-hidden="true" />
        {label}
      </div>
      <div className="plan-tile-value">{value}</div>
      <div className="plan-tile-hint">{hint}</div>
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
  const mode = SEARCH_MODES.find((m) => m.value === form.state.mode);

  function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = form.state.keyword.trim();
    if (!trimmed) {
      setError("请输入关键词");
      keywordRef.current?.focus();
      return;
    }
    // 采集平台是评论的唯一来源，一个都不选后端只会拿到空样本。
    // 与其让任务跑到清洗阶段才失败，不如在这里说清楚。
    if (form.crawlerCount === 0) {
      setError("请至少选择一个采集平台");
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
        <div className="home-layout">
          {/* 标题与「本次任务会怎么跑」并排：右侧四块随表单实时变化 */}
          <section className="home-hero">
            <div className="home-hero-copy">
              <span className="hero-eyebrow">
                <i className="bi bi-broadcast" aria-hidden="true" />
                全网舆情监测
              </span>
              <h1 className="home-hero-title">看清一个话题下，大家究竟在说什么</h1>
              <p className="home-hero-subtitle">
                输入关键词，跨五个平台采集真实评论，自动完成清洗、情感打分与观点提炼，
                并由搜索引擎补齐事件背景
              </p>
            </div>

            <div className="home-plan" aria-label="本次任务执行计划">
              <PlanTile
                icon="bi-diagram-3"
                label="采集平台"
                value={`${form.crawlerCount} / ${CRAWLER_TOTAL}`}
                hint={form.crawlerCount > 1 ? "并发抓取 · 来源轮转" : "单源采集"}
              />
              <PlanTile
                icon="bi-list-ul"
                label="目标样本"
                value={`${form.state.count}`}
                hint={mode ? mode.label : "条评论"}
              />
              <PlanTile
                icon="bi-search"
                label="检索增强"
                value={`${form.searchCount} / ${SEARCH_TOTAL}`}
                hint={form.searchCount ? "仅作事件背景" : "已关闭"}
                tone={form.searchCount ? undefined : "muted"}
              />
              <PlanTile
                icon="bi-stars"
                label="LLM 解读"
                value={llmConfigured ? "已就绪" : "未配置"}
                hint={llmConfigured ? config.llm_model || "" : "在左侧侧栏填写"}
                tone={llmConfigured ? undefined : "muted"}
              />
            </div>
          </section>

          {/* 左：任务配置；右：实时监测栏（随页面滚动吸顶） */}
          <div className="home-grid">
            <div className="home-col-main">
              <div className="hero-card card">
                <div className="card-body">
                  <form noValidate onSubmit={onSubmit}>
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
                        caption={
                          `采集 ${form.crawlerCount} 个平台` +
                          (form.searchCount ? ` · 检索 ${form.searchCount} 个引擎` : " · 未启用检索增强")
                        }
                        defaultOpen
                      >
                        <SourceSelector
                          selected={form.state.sources}
                          onToggle={form.toggleSource}
                          resolvedPlatform={form.platform}
                          crawlerCount={form.crawlerCount}
                          searchCount={form.searchCount}
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
                    </div>

                    {error && (
                      <div className="alert alert-danger mt-4 mb-0" role="alert">
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
                        "开始分析"
                      )}
                    </button>
                  </form>
                </div>
              </div>
            </div>

            <aside className="home-rail">
              <HotTopics onPick={pickHotspot} />

              {/* 跑之前先确认谁在风控，比任务失败后再回来查要省事 */}
              <div className="card">
                <div className="card-body">
                  <div className="d-flex justify-content-between align-items-start gap-2 mb-1">
                    <div>
                      <h4 className="mb-0">数据源可用性</h4>
                      <div className="section-caption mt-1">跑之前先确认谁在风控</div>
                    </div>
                  </div>
                  <div className="mt-3">
                    <SourceHealthCheck />
                  </div>
                </div>
              </div>
            </aside>
          </div>

          <RecentTasks />
        </div>
      }
    />
  );
}
