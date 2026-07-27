import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { LLMConfig } from "../api/types";

const EMPTY_CONFIG: LLMConfig = {
  llm_base_url: "",
  llm_api_key: "",
  llm_model: "",
  llm_question: "",
  llm_context_format: "xml",
};

/**
 * 全局 LLM 配置 hook：初始从服务端拉取，change 时即发即忘回写。
 * 配置不落盘、保存在 FastAPI 进程内存；刷新/跨 tab 自动回填。
 */
export function useLlmConfig() {
  const [config, setConfig] = useState<LLMConfig>(EMPTY_CONFIG);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.getLlmConfig().then((data) => {
      if (cancelled) return;
      // 后端 store 把 llm_context_format 初始化为空字符串，
      // 这里兜底回 "xml"，避免提交时被 pattern 校验拒绝（422）。
      const merged = { ...EMPTY_CONFIG, ...data };
      if (!merged.llm_context_format) merged.llm_context_format = "xml";
      setConfig(merged);
      setLoaded(true);
    }).catch(() => {
      if (cancelled) return;
      setLoaded(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  /** 给某个字段赋值，并立即 fire-and-forget 保存到服务端 */
  const updateField = useCallback(
    (field: keyof LLMConfig, value: string) => {
      setConfig((prev) => {
        const next = { ...prev, [field]: value };
        api.saveLlmConfig(next).catch(() => { /* 静默忽略保存失败 */ });
        return next;
      });
    },
    []
  );

  return { config, updateField, loaded };
}