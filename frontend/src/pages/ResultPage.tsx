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
          <div className="page-heading">
            <div>
              <h1>{summary?.keyword || "分析仪表板"}</h1>
              <div className="page-heading-meta">
                <span>任务 {formatTaskNo(taskNo)}</span>
                {startTime && <span className="ms-3">创建于 {formatDateTime(startTime)}</span>}
              </div>
            </div>
            <Link className="btn btn-outline-primary btn-sm" to="/">
              <i className="bi bi-plus-lg me-1" /> 新建任务
            </Link>
          </div>

          {/* 进度条 */}
          <div className="card mb-4">
            <div className="card-body">
              <div className="d-flex justify-content-between align-items-center mb-3">
                <strong className="fw-semibold">
                  {!isFinished && <span className="dot-pulse" />}{label}
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
              {/* 统计卡片 */}
              <div className="row g-3 mb-3">
                <StatCard label="有效评论数" value={String(summary.total)} />
                <StatCard label="耗时" value={summary.elapsed + "s"} />
                <StatCard label="关键词" value={summary.keyword || "-"} />
                <StatCard label="数据源" value={platformLabel(summary.platform)} />
              </div>

              {/* 平台内容优先：评论的出处（B站视频 / 贴吧帖 / 微博…）是用户来这一页
                  最想先看到的东西，搜索引擎结果只是背景资料，挪到页面靠后。 */}
              {summary.source_items && summary.source_items.length > 0 && (
                <SourceCard items={summary.source_items} />
              )}

              {/* 样本构成：多源聚合时才有意义 */}
              <SourceMix stats={summary.source_stats} />

              {/* 搜索引擎补充的事件背景。排在平台内容之后——它不是主角，但
                  也不该藏起来：折叠久了用户会以为百度/必应根本没跑 */}
              <SearchResultsCard
                results={summary.search_results}
                status={summary.search_status}
              />

              {/* LLM 解读 */}
              {summary.llm_insight && (
                (summary.llm_insight.title || summary.llm_insight.answer || summary.llm_insight.question) && (
                  <InsightCard insight={summary.llm_insight} />
                )
              )}

              {/* 图表 */}
              <div className="row g-3">
                <div className="col-lg-5">
                  <div className="card h-100">
                    <div className="card-body">
                      <h5 className="card-title">情感分布</h5>
                      {pie && <SentimentPie data={pie} />}
                    </div>
                  </div>
                </div>
                <div className="col-lg-7">
                  <div className="card h-100">
                    <div className="card-body">
                      <h5 className="card-title">全量高频词 Top 15</h5>
                      {topWords && <TopWordsBar data={topWords} />}
                    </div>
                  </div>
                </div>
              </div>

              {/* 词云 */}
              <div className="row g-3 mt-1">
                <div className="col-12">
                  <div className="card">
                    <div className="card-body">
                      <h5 className="card-title">观点词云（仅作参考）</h5>
                      <div className="section-caption mb-3">
                        短语抽取与情感权重属于启发式结果，适合快速浏览，不代表严格人工标注结论
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

              {/* 模型上下文 XML：调试用，正常浏览时不该占据首屏 */}
              <div className="card mt-3">
                <div className="card-body">
                  <div className="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
                    <h5 className="card-title mb-0">模型上下文（XML）</h5>
                    <button className="btn btn-outline-secondary btn-sm" type="button" onClick={copyXml}>
                      {copied ? (
                        <><i className="bi bi-check2 me-1" />已复制</>
                      ) : (
                        <><i className="bi bi-clipboard me-1" />复制</>
                      )}
                    </button>
                  </div>
                  <details className="llm-context-box">
                    <summary>展开 / 收起</summary>
                    <pre className="mb-0">{xmlContext || "加载中..."}</pre>
                  </details>
                </div>
              </div>

              {/* 下载归档 */}
              {exports.length > 0 && (
                <div className="card mt-3">
                  <div className="card-body">
                    <h5 className="card-title mb-3">下载数据归档</h5>
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
      <div className="card stat-card h-100">
        <div className="card-body">
          <div className="stat-card-label">{label}</div>
          <div className="stat-card-value">{value}</div>
        </div>
      </div>
    </div>
  );
}

