// src/design-system/components/EditorialChartCard/buildEditorialOption.ts
//
// Helpers que devolvem `EChartsOption` opinionados para o paradigma editorial
// (Goldman/FT/Economist): area layered + endLabel inline + grid horizontal
// dashed + chrome de eixo minimo. Cada helper foca um tipo de chart — comeca
// com `buildEditorialAreaOption`, mais podem ser adicionados conforme o padrao
// escala (line-only, bar editorial, etc.).
//
// Hex literals abaixo sao excecao canonica do CLAUDE.md §4 (Tailwind nao
// alcanca o canvas ECharts). Onde possivel, referenciam `tokens.colors.chart`.

import type {
  EChartsOption,
  LineSeriesOption,
} from "echarts"

import { tokens } from "@/design-system/tokens"

export type EditorialAreaSeries = {
  name: string
  data: Array<number | null>
  /** Hex (preferir tokens.colors.chart). Aplica em linha + gradiente da area. */
  color: string
  /**
   * Override do label inline na ponta direita. Default = `name`.
   * Util quando a serie tem nome longo e voce quer um label curto inline
   * (ex.: serie "Volume de Operacao" com endLabel "VOP").
   */
  endLabel?: string
}

export type EditorialAreaOptions = {
  xAxis: string[]
  series: EditorialAreaSeries[]
  /** Formatador do eixo Y (ex.: `(v) => "R$ 12M"`). */
  yFormatter?: (value: number) => string
  /** Formatador do tooltip por linha de serie. Default formata como BRL compacto. */
  tooltipValueFormatter?: (value: number | null, seriesName: string) => string
}

const TOP_OPACITY = 0.32
const BOTTOM_OPACITY = 0

const defaultBRLCompact = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 1,
})

function buildAreaSeries(s: EditorialAreaSeries): LineSeriesOption {
  const labelText = s.endLabel ?? s.name
  return {
    name: s.name,
    type: "line",
    smooth: true,
    symbol: "none",
    showSymbol: false,
    sampling: "lttb",
    connectNulls: false,
    lineStyle: {
      color: s.color,
      width: 2,
    },
    areaStyle: {
      color: {
        type: "linear",
        x: 0,
        y: 0,
        x2: 0,
        y2: 1,
        colorStops: [
          { offset: 0, color: hexWithAlpha(s.color, TOP_OPACITY) },
          { offset: 1, color: hexWithAlpha(s.color, BOTTOM_OPACITY) },
        ],
      },
    },
    emphasis: {
      focus: "series",
      lineStyle: { width: 2.5 },
    },
    endLabel: {
      show: true,
      formatter: labelText,
      color: s.color,
      fontWeight: 600,
      fontSize: 12,
      padding: [2, 6],
      distance: 8,
      align: "left",
      verticalAlign: "middle",
    },
    labelLayout: { moveOverlap: "shiftY" },
    data: s.data,
  }
}

export function buildEditorialAreaOption(
  opts: EditorialAreaOptions,
): EChartsOption {
  const valueFmt =
    opts.tooltipValueFormatter ??
    ((v) =>
      v == null
        ? "—"
        : defaultBRLCompact.format(v))

  return {
    grid: {
      left: 8,
      right: 96,
      top: 16,
      bottom: 32,
      containLabel: true,
    },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line" },
      formatter: (params) => {
        const arr = params as unknown as Array<{
          axisValue: string
          seriesName?: string
          value: number | null
          color: string
        }>
        if (!Array.isArray(arr) || arr.length === 0) return ""
        const lines = arr
          .map((p) => {
            const dot = `<span style="display:inline-block;margin-right:6px;width:8px;height:8px;border-radius:50%;background:${p.color}"></span>`
            return `${dot}<span>${p.seriesName ?? ""}</span><strong style="margin-left:12px;float:right">${valueFmt(p.value, p.seriesName ?? "")}</strong>`
          })
          .join("<br/>")
        return `<div style="min-width:180px"><div style="margin-bottom:6px;font-weight:600">${arr[0].axisValue}</div>${lines}</div>`
      },
    },
    xAxis: {
      type: "category",
      data: opts.xAxis,
      boundaryGap: false,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: "#9CA3AF", fontSize: 11 },
    },
    yAxis: {
      type: "value",
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: "#9CA3AF",
        fontSize: 11,
        formatter: opts.yFormatter,
      },
      splitLine: {
        show: true,
        lineStyle: { color: "#E5E7EB", type: "dashed", width: 1 },
      },
    },
    series: opts.series.map(buildAreaSeries),
  } satisfies EChartsOption
}

// ── helpers internos ─────────────────────────────────────────────────────────

/**
 * Converte `#RRGGBB` em `rgba(r,g,b,alpha)`. Usado nos colorStops do gradient
 * vertical da areaStyle. Se `hex` ja for `rgba(...)` ou nome named, devolve
 * inalterado (deixa ECharts lidar).
 */
function hexWithAlpha(hex: string, alpha: number): string {
  if (!hex.startsWith("#") || (hex.length !== 7 && hex.length !== 4)) {
    return hex
  }
  const full =
    hex.length === 4
      ? `#${hex[1]}${hex[1]}${hex[2]}${hex[2]}${hex[3]}${hex[3]}`
      : hex
  const r = parseInt(full.slice(1, 3), 16)
  const g = parseInt(full.slice(3, 5), 16)
  const b = parseInt(full.slice(5, 7), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

// Re-export tokens para conveniencia em paginas que montam series.
export const editorialChartColors = tokens.colors.chart
