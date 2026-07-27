import type {
  ApiEnvelope,
  ExportItem,
  Hotspot,
  LLMConfig,
  LLMTestRequest,
  PieSlice,
  SourceHealth,
  Summary,
  TaskCreated,
  TaskHistoryItem,
  TaskRequest,
  TaskStatus,
  WordItem,
} from "./types";

export class ApiError extends Error {
  constructor(message: string, public status?: number) {
    super(message);
    this.name = "ApiError";
  }
}

async function parseResponse<T>(response: Response): Promise<ApiEnvelope<T>> {
  let body: ApiEnvelope<T> | undefined;
  try {
    body = (await response.json()) as ApiEnvelope<T>;
  } catch {
    throw new ApiError("HTTP " + response.status, response.status);
  }
  if (!response.ok || body.code !== 0) {
    throw new ApiError(body.msg || "HTTP " + response.status, response.status);
  }
  return body;
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  const envelope = await parseResponse<T>(response);
  return envelope.data as T;
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const envelope = await parseResponse<T>(response);
  return envelope.data as T;
}

/** 把后端包络解开来：成功返回 data，失败抛 ApiError */
export const api = {
  // LLM 配置（进程内存）
  getLlmConfig: () => getJson<LLMConfig>("/api/llm/config"),
  saveLlmConfig: (config: LLMConfig) => postJson<LLMConfig>("/api/llm/config", config),

  // LLM 测试
  testLlm: (req: LLMTestRequest) => postJson<{ message: string }>("/api/llm/test", req),

  // 热搜
  getHotspots: () => getJson<Hotspot[]>("/api/hotspots"),

  // 数据源可用性（后端带 5 分钟缓存）
  getSourceHealth: () => getJson<SourceHealth[]>("/api/sources/health"),

  // 任务
  createTask: (req: TaskRequest) => postJson<TaskCreated>("/api/task", req),
  getTaskStatus: (id: string) => getJson<TaskStatus>(`/api/task/${id}/status`),
  getHistory: () => getJson<TaskHistoryItem[]>("/api/tasks/history"),

  // 结果
  getSummary: (id: string) => getJson<Summary>(`/api/result/${id}/summary`),
  getSentimentPie: (id: string) => getJson<PieSlice[]>(`/api/result/${id}/sentiment-pie`),
  getTopWords: (id: string) => getJson<WordItem[]>(`/api/result/${id}/top-words`),
  getExports: (id: string) => getJson<ExportItem[]>(`/api/result/${id}/exports`),
  getXmlContext: (id: string) => getJson<{ xml: string }>(`/api/result/${id}/xml-context`),
  getPositiveCloud: (id: string) => getJson<{ image: string }>(`/api/result/${id}/wordcloud/positive`),
  getNegativeCloud: (id: string) => getJson<{ image: string }>(`/api/result/${id}/wordcloud/negative`),
};