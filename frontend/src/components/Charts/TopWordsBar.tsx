import { useEffect, useRef } from "react";
import { CHART_FONT, chartPalette, echarts } from "./echarts";
import { useThemeTick } from "../../state/theme";
import type { WordItem } from "../../api/types";

interface Props {
  data: WordItem[];
}

export function TopWordsBar({ data }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const themeTick = useThemeTick();

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chartRef.current = chart;
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const reversed = data.slice().reverse();
    const c = chartPalette();
    chart.setOption({
      textStyle: { fontFamily: CHART_FONT, color: c.textSecondary },
      tooltip: {
        trigger: "axis",
        axisPointer: {
          type: "shadow",
          shadowStyle: { color: c.isDark ? "rgba(255,255,255,.06)" : "rgba(0,0,0,.03)" },
        },
        backgroundColor: c.tooltipBg,
        borderWidth: 0,
        extraCssText:
          `backdrop-filter:blur(20px);border-radius:12px;box-shadow:${c.tooltipShadow};`,
        textStyle: { color: c.text, fontSize: 13 },
      },
      grid: { left: 4, right: 24, bottom: 4, top: 8, containLabel: true },
      xAxis: {
        type: "value",
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: c.textSecondary, fontSize: 12 },
        splitLine: { lineStyle: { color: c.grid } },
      },
      yAxis: {
        type: "category",
        data: reversed.map((item) => item.name),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: c.text, fontSize: 13 },
      },
      series: [
        {
          type: "bar",
          barMaxWidth: 18,
          data: reversed.map((item) => item.value),
          itemStyle: {
            color: c.accent,
            borderRadius: [0, 5, 5, 0],
          },
        },
      ],
    });
  }, [data, themeTick]);

  return <div ref={ref} style={{ height: 360 }} />;
}