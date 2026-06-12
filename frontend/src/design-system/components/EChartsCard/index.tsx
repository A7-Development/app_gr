// src/design-system/components/EChartsCard/index.tsx
// Wrapper around echarts-for-react.
// Adds: ResizeObserver reflow, caption slot, footer slot, error/retry,
//       notMerge + lazyUpdate defaults, useEChartsTheme() auto dark/light.

"use client"

import * as React from "react"
import ReactECharts from "echarts-for-react"
import type { EChartsOption } from "echarts"
import {
  RiArrowDownLine,
  RiArrowUpLine,
  RiErrorWarningLine,
  RiRefreshLine,
} from "@remixicon/react"
import { cx } from "@/lib/utils"
import { useEChartsTheme } from "@/design-system/tokens/echarts-theme"
import { OriginDot } from "@/design-system/components/OriginDot"
import type { Provenance } from "@/design-system/types/provenance"

export { useEChartsTheme }

// ════════════════════════════════════════════════════════════════════════
// HeaderKpi — KPI editorial no header do card (CLAUDE.md §7,
// docs/bi-patterns-presentacao-dados.md §4.3 "Hero Chart com KPI no titulo").
//
// Quando passado, transforma o header do card em "eyebrow + valor + delta":
//
//   ┌─ VOP ────────────────────────── [actions] ┐  ← title vira eyebrow
//   │ R$ 3,7 mi  ↑ 4,2%  MTD                    │  ← value + delta inline
//   │ caption opcional abaixo                   │
//   └───────────────────────────────────────────┘
//
// Regra de uso: o `value` representa O numero que aquele card explica. Numero
// que nao casa com a abertura analitica do card abaixo (ex.: total de soma,
// nao da pra exibir como inteiro) deve ficar em `caption` ou no proprio chart.
// ════════════════════════════════════════════════════════════════════════

export type EChartsCardHeaderKpiDelta = {
  /** Valor numerico do delta. */
  value: number
  /** Sufixo (ex.: "%", "pp", "d"). Default: "". */
  suffix?: string
  /**
   * Casas decimais FIXAS (min = max). Quando definido, o delta sempre mostra
   * exatamente N casas (ex.: `2` -> "4,20%"). Quando undefined, mantem o
   * comportamento legado (ate 2 casas, sem minimo: "4,2%").
   */
  fractionDigits?: number
  /** Direcao do indicador. Default: infere do sinal. */
  direction?: "up" | "down"
  /**
   * Bom (verde) vs ruim (vermelho). Default: `direction === "up"`.
   * Para metricas onde subir e ruim (prazo, inadimplencia), passar
   * `good: false` quando o valor for positivo.
   */
  good?: boolean
}

export type EChartsCardHeaderKpi = {
  /** Numero principal pre-formatado (ex.: "R$ 3,7 mi", "1,8%", "32 d"). */
  value: string
  /** Delta opcional. */
  delta?: EChartsCardHeaderKpiDelta
  /** Texto inline pos-delta (ex.: "MTD", "vs mês anterior"). */
  deltaSub?: string
}

function HeaderKpiInline({ kpi }: { kpi: EChartsCardHeaderKpi }) {
  const dir =
    kpi.delta?.direction ??
    (kpi.delta && kpi.delta.value >= 0 ? "up" : "down")
  const good = kpi.delta?.good ?? dir === "up"
  const ArrowIcon = dir === "up" ? RiArrowUpLine : RiArrowDownLine
  const deltaColor = good
    ? "text-emerald-600 dark:text-emerald-400"
    : "text-red-600 dark:text-red-400"

  return (
    <p className="mt-1 flex flex-wrap items-baseline gap-x-2 tabular-nums">
      <span className="text-[20px] font-semibold leading-none tracking-tight text-gray-900 dark:text-gray-50">
        {kpi.value}
      </span>
      {kpi.delta && (
        <span
          className={cx(
            "inline-flex items-baseline whitespace-nowrap text-xs font-medium",
            deltaColor,
          )}
        >
          <ArrowIcon
            className="mr-0.5 inline size-3 shrink-0 align-[-0.125em]"
            aria-hidden="true"
          />
          {Math.abs(kpi.delta.value).toLocaleString("pt-BR", {
            minimumFractionDigits: kpi.delta.fractionDigits ?? 0,
            maximumFractionDigits: kpi.delta.fractionDigits ?? 2,
          })}
          {kpi.delta.suffix ?? ""}
        </span>
      )}
      {kpi.deltaSub && (
        <span className="text-[11px] text-gray-500 dark:text-gray-400">
          {kpi.deltaSub}
        </span>
      )}
    </p>
  )
}

