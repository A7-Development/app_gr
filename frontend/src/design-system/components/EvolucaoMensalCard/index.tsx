// src/design-system/components/EvolucaoMensalCard/index.tsx
//
// Card canonico para series temporais mensais com filtro de dimensao opcional
// e footer de destaques (melhor mes, pior mes, mes corrente vs media).
//
// Compõe `EChartsCard` (header + actions + caption + footer + chart). Não
// reinventa a casca — adiciona vocabulario de "evolucao mensal" + filtro de
// dimensao no slot `actions` + destaques no slot `footer`.
//
// Uso (exemplo simples):
//   <EvolucaoMensalCard
//     title="Evolução do VOP"
//     presetLabel="Últimos 12 meses"
//     data={[{ periodo: "2025-05", valor: 1200000, comparativo: 1100000 }, ...]}
//     comparativoLabel="MM 3M"
//     valueFormatter={(v) => fmtBRL.format(v)}
//   />
//
// Uso com filtro de dimensao + destaques:
//   <EvolucaoMensalCard
//     title="Evolução do VOP"
//     presetLabel={presetLabel}
//     data={slice}
//     dimension={{
//       label: "UA",
//       icon: RiBuilding2Line,
//       options: uaOptions,
//       value: selectedUaId,
//       onChange: setSelectedUaId,
//       allLabel: "Todas as UAs",
//     }}
//     comparativoLabel="MM 3M"
//     destaques={{ melhor, pior, vsMedia }}
//     valueFormatter={fmtBRLFull.format}
//     axisFormatter={fmtBRL.format}
//   />
//
// Variants:
//   - "bar+line": barras + linha tracejada do comparativo (default).
//   - "line":     duas linhas suaves (principal + comparativo).
//   - "area":     area com gradient + linha tracejada do comparativo.
//
// Hex literals neste arquivo sao excecao canonica do CLAUDE.md §4 — Tailwind
// nao alcanca o canvas ECharts.

"use client"

import * as React from "react"
import type { EChartsOption } from "echarts"
import { RiCheckLine, type RemixiconComponentType } from "@remixicon/react"

import { EChartsCard } from "../EChartsCard"
import { FilterChip } from "../FilterBar"
import { cx } from "@/lib/utils"

// ─── Tipos publicos ─────────────────────────────────────────────────────────

export type EvolucaoMensalPonto = {
  /** Periodo no formato ISO "YYYY-MM". */
  periodo: string
  /** Valor principal da serie. */
  valor: number
  /** Valor comparativo no mesmo periodo (ex.: media movel 3M). null = nao calculado. */
  comparativo?: number | null
  /** Linhas extras no tooltip — caller pre-formata os valores como string. */
  tooltipExtras?: Array<{ label: string; value: string }>
}

export type EvolucaoMensalVariant = "bar+line" | "line" | "area"

export type EvolucaoMensalDimensionOption<T extends number | string = number | string> = {
  id: T
  nome: string
}

export type EvolucaoMensalDimensionConfig<T extends number | string = number | string> = {
  /** Label curto exibido no FilterChip (ex.: "UA"). */
  label: string
  /** Icone do FilterChip. */
  icon: RemixiconComponentType
  /** Opcoes selecionaveis. */
  options: EvolucaoMensalDimensionOption<T>[]
  /** Valor selecionado. null = "todas". */
  value: T | null
  /** Callback ao trocar selecao. null = voltou pra "todas". */
  onChange: (value: T | null) => void
  /** Label do estado "todas as opcoes" (ex.: "Todas as UAs"). */
  allLabel: string
}

export type EvolucaoMensalMesDestaque = {
  periodo: string
  valor: number
}

export type EvolucaoMensalVsMedia = {
  /** Variacao percentual do mes corrente vs media (ex.: 12.3 = +12,3%). */
  pct: number
}

export type EvolucaoMensalDestaques = {
  melhor?: EvolucaoMensalMesDestaque | null
  pior?: EvolucaoMensalMesDestaque | null
  vsMedia?: EvolucaoMensalVsMedia | null
}

export type EvolucaoMensalCardProps = {
  /** Titulo do card (ex.: "Evolução do VOP"). */
  title: string
  /** Label do periodo apurado (ex.: "Últimos 12 meses"). Compoe a caption. */
  presetLabel: string
  /** Pontos da serie temporal — caller filtra antes de passar. */
  data: EvolucaoMensalPonto[]
  /** Filtro de dimensao opcional — renderiza FilterChip no slot `actions`. */
  dimension?: EvolucaoMensalDimensionConfig
  /** Visualizacao. Default: "bar+line". */
  variant?: EvolucaoMensalVariant
  /** Label da serie comparativa (ex.: "MM 3M"). Quando setado, compoe a caption. */
  comparativoLabel?: string
  /** Destaca o ultimo ponto (mes corrente) com cor diferente. So vale para "bar+line". Default: true. */
  highlightLast?: boolean
  /** Footer com melhor/pior/vs media. Quando setado, renderiza no slot `footer`. */
  destaques?: EvolucaoMensalDestaques
  /** Formatador para tooltips e destaques (ex.: BRL completo). */
  valueFormatter: (v: number) => string
  /** Formatador do eixo Y. Default: igual a valueFormatter. */
  axisFormatter?: (v: number) => string
  /** Formatador dos rotulos no topo das barras (variant "bar+line"). Default: igual a axisFormatter. */
  dataLabelFormatter?: (v: number) => string
  /** Altura do canvas. Default: 240. */
  height?: number
  loading?: boolean
  error?: string | null
  onRetry?: () => void
}

