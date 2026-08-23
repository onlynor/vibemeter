import * as echarts from "echarts";

/**
 * 图表配色与字体。
 *
 * ECharts 在 canvas 里画字，读不到 CSS 变量——过去的做法是在这里手抄一份
 * 常量，于是每次改调色板都要记得改两处，深色主题更是没法用一套常量兼顾。
 * 现在改成运行时从 `:root` 上把令牌的计算值读出来：样式表仍是唯一的配色
 * 来源，主题一换、值就跟着变，只需要重新 `setOption`（见 `useThemeTick`）
 */
export const CHART_FONT =
  '"SF Pro Text", -apple-system, BlinkMacSystemFont, "PingFang SC", ' +
  '"Microsoft YaHei", "Helvetica Neue", Arial, sans-serif';

function token(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return value || fallback;
}

export interface ChartPalette {
  /** 正向 / 中立 / 负向，顺序与后端 sentiment-pie 返回的一致 */
  sentiment: [string, string, string];
  text: string;
  textSecondary: string;
  grid: string;
  accent: string;
  surface: string;
  /** tooltip 的底色与阴影：深色下白底 tooltip 会亮瞎眼 */
  tooltipBg: string;
  tooltipShadow: string;
  isDark: boolean;
}

export function chartPalette(): ChartPalette {
  const isDark = document.documentElement.dataset.theme === "dark";
  return {
    sentiment: [
      token("--positive", "#34c759"),
      token("--neutral", "#ff9f0a"),
      token("--negative", "#ff3b30"),
    ],
    text: token("--text", "#1d1d1f"),
    textSecondary: token("--text-secondary", "#6e6e73"),
    grid: token("--hairline", "rgba(0,0,0,.09)"),
    accent: token("--accent", "#0071e3"),
    surface: token("--surface", "#ffffff"),
    tooltipBg: isDark ? "rgba(38,38,44,.94)" : "rgba(255,255,255,.92)",
    tooltipShadow: isDark
      ? "0 8px 28px rgba(0,0,0,.55)"
      : "0 8px 28px rgba(0,0,0,.12)",
    isDark,
  };
}

export { echarts };
