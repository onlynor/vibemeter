/** 后端统一响应包络 */
export interface ApiEnvelope<T> {
  code: number; // 0 成功，其它为失败
  msg?: string;
  data?: T;
}

export type Platform =
  | "auto"
  | "bilibili"
  | "weibo"
  | "douban"
  | "zhihu"
  | "tieba";

/** GET /api/sources/health 的单项：某个数据源当前的可用性 */
export interface SourceHealth {
  platform: Platform | string;
  label: string;
  /** crawler = 可选的采集平台；search = 检索增强的搜索引擎，不进平台下拉框 */
  kind?: "crawler" | "search";
  ok: boolean;
  message: string;
  /** 该平台可选 Cookie 对应的环境变量名，无则为空串 */
  cookie_env: string;
  /** 无 Cookie 时该平台是否完全不可用 */
  cookie_required: boolean;
  cookie_configured: boolean;
}

export interface LLMConfig {
  llm_base_url: string;
  llm_api_key: string;
  llm_model: string;
  llm_question: string;
  llm_context_format: "xml" | "markdown";
}

export interface LLMTestRequest {
  base_url: string;
  api_key: string;
  model: string;
}

export interface TaskRequest {
  keyword: string;
  platform: Platform;
  count: number;
  llm_base_url: string;
  llm_api_key: string;
  llm_model: string;
  llm_question: string;
  llm_context_format: "xml" | "markdown";
}

export interface TaskCreated {
  task_id: string;
}

export interface TaskHistoryItem {
  task_no: number;
  task_id: string;
  keyword: string;
  platform: Platform;
  status: string;
  total_count: number;
  start_time: string;
  end_time?: string;
  error?: string;
  display_no: string;
  url: string;
}

/** GET /api/task/{id}/status 同此结构（来自 tasks 表） */
export interface TaskStatus extends TaskHistoryItem {
  raw_total?: number;
  elapsed?: number;
}

export interface Hotspot {
  rank: number | string;
  title: string;
  subtitle?: string;
  score?: string;
  url?: string;
  source: string;
  is_mock?: boolean;
}

export interface CommentItem {
  score: number;
  text: string;
}

export interface SourceItem {
  platform: string;
  title: string;
  subtitle?: string;
  url?: string;
  embed_url?: string;
}

export interface LLMInsight {
  title?: string;
  answer?: string;
  question?: string;
  context_text?: string;
  context_format?: string;
}

/** 各搜索引擎统一的结果模型，与后端 app.search.base.SearchResult 对应 */
export interface SearchResult {
  title: string;
  url: string;
  snippet: string;
  /** provider 名称，如 baidu */
  source: string;
  /** 在该 provider 自身结果中的名次，从 1 起；跨 provider 不可比 */
  rank: number;
}

export interface SearchProviderStatus {
  provider: string;
  label: string;
  ok: boolean;
  count: number;
  message: string;
}

export interface Summary {
  total: number;
  raw_total?: number;
  elapsed: number;
  keyword?: string;
  platform: Platform;
  source_items?: SourceItem[];
  /** 采集阶段各来源贡献的条数（去重前、清洗前），聚合搜索下用于判断样本构成 */
  source_stats?: Record<string, number>;
  /** 搜索引擎检索结果：仅作背景资料与展示，不参与情感分析 */
  search_results?: SearchResult[];
  search_status?: SearchProviderStatus[];
  top_positive?: CommentItem[];
  top_negative?: CommentItem[];
  positive: number;
  neutral: number;
  negative: number;
  llm_insight?: LLMInsight | null;
}

export interface PieSlice {
  name: string;
  value: number;
}

export interface WordItem {
  name: string;
  value: number;
}

export interface ExportItem {
  kind: "raw" | "cleaned" | "analysed" | "summary";
  url: string;
  size: number;
}

/** WebSocket 推送的进度消息 */
export interface ProgressMessage {
  status:
    | "crawling"
    | "preprocessing"
    | "analyzing"
    | "wordcloud"
    | "llm"
    | "completed"
    | "failed"
    | "keepalive"
    | string;
  current: number;
  total: number;
  raw_total?: number;
  message?: string;
  elapsed?: number;
  error?: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

/** SSE 帧的三种可能 */
export type ChatStreamEvent =
  | { delta: string }
  | { error: string }
  | { done: true };