// ─── Cores das series (hex inline — excecao §4) ────────────────────────────

const COLOR_BAR_DEFAULT = "#2A4D7A"
const COLOR_BAR_CURRENT = "#0EA5E9"
const COLOR_LINE_DASHED = "#9CA3AF"
const COLOR_AREA_LINE = "#2A4D7A"
const COLOR_AREA_FILL_TOP = "rgba(42,77,122,0.32)"
const COLOR_AREA_FILL_BOTTOM = "rgba(42,77,122,0)"
const COLOR_VALUE_LABEL = "#374151"

// ─── Helpers internos ──────────────────────────────────────────────────────

function fmtMonthShort(iso: string): string {
  const [y, m] = iso.split("-").map(Number)
  return new Date(y, (m ?? 1) - 1, 1)
    .toLocaleString("pt-BR", { month: "short", year: "2-digit" })
    .replace(".", "")
}

function fmtPct1(v: number): string {
  return `${v.toFixed(1).replace(".", ",")}%`
}

// ─── Component ─────────────────────────────────────────────────────────────

export function EvolucaoMensalCard({
  title,
  presetLabel,
  data,
  dimension,
  variant = "bar+line",
  comparativoLabel,
  highlightLast = true,
  destaques,
  valueFormatter,
  axisFormatter,
  dataLabelFormatter,
  height = 240,
  loading,
  error,
  onRetry,
}: EvolucaoMensalCardProps) {
  const axisFmt = axisFormatter ?? valueFormatter
  const dataLabelFmt = dataLabelFormatter ?? axisFmt

  const dimensionLabel = React.useMemo(() => {
    if (!dimension) return null
    if (dimension.value === null) return dimension.allLabel
    return (
      dimension.options.find((o) => o.id === dimension.value)?.nome ?? "(n/d)"
    )
  }, [dimension])

  const caption = React.useMemo(() => {
    const parts: string[] = []
    if (dimensionLabel) parts.push(dimensionLabel)
    parts.push(presetLabel)
    if (highlightLast && variant === "bar+line") {
      parts.push("barra clara = mês corrente")
    }
    if (comparativoLabel) parts.push(`linha tracejada = ${comparativoLabel}`)
    return parts.join(" · ")
  }, [dimensionLabel, presetLabel, highlightLast, variant, comparativoLabel])

  const option = React.useMemo<EChartsOption>(() => {
    return buildOption({
      data,
      title,
      variant,
      comparativoLabel,
      highlightLast,
      valueFormatter,
      axisFmt,
      dataLabelFmt,
    })
  }, [data, title, variant, comparativoLabel, highlightLast, valueFormatter, axisFmt, dataLabelFmt])

  const actions = dimension ? (
    <FilterChip
      label={dimension.label}
      value={dimensionLabel ?? dimension.allLabel}
      active={dimension.value !== null}
      icon={dimension.icon}
    >
      <div className="py-1">
        <DimensionPickerItem
          label={dimension.allLabel}
          selected={dimension.value === null}
          onSelect={() => dimension.onChange(null)}
        />
        {dimension.options.map((o) => (
          <DimensionPickerItem
            key={String(o.id)}
            label={o.nome}
            selected={dimension.value === o.id}
            onSelect={() => dimension.onChange(o.id)}
          />
        ))}
      </div>
    </FilterChip>
  ) : undefined

  const footer = destaques ? (
    <EvolucaoMensalDestaquesView
      destaques={destaques}
      valueFormatter={valueFormatter}
    />
  ) : undefined

  return (
    <EChartsCard
      title={title}
      caption={caption}
      option={option}
      height={height}
      actions={actions}
      footer={footer}
      loading={loading}
      error={error}
      onRetry={onRetry}
    />
  )
}

// ─── Sub-view do footer (exportado) ────────────────────────────────────────

export function EvolucaoMensalDestaquesView({
  destaques,
  valueFormatter,
}: {
  destaques: EvolucaoMensalDestaques
  valueFormatter: (v: number) => string
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-1 pt-2 text-[11px] text-gray-500 dark:text-gray-400">
      {destaques.melhor && (
        <span>
          Melhor mês:{" "}
          <strong className="text-gray-900 dark:text-gray-50">
            {fmtMonthShort(destaques.melhor.periodo)}
          </strong>{" "}
          ({valueFormatter(destaques.melhor.valor)})
        </span>
      )}
      {destaques.pior && (
        <span>
          Pior mês:{" "}
          <strong className="text-gray-900 dark:text-gray-50">
            {fmtMonthShort(destaques.pior.periodo)}
          </strong>{" "}
          ({valueFormatter(destaques.pior.valor)})
        </span>
      )}
      {destaques.vsMedia && (
        <span>
          Mês corrente vs média:{" "}
          <strong
            className={cx(
              "font-semibold",
              destaques.vsMedia.pct >= 0
                ? "text-emerald-600 dark:text-emerald-400"
                : "text-red-600 dark:text-red-400",
            )}
          >
            {destaques.vsMedia.pct >= 0 ? "+" : ""}
            {fmtPct1(destaques.vsMedia.pct)}
          </strong>
        </span>
      )}
    </div>
  )
}

