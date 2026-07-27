import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { Platform, TaskRequest } from "../api/types";
import { useLlmConfig } from "../state/llmConfig";
import { LlmSidebar } from "../components/LlmSidebar";
import { LlmConfigForm } from "../components/LlmConfigForm";
import { HotspotList } from "../components/HotspotList";
import { SourceHealthCheck } from "../components/SourceHealthCheck";

export function HomePage() {
  const navigate = useNavigate();
  const { config, updateField } = useLlmConfig();
  const keywordRef = useRef<HTMLInputElement | null>(null);

  const [keyword, setKeyword] = useState("");
  const [platform, setPlatform] = useState<Platform>("auto");
  const [count, setCount] = useState(500);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = keyword.trim();
    if (!trimmed) {
      setError("请输入关键词");
      return;
    }
    setError(null);
    setSubmitting(true);

    const payload: TaskRequest = {
      keyword: trimmed,
      platform,
      count,
      llm_base_url: config.llm_base_url,
      llm_api_key: config.llm_api_key,
      llm_model: config.llm_model,
      llm_question: config.llm_question,
      llm_context_format: config.llm_context_format || "xml",
    };

    api
      .createTask(payload)
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
    setKeyword(title);
    keywordRef.current?.focus();
  }

  return (
    <LlmSidebar
      title={<><i className="bi bi-stars me-2" />LLM 配置</>}
      sidebar={<LlmConfigForm config={config} updateField={updateField} />}
      main={
        <div className="row g-4">
          <div className="col-12">
            <div className="hero-card card border-0 shadow-lg">
              <div className="card-body p-4 p-md-5">
                <div className="d-flex align-items-center mb-3">
                  <i className="bi bi-broadcast-pin hero-icon" />
                  <h2 className="card-title fw-bold ms-3 mb-0">开启一次舆情洞察</h2>
                </div>
                <p className="text-muted mb-4">输入关键词后直接开始采集和分析。</p>
                <form noValidate onSubmit={onSubmit}>
                  <div className="mb-3">
                    <label className="form-label fw-semibold" htmlFor="keyword">关键词</label>
                    <input
                      id="keyword"
                      ref={keywordRef}
                      className="form-control form-control-lg"
                      required
                      maxLength={64}
                      placeholder="例如：AI、Agent、多智能体"
                      value={keyword}
                      onChange={(e) => setKeyword(e.target.value)}
                    />
                  </div>
                  <div className="row g-3">
                    <div className="col-md-6">
                      <label className="form-label fw-semibold" htmlFor="platform">数据源</label>
                      <select
                        id="platform"
                        className="form-select form-select-lg"
                        value={platform}
                        onChange={(e) => setPlatform(e.target.value as Platform)}
                      >
                        <option value="auto">聚合搜索（推荐）</option>
                        <option value="bilibili">B站</option>
                        <option value="weibo">微博</option>
                        <option value="douban">豆瓣</option>
                        <option value="zhihu">知乎</option>
                        <option value="tieba">贴吧</option>
                      </select>
                    </div>
                    <div className="col-md-6">
                      <label className="form-label fw-semibold" htmlFor="count">采集数量</label>
                      <input
                        id="count"
                        type="number"
                        className="form-control form-control-lg"
                        min={300}
                        max={2000}
                        step={50}
                        value={count}
                        onChange={(e) => setCount(Number(e.target.value) || 500)}
                      />
                    </div>
                  </div>
                  <div className="mt-3">
                    <SourceHealthCheck />
                  </div>
                  {error && (
                    <div className="text-danger small mt-3">{error}</div>
                  )}
                  <button
                    className="btn btn-primary btn-lg w-100 mt-4"
                    type="submit"
                    disabled={submitting}
                  >
                    <i className="bi bi-graph-up-arrow me-2" />
                    <span>{submitting ? "正在创建任务..." : "开始分析"}</span>
                  </button>
                </form>
              </div>
            </div>
          </div>

          <div className="col-12">
            <HotspotList onPick={pickHotspot} />
          </div>
        </div>
      }
    />
  );
}