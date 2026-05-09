// src/design-system/components/PvmBridgeCard/index.tsx
//
// PVM bridge para MEDIAS PONDERADAS (Taxa, Prazo). Decomposicao
// Marshall-Edgeworth: prior_avg → +mix_effect → +intra_effect → current_avg.
//
// 4 barras: prior anchor (gray-800), mix (sky-500 ou rose-500 conforme sinal),
// intra (sky-500 ou rose-500), current anchor (gray-800).
//
// Detalhe (top contributors por efeito) sai no DrillDownSheet quando user
// clica num dos efeitos centrais.

"use client"

import * as React from "react"
import type { EChartsOption } from "echarts"

import {
  EChartsCard,
  type EChartsCardHeaderKpi,
} from "@/design-system/components/EChartsCard"
import type { Operacoes2PvmBridgeData } from "@/lib/api-client"

const COLOR_ANCHOR = "#1F2937"
const COLOR_ANCHOR_DARK = "#E5E7EB"
const COLOR_POSITIVE = "#10B981"
const COLOR_NEGATIVE = "#F43F5E"

type PvmBarKind = "anchor" | "mix" | "intra"

type PvmBar = {
  category: string
  bar: number
  base: number
  color: string
  colorDark?: string
  kind: PvmBarKind
  realValue: number
  /** Valor "absoluto" do anchor (so quando kind === 'anchor'). */
  anchorValue?: number
}

function buildBars(data: Operacoes2PvmBridgeData): PvmBar[] {
  const bars: PvmBar[] = []
  bars.push({
    category: data.prior_anchor_label,
    bar: data.prior_anchor_value,
    base: 0,
    color: COLOR_ANCHOR,
    colorDark: COLOR_ANCHOR_DARK,
    kind: "anchor",
    realValue: data.prior_anchor_value,
    anchorValue: data.prior_anchor_value,
  })

  let running = data.prior_anchor_value

  // Mix effect
  const mix = data.mix_effect
  bars.push({
    category: "Mix",
    bar: Math.abs(mix),
    base: mix >= 0 ? running : running + mix,
    color: mix >= 0 ? COLOR_POSITIVE : COLOR_NEGATIVE,
    kind: "mix",
    realValue: mix,
  })
  running += mix

  // Intra effect — exibido como "Categoria" no eixo X (mais legivel que jargao
  // PVM para usuario nao-FP&A).
  const intra = data.intra_effect
  bars.push({
    category: "Categoria",
    bar: Math.abs(intra),
    base: intra >= 0 ? running : running + intra,
    color: intra >= 0 ? COLOR_POSITIVE : COLOR_NEGATIVE,
    kind: "intra",
    realValue: intra,
  })
  running += intra

  // Current anchor
  bars.push({
    category: data.current_anchor_label,
    bar: data.current_anchor_value,
    base: 0,
    color: COLOR_ANCHOR,
    colorDark: COLOR_ANCHOR_DARK,
    kind: "anchor",
    realValue: data.current_anchor_value,
    anchorValue: data.current_anchor_value,
  })

  return bars
}

const fmtPct2 = (v: number) => `${v.toFixed(2).replace(".", ",")}%`
const fmtDays = (v: number) => `${v.toFixed(1).replace(".", ",")}d`

function fmtUnitSigned(v: number, unit: "pp" | "dias"): string {
  const sinal = v >= 0 ? "+" : "−"
  const abs = Math.abs(v)
  if (unit === "pp") {
    return `${sinal}${abs.toFixed(2).replace(".", ",")}pp`
  }
  return `${sinal}${abs.toFixed(1).replace(".", ",")}d`
}

function fmtAnchor(value: number, unit: "pp" | "dias"): string {
  if (unit === "pp") return fmtPct2(value)
  return fmtDays(value)
}

export interface PvmBridgeCardProps {
  data: Operacoes2PvmBridgeData
  /** Titulo do card. Ex.: "Taxa media", "Prazo medio". */
  title: string
  /** Caption do card (default: delta total formatado na unidade do KPI). */
  caption?: string
  /**
   * KPI editorial no header. Default: auto-derivado de `current_anchor_value`
   * + `delta` (na unidade do KPI). Passe `null` para suprimir e voltar ao
   * header classico. Para metricas onde subir e ruim (Prazo medio, etc.),
   * passe explicitamente com `good: false` no delta.
   */
  headerKpi?: EChartsCardHeaderKpi | null
  /** Callback quando user clica em "Mix" ou "Intra" (anchors nao). */
  onEffectClick?: (kind: "mix" | "intra", data: Operacoes2PvmBridgeData) => void
  height?: number
  footer?: React.ReactNode
  actions?: React.ReactNode
  className?: string
}