/** 搜索引擎检索结果。
 *
 * 与"平台内容来源"分开成卡：那些是评论的出处，而这些只是事件背景资料，
 * 不参与情感分析——所以排在平台内容之后。但**不再默认折叠**：折起来之后
 * 用户看不到百度/必应的任何痕迹，会直接以为检索层没跑起来。
 *
 * 卡内顺序也做了一次调整：带摘要的结果排在前面。聚合层是按引擎轮转合并的
 * （见 registry._interleave），轮转保证了来源均衡，但"某某公司_百度百科"
 * 这种只有标题没有摘要的条目混在前排，等于把最有信息量的位置浪费掉。
 * 这里只做稳定的两段划分，不重排组内顺序，均衡性因此不受影响。
 */

/** 摘要短于这个长度基本等于没有内容，排到后面去 */
const SNIPPET_RICH_MIN = 40;
/** 首屏先给这么多条，其余点开再看 */
const SEARCH_PREVIEW_COUNT = 6;

function SearchResultsCard({
  results,
  status,
}: {
  results?: SearchResult[];
  status?: SearchProviderStatus[];
}) {
  const [expanded, setExpanded] = useState(false);
  const items = results || [];
  const failed = (status || []).filter((s) => !s.ok);
  if (items.length === 0 && failed.length === 0) return null;

  const rich = items.filter((i) => (i.snippet || "").length >= SNIPPET_RICH_MIN);
  const lean = items.filter((i) => (i.snippet || "").length < SNIPPET_RICH_MIN);
  const ordered = [...rich, ...lean];
  const visible = expanded ? ordered : ordered.slice(0, SEARCH_PREVIEW_COUNT);
  const engines = Array.from(new Set(items.map((i) => i.source)));

  return (
    <div className="card mb-3">
      <div className="card-body">
        <h5 className="card-title">事件背景 · 搜索引擎补充</h5>
        <div className="section-caption mb-3">
          {items.length} 条结果
          {engines.length > 0 && ` · ${engines.map(platformLabel).join(" / ")}`}
          ，作为背景资料提供给模型，不计入情感分析
        </div>

        {failed.length > 0 && (
          <div className="alert alert-warning mb-3">
            {failed.map((s) => (
              <div key={s.provider}>
                {s.label}：{s.message}
              </div>
            ))}
          </div>
        )}

        <ol className="search-result-list">
          {visible.map((item) => (
            <li key={`${item.source}-${item.rank}-${item.url}`} className="search-result-item">
              <span className="search-result-rank">
                {platformLabel(item.source)} {item.rank}
              </span>
              <div className="min-w-0">
                <a
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="search-result-title text-break"
                >
                  {item.title}
                </a>
                {item.snippet && (
                  <div className="search-result-snippet text-break">{item.snippet}</div>
                )}
                <div className="search-result-host">{hostOf(item.url)}</div>
              </div>
            </li>
          ))}
        </ol>

        {ordered.length > SEARCH_PREVIEW_COUNT && (
          <button
            className="btn btn-light btn-sm mt-2"
            type="button"
            onClick={() => setExpanded((v) => !v)}
          >
            <i className={"bi me-1 " + (expanded ? "bi-chevron-up" : "bi-chevron-down")} />
            {expanded ? "收起" : `展开全部 ${ordered.length} 条`}
          </button>
        )}
      </div>
    </div>
  );
}