function ChartSkeleton({ height }: { height: number }) {
  return (
    <div
      className="w-full animate-pulse rounded bg-gray-100 dark:bg-gray-800"
      style={{ height }}
      aria-busy="true"
      aria-label="Carregando gráfico"
    />
  )
}

function ChartError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-8">
      <RiErrorWarningLine className="size-6 text-red-400" aria-hidden="true" />
      <p className="text-xs text-gray-500 dark:text-gray-400">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-1 rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-950 px-2.5 py-1 text-xs font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-900 transition-colors"
        >
          <RiRefreshLine className="size-3.5" aria-hidden="true" />
          Tentar novamente
        </button>
      )}
    </div>
  )
}

export interface EChartsCardProps {
  option:        EChartsOption
  height?:       number
  loading?:      boolean
  error?:        string | null
  onRetry?:      () => void
  title?:        string
  caption?:      string
  /**
   * KPI editorial no header (docs/bi-patterns-presentacao-dados.md §4.3).
   * Quando presente, o `title` vira eyebrow (uppercase, smaller) e o KPI
   * `{ value, delta?, deltaSub? }` ocupa o espaco visual de "lead".
   * Substitui o paradigma de KpiStrip page-level — cada card carrega O
   * numero que ele decompoe.
   */
  headerKpi?:    EChartsCardHeaderKpi
  actions?:      React.ReactNode
  footer?:       React.ReactNode
  /**
   * Proveniencia canonica dos dados do chart (CLAUDE.md §14.1).
   * Renderiza dot pequeno no rodape direito do card com tooltip de
   * fonte + adapter@versao + sincronizacao + trust level.
   * Mock = `undefined | null` (dot some).
   */
  provenance?:   Provenance | null
  /**
   * Quando true, remove a borda + shadow + bg branco do wrapper externo
   * do card — usar quando o EChartsCard ja esta dentro de outro <Card>
   * (evita "borda dupla"). Mantem o internal layout do header/footer/canvas.
   */
  embedded?:     boolean
  className?:    string
  echartsProps?: Omit<React.ComponentProps<typeof ReactECharts>, "option" | "style">
}

