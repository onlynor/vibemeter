import * as echarts from "echarts";

/**
 * 图表共享的字体与配色。
 *
 * ECharts 在 canvas 里画字，拿不到 CSS 变量，所以这里把设计系统里的值
 * 复制一份常量。改 styles.css 的调色板时记得同步这里，否则图表会和页面
 * 其余部分脱节。
 */
export const CHART_FONT =
  '"SF Pro Text", -apple-system, BlinkMacSystemFont, "PingFang SC", ' +
  '"Microsoft YaHei", "Helvetica Neue", Arial, sans-serif';

/** 正向 / 中立 / 负向，顺序与后端 sentiment-pie 返回的一致 */
export const SENTIMENT_COLORS = ["#34c759", "#ff9f0a", "#ff3b30"];

export const CHART_TEXT = "#1d1d1f";
export const CHART_TEXT_SECONDARY = "#6e6e73";
export const CHART_GRID = "rgba(0,0,0,.06)";
export const CHART_ACCENT = "#0071e3";

export { echarts };
