import { useCallback, useEffect, useMemo, useState } from "react";
import type { LLMConfig, Platform, TaskRequest } from "../api/types";

/**
 * 首页分析表单的集中状态。
 *
 * 这里的选项分两类，`backed` 字段就是这条界线：
 *
 * - **backed: true** —— 能映射到真实请求字段（检索模式→count、采集平台→
 *   platform + platforms[]、检索源→search_providers[]、LLM 分析类型→
 *   llm_question 模板）。
 * - **backed: false** —— 后端尚无对应能力，仅保存前端偏好，UI 上标注
 *   “前端预设”，不谎称已生效。见文件内 TODO(backend)。
 *
 * 数据源多选此前是 backed: false 的重灾区：后端只收单个 platform，勾掉一个
 * 平台并不会真的不去抓它。现在 `POST /api/task` 接受 `platforms[]` 与
 * `search_providers[]`，这两组勾选才名副其实。
 */

const STORAGE_KEY = "vibe.home.form.v1";

export type SearchMode = "quick" | "deep" | "monitor";
export type RankingStrategy = "latest" | "popularity" | "diversity" | "relevance";
export type SentimentGranularity = "overall" | "polarity" | "emotions";
export type LlmAnalysisType = "summary" | "trend" | "events" | "risk" | "opinion";

export interface OptionMeta<T extends string> {
  value: T;
  label: string;
  hint: string;
  icon?: string;
  /** 后端是否真的支持；false 表示仅前端偏好 */
  backed: boolean;
}

export const SEARCH_MODES: (OptionMeta<SearchMode> & { count: number })[] = [
  {
    value: "quick",
    label: "快速分析",
    hint: "采集量小、出结果快，适合日常监测",
    icon: "bi-lightning-charge",
    backed: true,
    count: 300,
  },
  {
    value: "deep",
    label: "深度研究",
    hint: "更多来源与样本，LLM 摘要更充分",
    icon: "bi-binoculars",
    backed: true,
    count: 1500,
  },
  {
    value: "monitor",
    label: "实时监测",
    hint: "定时重跑，跟踪趋势变化",
    icon: "bi-broadcast",
    // 定时重跑目前由前端计时器驱动，后端没有常驻任务概念
    backed: false,
    count: 500,
  },
];

export interface SourceMeta {
  id: string;
  label: string;
  icon: string;
  /** crawler = 参与评论采集；search = 检索增强（背景资料） */
  kind: "crawler" | "search";
  /** 对应后端 platform 值；null 表示后端无此采集源 */
  platform: Platform | null;
  /** 对应后端 search provider 的 name（app/search/*.py 里的 `name`） */
  provider: string | null;
  backed: boolean;
  hint: string;
}

export const SOURCES: SourceMeta[] = [
  { id: "weibo", label: "微博", icon: "bi-chat-quote", kind: "crawler", platform: "weibo", provider: null, backed: true, hint: "需配置 Cookie" },
  { id: "douban", label: "豆瓣", icon: "bi-film", kind: "crawler", platform: "douban", provider: null, backed: true, hint: "影视 / 图书短评" },
  { id: "tieba", label: "贴吧", icon: "bi-people", kind: "crawler", platform: "tieba", provider: null, backed: true, hint: "匿名可用" },
  { id: "bilibili", label: "B站", icon: "bi-play-btn", kind: "crawler", platform: "bilibili", provider: null, backed: true, hint: "建议配 Cookie" },
  { id: "zhihu", label: "知乎", icon: "bi-question-circle", kind: "crawler", platform: "zhihu", provider: null, backed: true, hint: "需配置 Cookie" },
  { id: "baidu_search", label: "百度搜索", icon: "bi-search", kind: "search", platform: null, provider: "baidu", backed: true, hint: "网页检索，覆盖面广" },
  { id: "bing_search", label: "必应搜索", icon: "bi-globe2", kind: "search", platform: null, provider: "bing", backed: true, hint: "百度被限流时的兜底" },
  // 检索源只保留通用网页搜索：代码托管站（GitHub 等）搜到的是仓库与 issue，
  // 与"某个话题下大家在说什么"无关，放进背景资料只会稀释上下文。
  // 若要新增引擎，见 backend/app/search/README.md：加一个 provider 文件即可，
  // 注册表自动发现，这里补一行即成为真正生效的勾选项。
];

export const RANKING_STRATEGIES: OptionMeta<RankingStrategy>[] = [
  // TODO(backend): 排序策略需要后端在合并检索结果时支持，当前仅前端偏好。
  { value: "latest", label: "最新优先", hint: "按时间倒序", backed: false },
  { value: "popularity", label: "热度优先", hint: "按互动量排序", backed: false },
  { value: "diversity", label: "来源多样性", hint: "各平台轮转，避免单一来源主导", backed: false },
  { value: "relevance", label: "AI 相关性", hint: "由模型判断与关键词的相关度", backed: false },
];

export const SENTIMENT_GRANULARITIES: OptionMeta<SentimentGranularity>[] = [
  { value: "overall", label: "整体情感", hint: "只给一个总体倾向", backed: false },
  { value: "polarity", label: "正负比例", hint: "正向 / 中立 / 负向占比（当前默认）", backed: true },
  { value: "emotions", label: "情绪分类", hint: "愤怒 / 喜悦 / 担忧等细分", backed: false },
];

