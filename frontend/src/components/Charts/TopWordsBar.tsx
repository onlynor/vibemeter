import { useEffect, useRef } from "react";
import { echarts } from "./echarts";
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
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: "18%", right: "8%", bottom: "5%", top: "5%" },
      xAxis: { type: "value", splitLine: { lineStyle: { color: "#eef0f5" } } },
      yAxis: {
        type: "category",
        data: reversed.map((item) => item.name),
        axisLine: { show: false },
        axisTick: { show: false },
      },
      series: [
        {
          type: "bar",
          data: reversed.map((item) => item.value),
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
              { offset: 0, color: "#4f7ec7" },
              { offset: 1, color: "#1a3d8f" },
            ]),
            borderRadius: [0, 6, 6, 0],
          },
        },
      ],
    });
  }, [data]);

  return <div ref={ref} style={{ height: 360 }} />;
}