// ─── Helpers internos: builder de option e item do picker ──────────────────

type BuildOptionArgs = {
  data: EvolucaoMensalPonto[]
  title: string
  variant: EvolucaoMensalVariant
  comparativoLabel?: string
  highlightLast: boolean
  valueFormatter: (v: number) => string
  axisFmt: (v: number) => string
  dataLabelFmt: (v: number) => string
}

function buildOption({
  data,
  title,
  variant,
  comparativoLabel,
  highlightLast,
  valueFormatter,
  axisFmt,
  dataLabelFmt,
}: BuildOptionArgs): EChartsOption {
  const labels = data.map((p) => fmtMonthShort(p.periodo))
  const valores = data.map((p) => p.valor)
  const comparativo = data.map((p) => (p.comparativo == null ? null : p.comparativo))
  const lastIdx = data.length - 1

  const tooltip: EChartsOption["tooltip"] = {
    trigger: "axis",
    axisPointer: { type: variant === "bar+line" ? "shadow" : "line" },
    formatter: (params: unknown) => {
      const arr = params as Array<{ name: string; dataIndex: number }>
      if (!Array.isArray(arr) || arr.length === 0) return ""
      const idx = arr[0].dataIndex
      const p = data[idx]
      if (!p) return ""
      const lines = [
        `<strong>${arr[0].name}</strong>`,
        `${title}: ${valueFormatter(p.valor)}`,
      ]
      if (comparativoLabel) {
        const v = p.comparativo
        lines.push(
          `${comparativoLabel}: ${v == null ? "—" : valueFormatter(v)}`,
        )
      }
      if (p.tooltipExtras) {
        for (const e of p.tooltipExtras) lines.push(`${e.label}: ${e.value}`)
      }
      return lines.join("<br/>")
    },
  }

  // axisPointer.label.show:false em ambos os eixos suprime o "chip" colorido
  // que o tema global do projeto (echarts-theme.ts) projeta nos eixos ao hover.
  // Per-axis tem precedencia sobre top-level e tooltip.axisPointer no ECharts.
  const xAxis: EChartsOption["xAxis"] = {
    type: "category",
    data: labels,
    axisTick: { show: false },
    axisPointer: { label: { show: false } },
    ...(variant !== "bar+line" ? { boundaryGap: false } : {}),
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

  const comparativoSeries =
    comparativoLabel != null
      ? [
          {
            name: comparativoLabel,
            type: "line" as const,
            smooth: true,
            symbol: "none" as const,
            data: comparativo,
            lineStyle: {
              color: COLOR_LINE_DASHED,
              width: 1.5,
              type: "dashed" as const,
            },
          },
        ]
      : []

  if (variant === "bar+line") {
    return {
      grid,
      tooltip,
      xAxis,
      yAxis,
      series: [
        {
          name: title,
          type: "bar",
          barMaxWidth: 32,
          label: {
            show: true,
            position: "top",
            color: COLOR_VALUE_LABEL,
            fontSize: 10,
            fontWeight: 500,
            formatter: (p) => dataLabelFmt((p as { value: number }).value),
          },
          data: valores.map((v, i) => ({
            value: v,
            itemStyle: {
              color:
                highlightLast && i === lastIdx
                  ? COLOR_BAR_CURRENT
                  : COLOR_BAR_DEFAULT,
              borderRadius: [3, 3, 0, 0],
            },
          })),
        },
        ...comparativoSeries,
      ],
    }
  }

  if (variant === "line") {
    return {
      grid,
      tooltip,
      xAxis,
      yAxis,
      series: [
        {
          name: title,
          type: "line",
          smooth: true,
          symbol: "none",
          data: valores,
          lineStyle: { color: COLOR_AREA_LINE, width: 2 },
        },
        ...comparativoSeries,
      ],
    }
  }

  // variant === "area"
  return {
    grid,
    tooltip,
    xAxis,
    yAxis,
    series: [
      {
        name: title,
        type: "line",
        smooth: true,
        symbol: "none",
        data: valores,
        lineStyle: { color: COLOR_AREA_LINE, width: 2 },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: COLOR_AREA_FILL_TOP },
              { offset: 1, color: COLOR_AREA_FILL_BOTTOM },
            ],
          },
        },
      },
      ...comparativoSeries,
    ],
  }
}

function DimensionPickerItem({
  label,
  selected,
  onSelect,
}: {
  label: string
  selected: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cx(
        "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
        selected
          ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
          : "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800",
      )}
    >
      <span className="flex-1 truncate text-left">{label}</span>
      {selected && (
        <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />
      )}
    </button>
  )
}