/** 只显示域名：完整 URL 又长又没信息量，域名才是"这条结果可不可信"的线索 */
function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
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
    <div className="card mb-3">
      <div className="card-body">
        <h5 className="card-title">样本构成</h5>
        <div className="section-caption mb-3">
          采集阶段各来源贡献的原始条数（去重、清洗前），共 {total} 条
        </div>
        <div className="source-mix-bar" role="img"
             aria-label={entries.map(([p, n]) => `${platformLabel(p)} ${n} 条`).join("，")}>
          {entries.map(([platform, n], i) => (
            <div
              key={platform}
              style={{
                width: (n / total) * 100 + "%",
                background: SOURCE_MIX_COLORS[i % SOURCE_MIX_COLORS.length],
              }}
              title={`${platformLabel(platform)} ${n} 条`}
            />
          ))}
        </div>
        <div className="source-mix-legend">
          {entries.map(([platform, n], i) => (
            <div key={platform} className="d-flex align-items-center">
              <span
                className="source-mix-swatch"
                style={{ background: SOURCE_MIX_COLORS[i % SOURCE_MIX_COLORS.length] }}
              />
              <span className="fw-semibold me-2">{platformLabel(platform)}</span>
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

/** 定性区分用的中性色板，刻意避开情感三色，免得被误读成"这个源偏正面" */
const SOURCE_MIX_COLORS = ["#0071e3", "#5e5ce6", "#64d2ff", "#8e8e93", "#c7c7cc"];

/** 平台内容来源：评论抓自哪些帖子 / 视频。
 *
 * 这张卡紧跟统计卡片，排在搜索引擎结果之前——评论的出处才是本页主角。
 * 第一条可内嵌的内容默认展开播放器：它就在首屏视野里，用户搜完立刻能看到
 * 视频本身；其余条目点了才挂载 iframe，收起时 iframe 一并卸载（声音随之停）。
 */
function SourceCard({ items }: { items: SourceItem[] }) {
  const firstEmbeddable = items.findIndex((x) => x.embed_url);
  const [playing, setPlaying] = useState<number | null>(
    firstEmbeddable >= 0 ? firstEmbeddable : null
  );

  // 顶部先列出涉及的平台，"这些内容来自哪儿"一眼看清
  const platforms = Array.from(
    new Set(items.map((x) => x.platform).filter(Boolean))
  ) as string[];

  return (
    <div className="card mb-3">
      <div className="card-body">
        <h5 className="card-title">平台内容来源</h5>
        <div className="section-caption mb-3">
          本次评论抓自以下帖子 / 视频
          {platforms.length > 0 && `：${platforms.map(platformLabel).join(" · ")}`}
        </div>

        <div className="row g-3">
          {items.map((item, idx) => {
            const open = playing === idx;
            return (
              <div className="col-xl-6" key={idx}>
                <div className={"source-item-card" + (open ? " is-open" : "")}>
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

                  <div className="source-item-actions">
                    {item.url && (
                      <a
                        className="btn btn-outline-primary btn-sm"
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        <i className="bi bi-box-arrow-up-right me-1" />
                        打开原页面
                      </a>
                    )}
                    {item.embed_url && (
                      <button
                        className={"btn btn-sm " + (open ? "btn-light" : "btn-primary")}
                        type="button"
                        onClick={() => setPlaying(open ? null : idx)}
                      >
                        <i className={"bi me-1 " + (open ? "bi-x-lg" : "bi-play-fill")} />
                        {open ? "收起播放器" : "内嵌播放"}
                      </button>
                    )}
                  </div>

                  {open && item.embed_url && (
                    <div className="source-embed-shell mt-3">
                      <iframe
                        className="source-embed-frame"
                        src={item.embed_url}
                        allowFullScreen
                        referrerPolicy="strict-origin-when-cross-origin"
                        title={item.title || "原帖内嵌查看"}
                      />
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function InsightCard({ insight }: { insight: NonNullable<Summary["llm_insight"]> }) {
  return (
    <div className="card mb-3">
      <div className="card-body">
        <div className="d-flex align-items-center gap-2 mb-2">
          <span className="insight-kicker">LLM</span>
        </div>
        {insight.question && (
          <div className="question-chip mb-3" dangerouslySetInnerHTML={{ __html: escapeHtml(insight.question) }} />
        )}
        <h4 className="mb-3">{insight.title || ""}</h4>
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
      <div className="card h-100">
        <div className="card-body">
          <h5 className={"card-title mb-3 " + textClass}>
            <i className={"bi " + icon + " me-2"} />{title}
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