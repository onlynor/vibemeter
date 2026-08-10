import { useEffect, useRef } from "react";
import {
  CHART_ACCENT,
  CHART_FONT,
  CHART_GRID,
  CHART_TEXT,
  CHART_TEXT_SECONDARY,
  echarts,
} from "./echarts";
import type { WordItem } from "../../api/types";

interface Props {
  data: WordItem[];
}

export function TopWordsBar({ data }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

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
    chart.setOption({
      textStyle: { fontFamily: CHART_FONT, color: CHART_TEXT_SECONDARY },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow", shadowStyle: { color: "rgba(0,0,0,.03)" } },
        backgroundColor: "rgba(255,255,255,.92)",
        borderWidth: 0,
        extraCssText: "backdrop-filter:blur(20px);border-radius:12px;" +
                      "box-shadow:0 8px 28px rgba(0,0,0,.12);",
        textStyle: { color: CHART_TEXT, fontSize: 13 },
      },
      grid: { left: 4, right: 24, bottom: 4, top: 8, containLabel: true },
      xAxis: {
        type: "value",
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: CHART_TEXT_SECONDARY, fontSize: 12 },
        splitLine: { lineStyle: { color: CHART_GRID } },
      },
      yAxis: {
        type: "category",
        data: reversed.map((item) => item.name),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: CHART_TEXT, fontSize: 13 },
      },
      series: [
        {
          type: "bar",
          barMaxWidth: 18,
          data: reversed.map((item) => item.value),
          itemStyle: {
            color: CHART_ACCENT,
            borderRadius: [0, 5, 5, 0],
          },
        },
      ],
    });
  }, [data]);

  return <div ref={ref} style={{ height: 360 }} />;
}