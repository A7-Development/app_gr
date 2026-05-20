// src/design-system/components/EvolucaoDiariaCard/index.tsx
//
// Card canonico para series temporais DIARIAS de um mes corrente. Irmao
// visual de `EvolucaoMensalCard` — mesma anatomia (header com KPI editorial,
// caption descritiva, barras + linha de tendencia tracejada), granularidade
// dia-calendario.
//
// Cobre TODOS os dias do mes no eixo X (inclusive sabados, domingos e
// feriados). Dias futuros renderizam placeholder no eixo X sem barra (valor
// null no ECharts). Hoje destacado em cor diferente quando `highlightToday`.
//
// Uso:
//   <EvolucaoDiariaCard
//     title="VOP DIÁRIO"
//     presetLabel="Maio/2026"
//     data={vopDiario.map(p => ({ data: p.data, valor: p.vop }))}
//     headerKpi={{ value: fmtBRL.format(acumulado), delta: { value: deltaPct, suffix: "%" }, deltaSub: "MTD" }}
//     valueFormatter={fmtBRLFull.format}
//     axisFormatter={fmtBRL.format}
//   />
//
// Por que componente irmao em vez de extender `EvolucaoMensalCard`:
// granularidade diaria muda o formatador do eixo X, o tooltip e o tratamento
// de valor null (dia futuro). Manter o mensal otimizado pro caso comum +
// novo irmao dedicado evita risco de regressao na Aba 1 (Volume & Ritmo).
// Promocao a `EvolucaoTemporalCard` unificado fica como follow-up.

"use client"

import * as React from "react"
import type { EChartsOption } from "echarts"

import { EChartsCard, type EChartsCardHeaderKpi } from "../EChartsCard"

// ─── Tipos publicos ─────────────────────────────────────────────────────────

export type EvolucaoDiariaPonto = {
  /** Data ISO "YYYY-MM-DD". */
  data: string
  /** Valor do dia. `null` = dia futuro (sem barra, eixo X reserva o slot). */
  valor: number | null
  /** Quando `false`, label do eixo X fica dim (sab/dom/feriado). Default: true. */
  ehDiaUtil?: boolean
  /** Quando `true`, dia esta no futuro. Default: derivado de `valor === null`. */
  ehFuturo?: boolean
  /** Linhas extras no tooltip — caller pre-formata os valores como string. */
  tooltipExtras?: Array<{ label: string; value: string }>
}

/**
 * Serie individual no modo stacked (uma serie por categoria, ex.: por UA).
 *
 * Valores acompanham o array `data` posicional — a serie i tem o valor
 * `series[s].values[i]` para o ponto `data[i]`. Use `null` para dias
 * futuros ou ausencia (ECharts pula a barra mantendo o slot no eixo X).
 */
export type EvolucaoDiariaSerie = {
  /** Nome da serie (ex.: "FIDC", "Securitizadora"). Aparece no tooltip. */
  name: string
  /** Cor hex (ex.: "#0EA5E9"). Se ausente, usa paleta canonica indexada. */
  color?: string
  /** Valores na ordem de `data[]`. null = sem barra (futuro/ausente). */
  values: Array<number | null>
}

