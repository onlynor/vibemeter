import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type {
  ExportItem,
  PieSlice,
  ProgressMessage,
  SearchProviderStatus,
  SearchResult,
  SourceItem,
  Summary,
  WordItem,
} from "../api/types";
import { api } from "../api/client";
import { useLlmConfig } from "../state/llmConfig";
import { LlmSidebar } from "../components/LlmSidebar";
import { LlmConfigForm } from "../components/LlmConfigForm";
import { ChatPanel } from "../components/ChatPanel";

import { SentimentPie } from "../components/Charts/SentimentPie";
import { TopWordsBar } from "../components/Charts/TopWordsBar";
import {
  escapeHtml,
  formatDateTime,
  formatSize,
  formatTaskNo,
  platformLabel,
  renderMarkdown,
} from "../lib/utils";

const STATUS_LABELS: Record<string, string> = {
  crawling: "采集中",
  preprocessing: "清洗中",
  analyzing: "情感分析",
  wordcloud: "提取短语",
  llm: "生成解读",
  completed: "已完成",
  failed: "失败",
  keepalive: "心跳",
};

const EXPORT_LABELS: Record<ExportItem["kind"], string> = {
  raw: "原始评论",
  cleaned: "清洗后评论",
  analysed: "带情感分数",
  summary: "摘要",
};