export function EChartsCard({
  option,
  height  = 240,
  loading = false,
  error   = null,
  onRetry,
  title,
  caption,
  headerKpi,
  actions,
  footer,
  provenance,
  embedded = false,
  className,
  echartsProps,
}: EChartsCardProps) {
  const theme = useEChartsTheme()
  const chartRef = React.useRef<ReactECharts | null>(null)
  const containerRef = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const ro = new ResizeObserver(() => {
      chartRef.current?.getEchartsInstance()?.resize()
    })
    ro.observe(container)
    return () => ro.disconnect()
  }, [])

  // Canvas do ECharts NAO herda CSS nem reage sozinho quando a web font (Inter
  // via next/font) termina de carregar — o 1o paint pode sair na fonte de
  // fallback ate um resize/interacao. Forca um re-render quando as fontes
  // ficam prontas. Resolve instantaneo se ja carregadas (preload no <head>).
  React.useEffect(() => {
    if (typeof document === "undefined" || !document.fonts?.ready) return
    let cancelled = false
    void document.fonts.ready.then(() => {
      if (!cancelled) chartRef.current?.getEchartsInstance()?.resize()
    })
    return () => {
      cancelled = true
    }
  }, [])

  const mergedOption: EChartsOption = React.useMemo(() => {
    const themeOption = theme as unknown as EChartsOption
    return {
      ...themeOption,
      backgroundColor: "transparent",
      ...option,
      animationDuration: option.animationDuration ?? theme.animationDuration,
      animationDurationUpdate: 0,
      tooltip: {
        ...(themeOption.tooltip as object),
        ...((option.tooltip as object) ?? {}),
      },
      axisPointer: {
        ...(themeOption.axisPointer as object),
        ...((option.axisPointer as object) ?? {}),
      },
      // O tema (echarts-theme.ts) define `visualMap.inRange.color: [...]` como
      // style default, mas o spread acima trata como visualMap real e o ECharts
      // renderiza uma barra de gradient roxa colada no eixo Y. Suprimimos por
      // default; chart que precisar de visualMap explicito sobrescreve.
      // GOTCHA (bug "barras todas da mesma cor", 2026-05-06 → 2026-06-12):
      // `{ show: false }` esconde so o WIDGET — o mapeamento de cor por valor
      // continua ativo e SEQUESTRA o itemStyle.color de TODAS as series
      // (provado via SSR: fills viram rgb(211,219,247) p/ todas). O
      // `seriesIndex: []` desliga o mapeamento de fato.
      visualMap: option.visualMap ?? { show: false, seriesIndex: [] },
    } as EChartsOption
  }, [option, theme])

  return (
    <div
      className={cx(
        "relative w-full",
        // Wrapper visual padrao: card com border + bg + shadow. Quando
        // `embedded=true`, esses estilos somem porque ja existe outro
        // <Card> em volta (evita "borda dupla"). Internals (header divider,
        // footer divider) seguem renderizando normal se forem usados.
        !embedded && "rounded border shadow-xs bg-white dark:bg-[#090E1A] border-gray-200 dark:border-gray-900",
        className,
      )}
    >
      {(title || actions || headerKpi) && (
        <div className="flex items-start justify-between gap-3 border-b border-gray-100 dark:border-gray-900 px-4 py-3">
          <div className="min-w-0">
            {/* Quando headerKpi esta presente, title vira eyebrow uppercase
                pequeno (alinhado com Linha2HeroRitmo / Linha2Projecao em
                bi/operacoes2). Sem headerKpi, mantem o estilo classico
                (text-sm font-semibold) para nao quebrar callers existentes. */}
            {title &&
              (headerKpi ? (
                <p className="truncate text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                  {title}
                </p>
              ) : (
                <h3 className="truncate text-sm font-semibold text-gray-900 dark:text-gray-50">
                  {title}
                </h3>
              ))}
            {headerKpi && <HeaderKpiInline kpi={headerKpi} />}
            {caption && (
              <p
                className={cx(
                  "text-xs text-gray-500 dark:text-gray-400",
                  headerKpi ? "mt-1.5" : "mt-0.5",
                )}
              >
                {caption}
              </p>
            )}
          </div>
          {actions && (
            <div className="flex shrink-0 items-center gap-2">{actions}</div>
          )}
        </div>
      )}

      <div ref={containerRef} className="px-4 py-3">
        {loading ? (
          <ChartSkeleton height={height} />
        ) : error ? (
          <div style={{ height }}>
            <ChartError message={error} onRetry={onRetry} />
          </div>
        ) : (
          <ReactECharts
            ref={chartRef}
            option={mergedOption}
            style={{ height, width: "100%" }}
            notMerge={false}
            lazyUpdate
            {...echartsProps}
          />
        )}
      </div>

      {footer && (
        <div className="border-t border-gray-100 dark:border-gray-900 px-4 py-2">
          {footer}
        </div>
      )}

      {/* Proveniencia (CLAUDE.md §14.1) — dot pinned no rodape direito.
          Mock (provenance undefined) = nada renderiza. */}
      {provenance && <OriginDot provenance={provenance} variant="pinned" />}
    </div>
  )
}

export interface SparkChartProps {
  data:       number[]
  color?:     string
  height?:    number
  className?: string
}

export function SparkChart({ data, color = "#3B82F6", height = 40, className }: SparkChartProps) {
  const option: EChartsOption = {
    grid:  { top: 2, right: 2, bottom: 2, left: 2 },
    xAxis: { type: "category", show: false },
    yAxis: { type: "value", show: false },
    series: [{
      type:      "line",
      data,
      smooth:    true,
      symbol:    "none",
      lineStyle: { color, width: 1.5 },
      areaStyle: { color, opacity: 0.08 },
    }],
    animation: false,
  }
  return (
    <ReactECharts
      option={option}
      style={{ height, width: "100%" }}
      className={className}
      notMerge
      lazyUpdate
    />
  )
}