export type EvolucaoDiariaCardProps = {
  /** Titulo do card (ex.: "VOP DIÁRIO"). */
  title: string
  /** Label do periodo (ex.: "Maio/2026"). Compoe a caption. */
  presetLabel: string
  /** Pontos da serie diaria — caller passa todos os dias do mes. */
  data: EvolucaoDiariaPonto[]
  /**
   * Quando setado, ativa modo STACKED: ignora `data[].valor` e usa as
   * series fornecidas (uma cor por serie, empilhadas). `data[]` continua
   * sendo a fonte do eixo X (datas + ehDiaUtil + ehFuturo).
   * `headerKpi` e `valueFormatter` continuam funcionando normalmente.
   * `showTrendLine` e desligado automaticamente no modo stacked.
   */
  seriesStacked?: EvolucaoDiariaSerie[]
  /** Destaca o dia de hoje (ultimo ponto com `valor != null`) em cor diferente. Default: true. */
  highlightToday?: boolean
  /** KPI editorial no header — title vira eyebrow, KPI ocupa o lead. */
  headerKpi?: EChartsCardHeaderKpi
  /** Mostra linha de tendencia tracejada (regressao linear sobre dias com valor). Default: true. */
  showTrendLine?: boolean
  /** Formatador para tooltip e KPI (ex.: BRL completo). */
  valueFormatter: (v: number) => string
  /** Formatador do eixo Y. Default: igual a valueFormatter. */
  axisFormatter?: (v: number) => string
  /** Formatador dos rotulos no topo das barras. Default: igual a axisFormatter. */
  dataLabelFormatter?: (v: number) => string
  /** Altura do canvas. Default: 240. */
  height?: number
  loading?: boolean
  error?: string | null
  onRetry?: () => void
  /**
   * Slot de actions no header (vira para o EChartsCard). Util para
   * SegmentSwitch alterando modo single/stacked.
   */
  actions?: React.ReactNode
  /**
   * Callback ao clicar numa barra do dia. Recebe a data ISO "YYYY-MM-DD"
   * do ponto. Cliques em dias futuros (valor null) sao ignorados.
   */
  onPointClick?: (dataISO: string) => void
}

// ─── Cores (hex inline — excecao §4, Tailwind nao alcanca canvas ECharts) ──

const COLOR_BAR_DEFAULT = "#2A4D7A"
const COLOR_BAR_TODAY = "#0EA5E9"
const COLOR_BAR_NONUTIL = "#94A3B8" // slate-400 (sab/dom/feriado passados)
const COLOR_LINE_TREND = "#9CA3AF"
const COLOR_VALUE_LABEL = "#374151"
const COLOR_AXIS_LABEL_DIM = "#9CA3AF"
const COLOR_AXIS_LABEL_DEFAULT = "#6B7280"

// Paleta de series stacked (modo "por UA"). Espelha a paleta canonica
// de chart series (chartUtils.ts CLAUDE.md §4) — slate vem primeiro
// (mesmo da serie default single).
const STACKED_PALETTE = [
  "#64748B", // slate-500
  "#0EA5E9", // sky-500
  "#14B8A6", // teal-500
  "#10B981", // emerald-500
  "#F59E0B", // amber-500
  "#F43F5E", // rose-500
  "#8B5CF6", // violet-500
  "#6366F1", // indigo-500
]

// ─── Helpers ───────────────────────────────────────────────────────────────

function fmtDayShort(iso: string): string {
  const day = iso.slice(8, 10)
  return day
}

function fmtDayLong(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number)
  const dt = new Date(y, (m ?? 1) - 1, d ?? 1)
  return dt.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "short",
    weekday: "short",
  })
}

/**
 * Regressao linear (minimos quadrados) sobre os indices dos dias com valor.
 * Retorna array completo do tamanho da serie — para indices sem valor
 * (dias futuros ou nulos), retorna `null` pra ECharts pular a interpolacao.
 */
function computeTrendLine(values: Array<number | null>): Array<number | null> {
  const present: Array<{ x: number; y: number }> = []
  values.forEach((v, i) => {
    if (v != null) present.push({ x: i, y: v })
  })
  if (present.length < 2) return values.map(() => null)
  let sumX = 0,
    sumY = 0,
    sumXY = 0,
    sumX2 = 0
  for (const { x, y } of present) {
    sumX += x
    sumY += y
    sumXY += x * y
    sumX2 += x * x
  }
  const n = present.length
  const denom = n * sumX2 - sumX * sumX
  if (denom === 0) {
    const mean = sumY / n
    return values.map(() => mean)
  }
  const slope = (n * sumXY - sumX * sumY) / denom
  const intercept = (sumY - slope * sumX) / n
  // Renderiza a tendencia apenas no intervalo de dias com dado real
  // (do primeiro dia presente ate o ultimo) — evita projecao no futuro.
  const firstIdx = present[0].x
  const lastIdx = present[present.length - 1].x
  return values.map((_, i) =>
    i >= firstIdx && i <= lastIdx ? intercept + slope * i : null,
  )
}

