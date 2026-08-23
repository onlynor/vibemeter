import { useEffect, useRef } from "react";
import { CHART_FONT, chartPalette, echarts } from "./echarts";
import { useThemeTick } from "../../state/theme";
import type { PieSlice } from "../../api/types";

interface Props {
  data: PieSlice[];
}

export function SentimentPie({ data }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  // 主题一变就重画：canvas 里的颜色不会跟着 CSS 变量走
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
    const c = chartPalette();
    chart.setOption({
      textStyle: { fontFamily: CHART_FONT, color: c.textSecondary },
      tooltip: {
        trigger: "item",
        formatter: "{b}: {c} ({d}%)",
        backgroundColor: c.tooltipBg,
        borderWidth: 0,
        extraCssText:
          `backdrop-filter:blur(20px);border-radius:12px;box-shadow:${c.tooltipShadow};`,
        textStyle: { color: c.text, fontSize: 13 },
      },
      legend: {
        bottom: 0,
        icon: "circle",
        itemGap: 20,
        textStyle: { color: c.textSecondary, fontSize: 13 },
      },
      color: c.sentiment,
      series: [
        {
          type: "pie",
          radius: ["58%", "78%"],
          center: ["50%", "46%"],
          // 扇区之间的缝隙用卡片底色描出来，深色下不能再写死白色
          itemStyle: { borderRadius: 6, borderColor: c.surface, borderWidth: 3 },
          label: {
            show: true,
            formatter: "{b}\n{d}%",
            color: c.text,
            fontSize: 13,
            lineHeight: 18,
          },
          labelLine: { lineStyle: { color: c.textSecondary } },
          data,
        },
      ],
    });
  }, [data, themeTick]);

  return <div ref={ref} style={{ height: 360 }} />;
}