/** LLM 分析类型 → 预置提问模板。这条链路是真实生效的：模板写进 llm_question。 */
export const LLM_ANALYSIS_TYPES: (OptionMeta<LlmAnalysisType> & { template: string })[] = [
  { value: "summary", label: "综合摘要", hint: "概括整体舆论态势", backed: true,
    template: "请概括本次采集到的舆论整体态势与主要观点。" },
  { value: "trend", label: "趋势分析", hint: "关注情绪与话题的走向", backed: true,
    template: "请分析这些评论反映出的情绪走向与话题演变趋势。" },
  { value: "events", label: "关键事件提取", hint: "抽出被反复提及的事件", backed: true,
    template: "请从这些评论中提取被反复提及的关键事件，并按重要性排序。" },
  { value: "risk", label: "风险识别", hint: "找出潜在负面风险点", backed: true,
    template: "请识别这些评论中反映出的潜在负面风险点，并说明依据。" },
  { value: "opinion", label: "观点挖掘", hint: "归纳对立的核心论点", backed: true,
    template: "请归纳这些评论中的主要对立观点，并分别说明各方论据。" },
];

export interface AnalysisFormState {
  keyword: string;
  mode: SearchMode;
  count: number;
  /** 已启用的来源 id */
  sources: string[];
  ranking: RankingStrategy;
  sentimentEnabled: boolean;
  granularity: SentimentGranularity;
  llmAnalysis: LlmAnalysisType;
}

const DEFAULT_STATE: AnalysisFormState = {
  keyword: "",
  mode: "quick",
  count: 300,
  sources: ["weibo", "douban", "tieba", "bilibili", "zhihu", "baidu_search", "bing_search"],
  ranking: "diversity",
  sentimentEnabled: true,
  granularity: "polarity",
  llmAnalysis: "summary",
};

function loadPersisted(): AnalysisFormState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_STATE;
    const saved = JSON.parse(raw) as Partial<AnalysisFormState>;
    return {
      ...DEFAULT_STATE,
      ...saved,
      // 关键词不持久化：上次查过什么不该在新会话里自动重来
      keyword: "",
      sources: Array.isArray(saved.sources) && saved.sources.length
        ? saved.sources.filter((id) => SOURCES.some((s) => s.id === id))
        : DEFAULT_STATE.sources,
    };
  } catch {
    return DEFAULT_STATE;
  }
}

/** 已启用的采集平台（排除检索源，它们不参与 platform 选择） */
export function selectedCrawlerPlatforms(sources: string[]): Platform[] {
  return SOURCES
    .filter((s) => s.kind === "crawler" && s.platform && sources.includes(s.id))
    .map((s) => s.platform as Platform);
}

/** 已启用的检索 provider（未接入的条目不会出现在这里） */
export function selectedSearchProviders(sources: string[]): string[] {
  return SOURCES
    .filter((s) => s.kind === "search" && s.provider && sources.includes(s.id))
    .map((s) => s.provider as string);
}

/**
 * 把多选来源映射成后端的 platform 字段。
 *
 * 恰好选中一个采集源时直接用它——单源任务没必要绕一层聚合爬虫。选中多个
 * 时用 `auto`，具体跑哪几个由随行的 `platforms[]` 决定。
 */
export function resolvePlatform(sources: string[]): Platform {
  const picked = selectedCrawlerPlatforms(sources);
  if (picked.length === 1) return picked[0];
  return "auto";
}

export function useAnalysisForm() {
  const [state, setState] = useState<AnalysisFormState>(loadPersisted);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      /* 隐私模式下 localStorage 不可用，忽略即可 */
    }
  }, [state]);

  const update = useCallback(
    <K extends keyof AnalysisFormState>(key: K, value: AnalysisFormState[K]) => {
      setState((prev) => ({ ...prev, [key]: value }));
    },
    []
  );

  /** 切换模式时同步套用该模式的建议采集量 */
  const setMode = useCallback((mode: SearchMode) => {
    const preset = SEARCH_MODES.find((m) => m.value === mode);
    setState((prev) => ({ ...prev, mode, count: preset ? preset.count : prev.count }));
  }, []);

  const toggleSource = useCallback((id: string) => {
    setState((prev) => {
      const next = prev.sources.includes(id)
        ? prev.sources.filter((s) => s !== id)
        : [...prev.sources, id];
      return { ...prev, sources: next };
    });
  }, []);

  const platform = useMemo(() => resolvePlatform(state.sources), [state.sources]);
  const crawlerCount = useMemo(
    () => selectedCrawlerPlatforms(state.sources).length,
    [state.sources]
  );
  const searchProviders = useMemo(
    () => selectedSearchProviders(state.sources),
    [state.sources]
  );

  /** 组装后端请求体 */
  const buildTaskRequest = useCallback(
    (config: LLMConfig): TaskRequest => {
      const preset = LLM_ANALYSIS_TYPES.find((t) => t.value === state.llmAnalysis);
      // 用户自己填了问题就尊重用户的，否则用分析类型对应的模板
      const question = config.llm_question?.trim()
        ? config.llm_question
        : preset?.template || "";
      return {
        keyword: state.keyword.trim(),
        platform: resolvePlatform(state.sources),
        count: state.count,
        platforms: selectedCrawlerPlatforms(state.sources),
        // 一个检索源都没勾 = 关闭检索增强。这里必须传空数组而不是省略字段：
        // 省略在后端表示"全部启用"，与用户的意思正好相反。
        search_providers: selectedSearchProviders(state.sources),
        llm_base_url: config.llm_base_url,
        llm_api_key: config.llm_api_key,
        llm_model: config.llm_model,
        llm_question: question,
        llm_context_format: config.llm_context_format || "xml",
      };
    },
    [state]
  );

  return {
    state,
    update,
    setMode,
    toggleSource,
    platform,
    crawlerCount,
    searchCount: searchProviders.length,
    buildTaskRequest,
    reset: () => setState({ ...DEFAULT_STATE, keyword: state.keyword }),
  };
}