// ─── Component ─────────────────────────────────────────────────────────────

export function EvolucaoDiariaCard({
  title,
  presetLabel,
  data,
  seriesStacked,
  highlightToday = true,
  headerKpi,
  showTrendLine = true,
  valueFormatter,
  axisFormatter,
  dataLabelFormatter,
  height = 240,
  loading,
  error,
  onRetry,
  actions,
  onPointClick,
}: EvolucaoDiariaCardProps) {
  const axisFmt = axisFormatter ?? valueFormatter
  const dataLabelFmt = dataLabelFormatter ?? axisFmt
  const stackedMode = seriesStacked != null && seriesStacked.length > 0
  // Trend line so faz sentido em single (stacked tem multiplas series).
  const effectiveShowTrend = stackedMode ? false : showTrendLine

  // Indice do "hoje" = ultimo ponto com valor != null. No modo stacked,
  // verifica se ALGUMA serie tem valor naquele indice.
  const todayIdx = React.useMemo(() => {
    if (stackedMode && seriesStacked) {
      for (let i = data.length - 1; i >= 0; i--) {
        const hasAny = seriesStacked.some((s) => s.values[i] != null)
        if (hasAny) return i
      }
      return -1
    }
    for (let i = data.length - 1; i >= 0; i--) {
      if (data[i].valor != null) return i
    }
    return -1
  }, [data, seriesStacked, stackedMode])

  // Caption enxuta: so o label do periodo (ex.: "Maio/2026"). Legendas
  // visuais ("barra clara = hoje", "linha tracejada = tendência") foram
  // removidas em 2026-05-19 — o usuario interpreta o grafico direto.
  const caption = presetLabel

  const option = React.useMemo<EChartsOption>(
    () =>
      stackedMode && seriesStacked
        ? buildStackedOption({
            data,
            title,
            series: seriesStacked,
            valueFormatter,
            axisFmt,
          })
        : buildOption({
            data,
            title,
            todayIdx,
            highlightToday,
            showTrendLine: effectiveShowTrend,
            valueFormatter,
            axisFmt,
            dataLabelFmt,
          }),
    [
      data,
      title,
      seriesStacked,
      stackedMode,
      todayIdx,
      highlightToday,
      effectiveShowTrend,
      valueFormatter,
      axisFmt,
      dataLabelFmt,
    ],
  )

  const echartsProps = React.useMemo(() => {
    if (!onPointClick) return undefined
    return {
      onEvents: {
        click: (params: { dataIndex?: number; seriesType?: string }) => {
          if (params.seriesType !== "bar") return
          const idx = params.dataIndex
          if (idx == null) return
          const p = data[idx]
          if (!p) return
          // No modo single, ignora dias sem valor. No stacked, qualquer
          // clique em barra (com valor em alguma serie) abre o drill.
          if (!stackedMode && p.valor == null) return
          onPointClick(p.data)
        },
      },
    }
  }, [onPointClick, data, stackedMode])

  return (
    <EChartsCard
      title={title}
      caption={caption}
      headerKpi={headerKpi}
      option={option}
      height={height}
      loading={loading}
      error={error}
      onRetry={onRetry}
      actions={actions}
      echartsProps={echartsProps}
    />
  )
}

// ─── Builder ───────────────────────────────────────────────────────────────

