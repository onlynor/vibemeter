import { useEffect, useRef } from "react";
import { CHART_FONT, SENTIMENT_COLORS, echarts } from "./echarts";
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
      textStyle: { fontFamily: CHART_FONT, color: "#6e6e73" },
      tooltip: {
        trigger: "item",
        formatter: "{b}: {c} ({d}%)",
        backgroundColor: "rgba(255,255,255,.92)",
        borderWidth: 0,
        extraCssText: "backdrop-filter:blur(20px);border-radius:12px;" +
                      "box-shadow:0 8px 28px rgba(0,0,0,.12);",
        textStyle: { color: "#1d1d1f", fontSize: 13 },
      },
      legend: {
        bottom: 0,
        icon: "circle",
        itemGap: 20,
        textStyle: { color: "#6e6e73", fontSize: 13 },
      },
      color: SENTIMENT_COLORS,
      series: [
        {
          type: "pie",
          radius: ["58%", "78%"],
          center: ["50%", "46%"],
          itemStyle: { borderRadius: 6, borderColor: "#fff", borderWidth: 3 },
          label: {
            show: true,
            formatter: "{b}\n{d}%",
            color: "#1d1d1f",
            fontSize: 13,
            lineHeight: 18,
          },
          labelLine: { lineStyle: { color: "#c7c7cc" } },
          data,
        },
      ],
    });
  }, [data]);

  return <div ref={ref} style={{ height: 360 }} />;
}