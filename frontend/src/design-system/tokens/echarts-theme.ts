// src/design-system/tokens/echarts-theme.ts
// ECharts theme generator — call getEChartsTheme(mode) and pass to
// ReactECharts option's `theme` or register globally via echarts.registerTheme().
//
// Rule: tooltip is ALWAYS dark regardless of app theme (Stripe/Vercel/Linear pattern).
// Rule: animationDurationUpdate = 0 (no re-render animation, only first-render).

import { tokens } from "./index"

export function getEChartsTheme(mode: "light" | "dark") {
  const d = mode === "dark"
  return {
    color: [...tokens.colors.chart],
    backgroundColor: "transparent",
    textStyle: {
      fontFamily: "'Geist', 'Inter', system-ui, sans-serif",
      fontSize: 12,
      color: d ? "#F9FAFB" : "#111827",
    },
    title: {
      textStyle: {
        fontFamily: "'Geist', system-ui, sans-serif",
        fontWeight: 600,
        fontSize: 14,
        color: d ? "#F9FAFB" : "#111827",
      },
    },
    legend: {
      icon: "circle" as const,
      itemWidth: 8,
      itemHeight: 8,
      textStyle: {
        fontSize: 11,
        color: d ? "#9CA3AF" : "#6B7280",
      },
    },
    axisLine: {
      lineStyle: { color: d ? "#374151" : "#D1D5DB" },
    },
    axisLabel: {
      fontFamily: "'Geist', 'Inter', system-ui",
      fontSize: 11,
      color: d ? "#9CA3AF" : "#6B7280",
    },
    axisTick: {
      show: false,
      lineStyle: { color: d ? "#374151" : "#E5E7EB" },
    },
    splitLine: {
      lineStyle: {
        color: d ? "#1F2937" : "#E5E7EB",
        type: "dashed" as const,
      },
    },
    tooltip: {
      backgroundColor: "#0A0F1C",
      borderColor: "#1F2937",
      borderWidth: 1,
      textStyle: {
        color: "#F9FAFB",
        fontFamily: "'Geist', 'Inter', system-ui",
        fontSize: 12,
      },
      extraCssText: [
        "box-shadow: 0 8px 24px rgba(0,0,0,0.4)",
        "border-radius: 8px",
        "backdrop-filter: blur(8px)",
        "font-variant-numeric: lining-nums tabular-nums",
      ].join(";"),
    },
    axisPointer: {
      lineStyle: { color: d ? "#374151" : "#D1D5DB", type: "dashed" },
      crossStyle: { color: d ? "#374151" : "#D1D5DB" },
      label: {
        backgroundColor: "#0A0F1C",
        color: "#F9FAFB",
        borderColor: "#1F2937",
      },
    },
    visualMap: {
      inRange: {
        color: ["#1E1B4B", "#3730A3", "#4F46E5", "#6366F1", "#A5B4FC"],
      },
    },
    animationDuration: 400,
    animationDurationUpdate: 0,
    animationEasing: "cubicOut" as const,
    animationEasingUpdate: "linear" as const,
  }
}

export type EChartsTheme = ReturnType<typeof getEChartsTheme>

/**
 * Hook to get the current ECharts theme based on next-themes resolved theme.
 * Returns a memoized object so passing it as a prop doesn't trigger re-renders.
 */
import { useTheme } from "next-themes"
import { useMemo } from "react"

export function useEChartsTheme(): EChartsTheme {
  const { resolvedTheme } = useTheme()
  return useMemo(
    () => getEChartsTheme(resolvedTheme === "dark" ? "dark" : "light"),
    [resolvedTheme],
  )
}