type BuildOptionArgs = {
  data: EvolucaoDiariaPonto[]
  title: string
  todayIdx: number
  highlightToday: boolean
  showTrendLine: boolean
  valueFormatter: (v: number) => string
  axisFmt: (v: number) => string
  dataLabelFmt: (v: number) => string
}

function buildOption({
  data,
  title,
  todayIdx,
  highlightToday,
  showTrendLine,
  valueFormatter,
  axisFmt,
  dataLabelFmt,
}: BuildOptionArgs): EChartsOption {
  const labels = data.map((p) => fmtDayShort(p.data))
  const valores = data.map((p) => p.valor)
  const trend = showTrendLine ? computeTrendLine(valores) : null

  // Quando ehDiaUtil for explicitamente false, deixa o label do eixo X dim.
  const axisLabelColors = data.map((p) =>
    p.ehDiaUtil === false ? COLOR_AXIS_LABEL_DIM : COLOR_AXIS_LABEL_DEFAULT,
  )

  const tooltip: EChartsOption["tooltip"] = {
    trigger: "axis",
    axisPointer: { type: "shadow" },
    formatter: (params: unknown) => {
      const arr = params as Array<{ dataIndex: number }>
      if (!Array.isArray(arr) || arr.length === 0) return ""
      const idx = arr[0].dataIndex
      const p = data[idx]
      if (!p) return ""
      const lines = [`<strong>${fmtDayLong(p.data)}</strong>`]
      if (p.valor == null) {
        lines.push("Dia futuro · sem dados")
      } else {
        lines.push(`${title}: ${valueFormatter(p.valor)}`)
        if (p.ehDiaUtil === false) {
          lines.push(
            `<span style="color:${COLOR_AXIS_LABEL_DIM}">não é dia útil</span>`,
          )
        }
      }
      if (p.tooltipExtras) {
        for (const e of p.tooltipExtras) lines.push(`${e.label}: ${e.value}`)
      }
      return lines.join("<br/>")
    },
  }

  const xAxis: EChartsOption["xAxis"] = {
    type: "category",
    data: labels,
    axisTick: { show: false },
    axisPointer: { label: { show: false } },
    axisLabel: {
      fontSize: 10,
      interval: 0,
      // ECharts assina `color` como `(value?, index?) => string`. Usamos o
      // index pra colorir dim em sab/dom/feriado. Hex literal e excecao §4
      // — canvas ECharts.
      color: (_value?: string | number, index?: number): string =>
        (index != null ? axisLabelColors[index] : undefined) ??
        COLOR_AXIS_LABEL_DEFAULT,
    },
  }

  const yAxis: EChartsOption["yAxis"] = {
    type: "value",
    axisLabel: { formatter: axisFmt },
    axisPointer: { label: { show: false } },
  }

  const grid: EChartsOption["grid"] = {
    top: 16,
    right: 12,
    bottom: 28,
    left: 64,
  }

  const trendSeries =
    showTrendLine && trend
      ? [
          {
            name: "Tendência",
            type: "line" as const,
            smooth: true,
            symbol: "none" as const,
            data: trend,
            lineStyle: {
              color: COLOR_LINE_TREND,
              width: 1.5,
              type: "dashed" as const,
            },
            // Conecta apenas os pontos com valor — `null` no array quebra a linha
            // automaticamente (dias futuros nao sao projetados).
            connectNulls: false,
          },
        ]
      : []

  return {
    grid,
    legend: { show: false },
    tooltip,
    xAxis,
    yAxis,
    series: [
      {
        name: title,
        type: "bar",
        barMaxWidth: 18,
        label: {
          show: true,
          position: "top",
          color: COLOR_VALUE_LABEL,
          fontSize: 9,
          fontWeight: 500,
          // Mostra label apenas em dias com valor (`null` => sem label).
          formatter: (p) => {
            const v = (p as { value: number | null }).value
            return v == null ? "" : dataLabelFmt(v)
          },
        },
        data: valores.map((v, i) => {
          if (v == null) {
            // Dia futuro — barra ausente, mas slot no eixo X mantido.
            return { value: null }
          }
          const isToday = highlightToday && i === todayIdx
          const isNonUtil = data[i].ehDiaUtil === false
          const color = isToday
            ? COLOR_BAR_TODAY
            : isNonUtil
              ? COLOR_BAR_NONUTIL
              : COLOR_BAR_DEFAULT
          return {
            value: v,
            itemStyle: { color, borderRadius: [3, 3, 0, 0] },
          }
        }),
      },
      ...trendSeries,
    ],
  }
}

