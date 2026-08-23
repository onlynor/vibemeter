import { useEffect, useState } from "react";

/**
 * 主题（浅色 / 深色 / 跟随系统）。
 *
 * 真正生效的只有 `<html data-theme="light|dark">` 这一个属性，styles.css 里
 * 深色令牌挂在 `:root[data-theme="dark"]` 上——"跟随系统"由这里解析成具体值
 * 再写上去，CSS 不必为 `prefers-color-scheme` 再复制一份令牌表。
 *
 * 首屏的初始值由 index.html 里的内联脚本抢在渲染前设好，否则深色用户会先
 * 闪一帧白底。这里的逻辑必须与那段脚本保持一致（同一个 storage key、同样的
 * 解析规则），改一处就要改两处。
 */

export type ThemeMode = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

const STORAGE_KEY = "vibe.theme.v1";
/** ECharts 拿不到 CSS 变量，只能在主题切换时收到通知后自己重画 */
const THEME_EVENT = "vibe:theme";

const media = () => window.matchMedia("(prefers-color-scheme: dark)");

export function systemTheme(): ResolvedTheme {
  return media().matches ? "dark" : "light";
}

export function resolveTheme(mode: ThemeMode): ResolvedTheme {
  return mode === "system" ? systemTheme() : mode;
}

function loadMode(): ThemeMode {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "light" || saved === "dark" || saved === "system") return saved;
  } catch {
    /* 隐私模式下 localStorage 不可用 */
  }
  return "system";
}

function apply(theme: ResolvedTheme) {
  const root = document.documentElement;
  root.dataset.theme = theme;
  // 原生控件（下拉、滚动条、日期选择）跟着换配色，否则深色页里会嵌一块白
  root.style.colorScheme = theme;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", theme === "dark" ? "#0a0a0c" : "#fbfbfd");
  window.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: theme }));
}

export function useTheme() {
  const [mode, setMode] = useState<ThemeMode>(loadMode);
  const [resolved, setResolved] = useState<ResolvedTheme>(() => resolveTheme(loadMode()));

  useEffect(() => {
    const next = resolveTheme(mode);
    setResolved(next);
    apply(next);
    try {
      localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      /* ignore */
    }
  }, [mode]);

  // 只有"跟随系统"时才需要盯着系统设置变化
  useEffect(() => {
    if (mode !== "system") return;
    const mq = media();
    const onChange = () => {
      const next = systemTheme();
      setResolved(next);
      apply(next);
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [mode]);

  return { mode, setMode, resolved };
}

/**
 * 主题变更计数器：给 ECharts 这类"必须重新 setOption 才能换色"的组件用。
 * 把返回值放进 effect 依赖里，主题一变就会重画。
 */
export function useThemeTick(): number {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const bump = () => setTick((n) => n + 1);
    window.addEventListener(THEME_EVENT, bump);
    return () => window.removeEventListener(THEME_EVENT, bump);
  }, []);
  return tick;
}