export function ResultPage() {
  const { taskId = "" } = useParams<{ taskId: string }>();
  const { config, updateField } = useLlmConfig();
  const [copied, setCopied] = useState(false);
  const copyTimerRef = useRef<number | null>(null);

  // 仪表板数据
  const [summary, setSummary] = useState<Summary | null>(null);
  const [pie, setPie] = useState<PieSlice[] | null>(null);
  const [topWords, setTopWords] = useState<WordItem[] | null>(null);
  const [exports, setExports] = useState<ExportItem[]>([]);
  const [positiveCloud, setPositiveCloud] = useState<CloudResult | null>(null);
  const [negativeCloud, setNegativeCloud] = useState<CloudResult | null>(null);
  const [xmlContext, setXmlContext] = useState("");
  const [ready, setReady] = useState(false);

  // 进度状态：任务编号与创建时间显示在顶部
  const [taskNo, setTaskNo] = useState<number | null>(null);
  const [startTime, setStartTime] = useState("");
  const [progress, setProgress] = useState<ProgressMessage>({
    status: "crawling",
    current: 0,
    total: 1,
    raw_total: 0,
    message: "建立连接...",
  });

  // 加载仪表板的统一函数：并发拉所有结果接口
  function loadDashboard() {
    Promise.all([
      api.getSummary(taskId).catch(() => null),
      api.getSentimentPie(taskId).catch(() => null),
      api.getTopWords(taskId).catch(() => null),
      api.getExports(taskId).catch(() => []),
      api.getPositiveCloud(taskId).then(
        (data): CloudResult => ({ image: data.image }),
        (e: Error): CloudResult => ({ image: "", msg: e.message })
      ),
      api.getNegativeCloud(taskId).then(
        (data): CloudResult => ({ image: data.image }),
        (e: Error): CloudResult => ({ image: "", msg: e.message })
      ),
    ]).then(([s, p, w, exp, pc, nc]) => {
      if (s) {
        setSummary(s);
        setReady(true);
        setProgress({
          status: "completed",
          current: s.total,
          total: Math.max(1, s.total),
          raw_total: s.raw_total || 0,
          message: s.raw_total
            ? `分析完成：共搜索到 ${s.raw_total} 条原始评论，清洗后保留 ${s.total} 条有效评论`
            : "任务已完成",
        });
      }
      if (p) setPie(p);
      if (w) setTopWords(w);
      setExports(exp || []);
      setPositiveCloud(pc);
      setNegativeCloud(nc);
    });
  }

  // 初始：拉状态决定是否需要 WebSocket
  useEffect(() => {
    let cancelled = false;
    api.getTaskStatus(taskId).then((status) => {
      if (cancelled) return;
      setTaskNo(status.task_no);
      setStartTime(status.start_time || "");
      if (status.status === "completed") {
        loadDashboard();
        return;
      }
      if (status.status === "failed") {
        setProgress({
          status: "failed",
          current: 1,
          total: 1,
          message: status.error || "任务失败",
        });
        return;
      }
      connectWebSocket();
    }).catch((err: Error) => {
      setProgress({
        status: "failed",
        current: 1,
        total: 1,
        message: "初始化失败: " + err.message,
      });
    });

    function connectWebSocket() {
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      const socket = new WebSocket(`${scheme}://${location.host}/ws/task/${taskId}`);
      socket.onmessage = (event) => {
        const data: ProgressMessage = JSON.parse(event.data);
        if (data.status === "keepalive") return;
        // 合并而不是整体替换：并非每条推送都带齐所有字段（失败推送就没有
        // current/total），整体替换会把它们变成 undefined，直接渲染成
        // “目前搜索到 undefined 条”。
        setProgress((prev) => ({ ...prev, ...data }));
        if (data.status === "completed") {
          socket.close();
          loadDashboard();
        } else if (data.status === "failed") {
          socket.close();
        }
      };
      socket.onerror = () => {
        setProgress((prev) => ({ ...prev, message: "WebSocket 连接异常，正在等待任务状态..." }));
      };
      // 组件卸载时关闭
      const onUnload = () => socket.close();
      window.addEventListener("beforeunload", onUnload);
      // 保存以便 cleanup
      socketRef.current = socket;
    }

    return () => {
      cancelled = true;
      if (socketRef.current) socketRef.current.close();
      window.removeEventListener("beforeunload", () => {});
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId]);

  const socketRef = useRef<WebSocket | null>(null);

  // 拉取 XML 上下文
  useEffect(() => {
    if (!ready) return;
    api.getXmlContext(taskId).then((data) => setXmlContext(data.xml)).catch(() => {
      setXmlContext("加载失败");
    });
  }, [ready, taskId]);

  function copyXml() {
    if (!xmlContext) return;
    const w = window as any;
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(xmlContext).then(flashCopied);
    } else if (w.document) {
      // 降级
      const ta = document.createElement("textarea");
      ta.value = xmlContext;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); flashCopied(); } catch { /* ignore */ }
      document.body.removeChild(ta);
    }
  }

  function flashCopied() {
    setCopied(true);
    if (copyTimerRef.current) window.clearTimeout(copyTimerRef.current);
    copyTimerRef.current = window.setTimeout(() => setCopied(false), 1500);
  }

  const isFinished = progress.status === "completed" || progress.status === "failed";
  const label = STATUS_LABELS[progress.status] || progress.status || "准备中";
  const progressWidth =
    progress.status === "completed" || progress.status === "failed"
      ? 100
      : Math.min(100, Math.round((progress.current / Math.max(1, progress.total)) * 100));

  return (
    <LlmSidebar
      title={<><i className="bi bi-stars me-2" />LLM 对话</>}
      sidebar={
        <>
          <details className="llm-sidebar-settings mb-3">
            <summary className="fw-semibold small text-muted">连接配置（已保存于本地）</summary>
            <LlmConfigForm config={config} updateField={updateField} variant="compact" />
          </details>
          <ChatPanel taskId={taskId} config={config} />
        </>
      }
      main={
        <div id="dashboard-root" data-task-id={taskId}>
          {/* 顶部任务标题 */}
          <div className="d-flex flex-wrap justify-content-between align-items-center mb-3">
            <div>
              <h3 className="fw-bold mb-0">分析仪表板</h3>
              <small className="text-muted">
                <span>任务编号 {formatTaskNo(taskNo)}</span>
                {startTime && (
                  <span className="ms-2">创建于 {formatDateTime(startTime)}</span>
                )}
              </small>
            </div>
            <div className="mt-2 mt-md-0">
              <Link className="btn btn-outline-secondary btn-sm" to="/">
                <i className="bi bi-plus-circle" /> 新建任务
              </Link>
            </div>
          </div>

          {/* 进度条 */}
          <div className="card border-0 shadow-sm mb-4">
            <div className="card-body">
              <div className="d-flex justify-content-between align-items-center mb-2">
                <strong>
                  {!isFinished && <span className="dot-pulse" />} {label}
                </strong>
                <span className="text-muted small">
                  {progress.status === "failed"
                    ? ""
                    : progress.status === "completed" && progress.raw_total
                    ? `搜索到 ${progress.raw_total} 条，采集 ${progress.current ?? 0} 条`
                    : (progress.status === "analyzing" || progress.status === "wordcloud" || progress.status === "llm") && progress.raw_total
                    ? `搜索到 ${progress.raw_total} 条，保留 ${progress.current ?? 0} 条`
                    : `目前搜索到 ${progress.current ?? 0} 条`}
                </span>
              </div>
              <div className="progress progress-tall">
                <div
                  className={
                    "progress-bar" +
                    (progress.status === "completed"
                      ? " bg-success"
                      : progress.status === "failed"
                      ? " bg-danger"
                      : " progress-bar-striped progress-bar-animated")
                  }
                  style={{ width: progressWidth + "%" }}
                />
              </div>
              <div className="text-muted small mt-2">{progress.message || ""}</div>
            </div>
          </div>

          {ready && summary && (
            <div id="dashboard-ready">
              {/* 模型上下文 XML */}
              <div className="card border-0 shadow-sm mb-3">
                <div className="card-body p-4">
                  <div className="d-flex justify-content-between align-items-center mb-2 flex-wrap gap-2">
                    <h5 className="card-title fw-bold mb-0">模型上下文（XML）</h5>
                    <button className="btn btn-outline-secondary btn-sm" type="button" onClick={copyXml}>
                      {copied ? (
                        <><i className="bi bi-check2 me-1" />已复制</>
                      ) : (
                        <><i className="bi bi-clipboard me-1" />复制</>
                      )}
                    </button>
                  </div>
                  <details className="mt-2 llm-context-box">
                    <summary className="text-muted small">展开 / 收起</summary>
                    <pre className="mb-0">{xmlContext || "加载中..."}</pre>
                  </details>
                </div>
              </div>

              {/* 统计卡片 */}
              <div className="row g-3 mb-3">
                <StatCard label="有效评论数" value={String(summary.total)} />
                <StatCard label="耗时" value={summary.elapsed + "s"} />
                <StatCard label="关键词" value={summary.keyword || "-"} />
                <StatCard label="数据源" value={platformLabel(summary.platform)} />
              </div>

              {/* 样本构成：多源聚合时才有意义 */}
              <SourceMix stats={summary.source_stats} />

              {/* 搜索引擎检索结果（背景资料，不计入情感分析） */}
              <SearchResultsCard
                results={summary.search_results}
                status={summary.search_status}
              />

              {/* 原帖 / 原视频 */}
              {summary.source_items && summary.source_items.length > 0 && (
                <SourceCard items={summary.source_items} />
              )}

              {/* LLM 解读 */}
              {summary.llm_insight && (
                (summary.llm_insight.title || summary.llm_insight.answer || summary.llm_insight.question) && (
                  <InsightCard insight={summary.llm_insight} />
                )
              )}

              {/* 图表 */}
              <div className="row g-3">
                <div className="col-lg-5">
                  <div className="card border-0 shadow-sm h-100">
                    <div className="card-body">
                      <h5 className="card-title fw-bold">情感分布</h5>
                      {pie && <SentimentPie data={pie} />}
                    </div>
                  </div>
                </div>
                <div className="col-lg-7">
                  <div className="card border-0 shadow-sm h-100">
                    <div className="card-body">
                      <h5 className="card-title fw-bold">全量高频词 Top 15</h5>
                      {topWords && <TopWordsBar data={topWords} />}
                    </div>
                  </div>
                </div>
              </div>

              {/* 词云 */}
              <div className="row g-3 mt-1">
                <div className="col-12">
                  <div className="card border-0 shadow-sm">
                    <div className="card-body">
                      <h5 className="card-title fw-bold mb-1">观点词云（仅作参考）</h5>
                      <div className="text-muted small mb-3">
                        短语抽取与情感权重属于启发式结果，适合快速浏览，不代表严格人工标注结论。
                      </div>
                      <div className="row g-3">
                        <CloudPanel kind="positive" state={positiveCloud} />
                        <CloudPanel kind="negative" state={negativeCloud} />
                      </div>
                    </div>
                  </div>
                </div>
                <CommentList
                  title="最正面评论"
                  icon="bi-chat-heart"
                  textClass="text-success"
                  items={summary.top_positive || []}
                  flavor="positive"
                />
                <CommentList
                  title="最负面评论"
                  icon="bi-chat-x"
                  textClass="text-danger"
                  items={summary.top_negative || []}
                  flavor="negative"
                />
              </div>

              {/* 下载归档 */}
              {exports.length > 0 && (
                <div className="card border-0 shadow-sm mt-3">
                  <div className="card-body">
                    <h5 className="card-title fw-bold"><i className="bi bi-download" /> 下载数据归档</h5>
                    <div className="d-flex flex-wrap gap-2">
                      {exports.map((item) => (
                        <a
                          key={item.kind}
                          className="export-btn"
                          href={item.url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          <i className="bi bi-file-earmark-arrow-down" />{" "}
                          {EXPORT_LABELS[item.kind] || item.kind}{" "}
                          <span className="text-muted small">({formatSize(item.size || 0)})</span>
                        </a>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      }
    />
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="col-md-3 col-6">
      <div className="card stat-card border-0 shadow-sm h-100">
        <div className="card-body">
          <div className="text-muted small">{label}</div>
          <div className="display-6 fw-bold">{value}</div>
        </div>
      </div>
    </div>
  );
}

/** 搜索引擎检索结果。
 *
 * 与"原帖/原视频"分开成卡：那些是评论的出处，而这些是事件背景资料，
 * 不参与情感分析。标题上明确写出来，免得把两者当成同一类数据看。
 */
function SearchResultsCard({
  results,
  status,
}: {
  results?: SearchResult[];
  status?: SearchProviderStatus[];
}) {
  const items = results || [];
  const failed = (status || []).filter((s) => !s.ok);
  if (items.length === 0 && failed.length === 0) return null;

  return (
    <div className="card border-0 shadow-sm mb-3">
      <div className="card-body p-4">
        <h5 className="card-title fw-bold mb-1">
          <i className="bi bi-search me-2" />搜索引擎结果
        </h5>
        <div className="text-muted small mb-3">
          作为事件背景提供给模型，不计入情感分析
        </div>

        {failed.length > 0 && (
          <div className="alert alert-warning py-2 px-3 small mb-3">
            {failed.map((s) => (
              <div key={s.provider}>
                {s.label}：{s.message}
              </div>
            ))}
          </div>
        )}

        <ol className="list-unstyled mb-0">
          {items.map((item) => (
            <li key={`${item.source}-${item.rank}-${item.url}`} className="mb-3">
              <div className="d-flex align-items-start gap-2">
                <span className="badge bg-secondary flex-shrink-0">
                  {platformLabel(item.source)} #{item.rank}
                </span>
                <div className="min-w-0">
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="fw-semibold d-block text-break"
                  >
                    {item.title}
                  </a>
                  {item.snippet && (
                    <div className="text-muted small mt-1 text-break">{item.snippet}</div>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

/** 各来源在本次样本里的占比。
 *
 * 聚合搜索最容易出问题的地方是"五源"其实几乎全来自一个平台——总数
 * 看不出来，情感分布却已经变成了那个平台的分布。单源任务构成是平凡的，
 * 所以只在真的有多个来源时才渲染。
 */
function SourceMix({ stats }: { stats?: Record<string, number> }) {
  const entries = Object.entries(stats || {})
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1]);
  if (entries.length < 2) return null;
  const total = entries.reduce((sum, [, n]) => sum + n, 0);

  return (
    <div className="card border-0 shadow-sm mb-3">
      <div className="card-body p-4">
        <h5 className="card-title fw-bold mb-1">样本构成</h5>
        <div className="text-muted small mb-3">
          采集阶段各来源贡献的原始条数（去重、清洗前），共 {total} 条
        </div>
        <div className="progress mb-3" style={{ height: 10 }} role="img"
             aria-label={entries.map(([p, n]) => `${platformLabel(p)} ${n} 条`).join("，")}>
          {entries.map(([platform, n], i) => (
            <div
              key={platform}
              className={"progress-bar " + SOURCE_MIX_CLASSES[i % SOURCE_MIX_CLASSES.length]}
              style={{ width: (n / total) * 100 + "%" }}
              title={`${platformLabel(platform)} ${n} 条`}
            />
          ))}
        </div>
        <div className="d-flex flex-wrap gap-3">
          {entries.map(([platform, n], i) => (
            <div key={platform} className="d-flex align-items-center small">
              <span
                className={
                  "d-inline-block rounded me-2 " +
                  SOURCE_MIX_CLASSES[i % SOURCE_MIX_CLASSES.length]
                }
                style={{ width: 10, height: 10 }}
              />
              <span className="fw-semibold me-1">{platformLabel(platform)}</span>
              <span className="text-muted">
                {n} 条 · {((n / total) * 100).toFixed(0)}%
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const SOURCE_MIX_CLASSES = [
  "bg-primary",
  "bg-success",
  "bg-warning",
  "bg-info",
  "bg-secondary",
];

function SourceCard({ items }: { items: SourceItem[] }) {
  const [embedUrl, setEmbedUrl] = useState<string | null>(null);
  useEffect(() => {
    const first = items.find((x) => x.embed_url);
    if (first?.embed_url) setEmbedUrl(first.embed_url);
  }, [items]);

  return (
    <div className="card border-0 shadow-sm mb-3">
      <div className="card-body p-4">
        <h5 className="card-title fw-bold mb-0">原帖 / 原视频</h5>
        <div className="row g-3 mt-1">
          <div className="col-lg-7">
            {items.map((item, idx) => (
              <div key={idx} className="source-item-card">
                <div className="d-flex justify-content-between align-items-start gap-3">
                  <div>
                    <div className="source-item-platform">
                      {platformLabel(item.platform || "")}
                    </div>
                    <div
                      className="source-item-title"
                      dangerouslySetInnerHTML={{ __html: escapeHtml(item.title || "原帖") }}
                    />
                    {item.subtitle && (
                      <div
                        className="source-item-subtitle"
                        dangerouslySetInnerHTML={{ __html: escapeHtml(item.subtitle) }}
                      />
                    )}
                  </div>
                  <div className="d-flex flex-wrap gap-2 justify-content-end">
                    {item.url && (
                      <a
                        className="btn btn-outline-primary btn-sm"
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        打开原页面
                      </a>
                    )}
                    {item.embed_url && (
                      <button
                        className="btn btn-primary btn-sm"
                        type="button"
                        onClick={() => setEmbedUrl(item.embed_url!)}
                      >
                        内嵌查看
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
          {embedUrl && (
            <div className="col-lg-5">
              <div className="source-embed-shell">
                <iframe
                  className="source-embed-frame"
                  src={embedUrl}
                  allowFullScreen
                  referrerPolicy="strict-origin-when-cross-origin"
                  title="原帖内嵌查看"
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function InsightCard({ insight }: { insight: NonNullable<Summary["llm_insight"]> }) {
  return (
    <div className="card border-0 shadow-sm mb-3">
      <div className="card-body p-4">
        <div className="d-flex align-items-center gap-2 mb-2">
          <span className="insight-kicker">LLM</span>
        </div>
        {insight.question && (
          <div className="question-chip mb-3" dangerouslySetInnerHTML={{ __html: escapeHtml(insight.question) }} />
        )}
        <h4 className="fw-bold mb-2">{insight.title || ""}</h4>
        {insight.answer && (
          <div
            className="insight-body"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(insight.answer) }}
          />
        )}
        {insight.context_text && (
          <details className="mt-3 llm-context-box">
            <summary>查看发送给模型的 {(insight.context_format || "xml").toUpperCase()} 上下文</summary>
            <pre className="mb-0">{insight.context_text}</pre>
          </details>
        )}
      </div>
    </div>
  );
}

type CloudResult = { image: string; msg?: string };

function CloudPanel({ kind, state }: { kind: "positive" | "negative"; state: CloudResult | null }) {
  return (
    <div className="col-lg-6">
      <div className={"wordcloud-panel wordcloud-panel-" + kind}>
        <div className="wordcloud-header">
          <span className={"wordcloud-dot wordcloud-dot-" + kind} />
          <span className="fw-semibold">{kind === "positive" ? "正向词云" : "负向词云"}</span>
        </div>
        {state && state.image ? (
          <div className="wordcloud-frame">
            <img
              src={"data:image/png;base64," + state.image}
              alt={kind === "positive" ? "正向词云" : "负向词云"}
              className="wordcloud-image"
            />
          </div>
        ) : (
          <div className="text-muted small">
            {state?.msg || "未生成"}
          </div>
        )}
      </div>
    </div>
  );
}

function CommentList({
  title,
  icon,
  textClass,
  items,
  flavor,
}: {
  title: string;
  icon: string;
  textClass: string;
  items: { score: number; text: string }[];
  flavor: "positive" | "negative";
}) {
  return (
    <div className="col-md-6">
      <div className="card border-0 shadow-sm h-100">
        <div className="card-body">
          <h5 className={"card-title fw-bold " + textClass}>
            <i className={"bi " + icon} /> {title}
          </h5>
          {items.map((item, idx) => (
            <div key={idx} className={"comment-item " + flavor}>
              <div className="comment-score">情感得分: {item.score}</div>
              <div dangerouslySetInnerHTML={{ __html: escapeHtml(item.text) }} />
            </div>
          ))}
          {!items.length && <div className="text-muted small">暂无数据</div>}
        </div>
      </div>
    </div>
  );
}