// ─── Builder stacked (modo "por série", ex.: por UA) ─────────────────────

type BuildStackedOptionArgs = {
  data: EvolucaoDiariaPonto[]
  title: string
  series: EvolucaoDiariaSerie[]
  valueFormatter: (v: number) => string
  axisFmt: (v: number) => string
}

function buildStackedOption({
  data,
  series,
  valueFormatter,
  axisFmt,
}: BuildStackedOptionArgs): EChartsOption {
  const labels = data.map((p) => fmtDayShort(p.data))
  const axisLabelColors = data.map((p) =>
    p.ehDiaUtil === false ? COLOR_AXIS_LABEL_DIM : COLOR_AXIS_LABEL_DEFAULT,
  )

  const tooltip: EChartsOption["tooltip"] = {
    trigger: "axis",
    axisPointer: { type: "shadow" },
    formatter: (params: unknown) => {
      const arr = params as Array<{ dataIndex: number; seriesName?: string; value?: number | null }>
      if (!Array.isArray(arr) || arr.length === 0) return ""
      const idx = arr[0].dataIndex
      const p = data[idx]
      if (!p) return ""
      const lines: string[] = [`<strong>${fmtDayLong(p.data)}</strong>`]
      let total = 0
      let hasAny = false
      for (const item of arr) {
        const v = item.value
        if (v == null) continue
        hasAny = true
        total += v
        lines.push(`${item.seriesName ?? ""}: ${valueFormatter(v)}`)
      }
      if (!hasAny) {
        lines.push("Dia futuro · sem dados")
      } else {
        lines.push(`<strong>Total: ${valueFormatter(total)}</strong>`)
      }
      if (p.ehDiaUtil === false && hasAny) {
        lines.push(
          `<span style="color:${COLOR_AXIS_LABEL_DIM}">não é dia útil</span>`,
        )
      }
      return lines.join("<br/>")
    },
  }

  const xAxis: EChartsOption["xAxis"] = {
    type: "category",
    data: labels,
    axisTick: { show: false },
    axisPointer: { label: { show: false } },
    axisLabel: {
      fontSize: 10,
      interval: 0,
      color: (_value?: string | number, index?: number): string =>
        (index != null ? axisLabelColors[index] : undefined) ??
        COLOR_AXIS_LABEL_DEFAULT,
    },
  }

  const yAxis: EChartsOption["yAxis"] = {
    type: "value",
    axisLabel: { formatter: axisFmt },
    axisPointer: { label: { show: false } },
  }

  const grid: EChartsOption["grid"] = {
    top: 16,
    right: 12,
    bottom: 40,
    left: 64,
  }

  return {
    grid,
    legend: {
      data: series.map((s) => s.name),
      bottom: 4,
      itemWidth: 10,
      itemHeight: 10,
      icon: "circle",
      textStyle: { fontSize: 11 },
    },
    tooltip,
    xAxis,
    yAxis,
    series: series.map((s, i) => ({
      name: s.name,
      type: "bar",
      stack: "total",
      barMaxWidth: 18,
      emphasis: { focus: "series" },
      itemStyle: {
        color: s.color ?? STACKED_PALETTE[i % STACKED_PALETTE.length],
        borderRadius: i === series.length - 1 ? [3, 3, 0, 0] : 0,
      },
      data: s.values,
    })),
  }
}