export function PvmBridgeCard({
  data,
  title,
  caption,
  headerKpi,
  onEffectClick,
  height = 280,
  footer,
  actions,
  className,
}: PvmBridgeCardProps) {
  const bars = React.useMemo(() => buildBars(data), [data])

  // KPI auto-derivado quando o caller nao passou explicitamente.
  // good=delta>=0 (default — taxa subindo = bom); para Prazo, caller passa
  // headerKpi explicito com good: false.
  const autoHeaderKpi = React.useMemo<EChartsCardHeaderKpi | undefined>(() => {
    if (headerKpi !== undefined) return headerKpi ?? undefined
    return {
      value: fmtAnchor(data.current_anchor_value, data.delta_unidade),
      delta: { value: data.delta, suffix: data.delta_unidade === "pp" ? "pp" : "d" },
      deltaSub: data.current_anchor_label,
    }
  }, [headerKpi, data])

  // Caption omitida quando headerKpi auto-derivado: o periodo "abr/26 →
  // mai/26" e comunicado via labels em negrito do eixo X (anchors).
  const autoCaption = React.useMemo<string | undefined>(() => {
    if (caption) return caption
    if (autoHeaderKpi) return undefined
    return `Δ ${fmtUnitSigned(data.delta, data.delta_unidade)} entre ${data.prior_anchor_label} e ${data.current_anchor_label}`
  }, [data, caption, autoHeaderKpi])

  const option: EChartsOption = React.useMemo(
    () => ({
      grid: { top: 28, right: 16, bottom: 28, left: 56 },
      legend: { show: false },
      xAxis: {
        type: "category",
        data: bars.map((b) => b.category),
        axisLabel: {
          fontSize: 11,
          // Anchors (primeiro e ultimo bar) em negrito chamam atencao dos
          // dois periodos em analise. Substitui a caption "prior_label →
          // current_label" que era redundante com o eixo. Cor herda do tema.
          formatter: (value: string, index: number) => {
            const bar = bars[index]
            return bar?.kind === "anchor" ? `{a|${value}}` : value
          },
          rich: {
            a: { fontWeight: "bold" },
          },
        },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        // scale=true: eixo nao parte do zero, encaixa nos dados — torna mix
        // e intra effects (pequenos vs anchors) legiveis em fracao da altura.
        scale: true,
        axisLabel: {
          formatter: (v: number) => fmtAnchor(v, data.delta_unidade),
          fontSize: 10,
        },
        splitLine: { show: true, lineStyle: { type: "dashed", opacity: 0.5 } },
      },
      tooltip: {
        trigger: "item",
        formatter: (params: unknown) => {
          const p = params as { dataIndex: number }
          const bar = bars[p.dataIndex]
          if (!bar) return ""
          if (bar.kind === "anchor") {
            return `<b>${bar.category}</b><br/>${fmtAnchor(bar.realValue, data.delta_unidade)}`
          }
          const isMix = bar.kind === "mix"
          const titleLabel = isMix
            ? "Mix (mudanca de composicao)"
            : "Categoria (variacao dentro da categoria)"
          const lines = [
            `<b>${titleLabel}</b>`,
            fmtUnitSigned(bar.realValue, data.delta_unidade),
            "Click para ver contribuintes",
          ]
          return lines.join("<br/>")
        },
      },
      series: [
        {
          // Placeholder INVISIVEL — ECharts nao respeita "transparent" direto
          // (cai na paleta do tema). rgba(0,0,0,0) + opacity:0 garante.
          name: "Base",
          type: "bar",
          stack: "pvm",
          itemStyle: {
            color: "rgba(0,0,0,0)",
            borderColor: "rgba(0,0,0,0)",
            opacity: 0,
          },
          emphasis: { disabled: true },
          data: bars.map((b) => b.base),
          silent: true,
        },
        {
          name: "Valor",
          type: "bar",
          stack: "pvm",
          barCategoryGap: "30%",
          data: bars.map((b) => ({
            value: b.bar,
            itemStyle: { color: b.color },
          })),
          label: {
            show: true,
            position: "top",
            fontSize: 10,
            formatter: (params: { dataIndex: number }) => {
              const bar = bars[params.dataIndex]
              if (!bar) return ""
              if (bar.kind === "anchor") {
                return fmtAnchor(bar.realValue, data.delta_unidade)
              }
              return fmtUnitSigned(bar.realValue, data.delta_unidade)
            },
          },
          cursor: "pointer",
        },
      ],
    }),
    [bars, data.delta_unidade],
  )

  const handleEvents = React.useMemo(
    () => ({
      click: (params: { dataIndex: number; componentType: string }) => {
        if (params.componentType !== "series") return
        const bar = bars[params.dataIndex]
        if (!bar || bar.kind === "anchor") return
        if (onEffectClick) onEffectClick(bar.kind, data)
      },
    }),
    [bars, data, onEffectClick],
  )

  return (
    <EChartsCard
      option={option}
      title={title}
      caption={autoCaption}
      headerKpi={autoHeaderKpi}
      height={height}
      actions={actions}
      footer={footer}
      className={className}
      echartsProps={{ onEvents: handleEvents }}
    />
  )
}
