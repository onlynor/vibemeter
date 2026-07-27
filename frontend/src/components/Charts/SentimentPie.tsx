import { useEffect, useRef } from "react";
import { echarts } from "./echarts";
import type { PieSlice } from "../../api/types";

interface Props {
  data: PieSlice[];
}

export function SentimentPie({ data }: Props) {
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
    chart.setOption({
      tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
      legend: { bottom: 0, icon: "circle" },
      color: ["#2eb872", "#f0b400", "#e64545"],
      series: [
        {
          type: "pie",
          radius: ["45%", "70%"],
          itemStyle: { borderRadius: 8, borderColor: "#fff", borderWidth: 2 },
          label: { show: true, formatter: "{b}\n{d}%" },
          data,
        },
      ],
    });
  }, [data]);

  return <div ref={ref} style={{ height: 360 }} />;
}