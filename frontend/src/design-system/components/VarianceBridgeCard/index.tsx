// src/design-system/components/VarianceBridgeCard/index.tsx
//
// Variance bridge (waterfall) para metricas ADITIVAS (VOP, Receita).
//
// Layout: barras verticais. 1a barra = prior anchor (gray-800), barras
// intermediarias = drivers (emerald positivo, rose negativo), ultima barra
// = current anchor (gray-800). Outros rollup aparece como ultima barra antes
// do current anchor.
//
// Click numa barra de driver chama `onDriverClick(driver)` (anchors nao
// emitem). Util pra abrir DrillDownSheet com top entidades do driver.

"use client"

import * as React from "react"
import type { EChartsOption } from "echarts"

import {
  EChartsCard,
  type EChartsCardHeaderKpi,
} from "@/design-system/components/EChartsCard"
import type {
  Operacoes2DriverContribution,
  Operacoes2VarianceBridgeData,
} from "@/lib/api-client"

// Cores: anchors em gray-800 (cor BI § 11.6), positivos em emerald-500,
// negativos em rose-500 — alinhado com chartUtils.ts.
// "Outros" segue a regra de sinal como qualquer outro driver — a natureza
// de agregado fica clara pela posicao (sempre ultimo), pelo label e pelo
// tooltip. Pintar diferente quebraria o pacto visual cor=direcao.
const COLOR_ANCHOR = "#1F2937" // gray-800
const COLOR_ANCHOR_DARK = "#E5E7EB" // gray-200 (em dark mode)
const COLOR_POSITIVE = "#10B981" // emerald-500
const COLOR_NEGATIVE = "#F43F5E" // rose-500

const fmtBRLCompact = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 2,
})

// Variante 1 casa decimal — usada nos rotulos de dados (bars) para reduzir
// ruido visual. Axis e tooltip continuam com 2 casas (precisao maior).
const fmtBRLCompact1 = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 1,
})

const fmtBRLFull = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
})

const fmtPct1 = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(1).replace(".", ",")}%`

type BridgeBarKind = "anchor" | "driver" | "outros"

type BridgeBar = {
  /** Label exibido no eixo X (curto — sigla quando aplicavel). */
  category: string
  /** Label completo, exibido no tooltip. */
  fullLabel: string
  /** Valor visivel da barra (positivo). */
  bar: number
  /** Posicao base do bar no waterfall (transparente). */
  base: number
  /** Cor da barra. */
  color: string
  /** Cor da barra em dark mode (default = mesma do light). */
  colorDark?: string
  /** Identifica o tipo pro tooltip + click handler. */
  kind: BridgeBarKind
  /** Driver original (so quando kind === 'driver' ou 'outros'). */
  driver?: Operacoes2DriverContribution
  /** Valor "real" sinalizado — pra tooltip. */
  realValue: number
}

/**
 * Heuristica: usa `member_id` como label do eixo X quando ele parece um
 * codigo curto (sigla uppercase com letras, max 8 chars, != member_label).
 * Caso contrario, usa o member_label completo.
 *
 * Casos:
 *   - produto: id="FAT", label="Faturizacao" -> sigla "FAT" no eixo
 *   - ua: id="1", "12", UUID -> falha (sem letra alfa) -> usa "Filial Centro"
 *   - faixa_ticket: id e label sao iguais -> usa label
 *   - "Outros" (rollup): id="__outros__" -> falha (tem _) -> usa "Outros"
 *
 * Bug fix 2026-05-09: regex anterior `^[A-Z0-9]+$` aceitava ids numericos
 * (id="1" da UA passava como "codigo curto"). Novo regex exige iniciar com
 * letra A-Z, garantindo que "1", "12", "999" caiam no fallback do label.
 */
function shortAxisLabel(memberId: string, memberLabel: string): string {
  const isShortCode =
    memberId.length <= 8 &&
    memberId !== memberLabel &&
    memberId === memberId.toUpperCase() &&
    /^[A-Z][A-Z0-9]*$/.test(memberId)
  return isShortCode ? memberId : memberLabel
}

/**
 * Constroi as barras do waterfall a partir dos dados.
 *
 * Esquema:
 *   - prior_anchor (barra plena, 0 -> prior_value)
 *   - Para cada driver:
 *       - se contribuicao > 0: base = running_total, bar = contrib
 *       - se contribuicao < 0: base = running_total + contrib, bar = -contrib
 *       - running_total += contrib
 *   - outros_rollup (ultima barra antes do anchor de fim, mesmas regras)
 *   - current_anchor (barra plena, 0 -> current_value)
 *
 * Anchors sao "fixos" (do zero) — facilita leitura visual de "valor total".
 */
/**
 * Piso do eixo quando `zoomToActivity`: o menor nivel (ancoras + running dos
 * drivers) menos uma folga. Faz o eixo dar ZOOM na faixa onde a acao acontece —
 * essencial quando o nivel (ex.: PL de fundo R$ 12 mi) e ordens de magnitude
 * maior que as variacoes (alguns milhares). Escala-agnostico: serve a qualquer PL.
 */
function computeFloor(data: Operacoes2VarianceBridgeData): number {
  const pts: number[] = [data.prior_anchor_value]
  let run = data.prior_anchor_value
  const middle = [...data.drivers]
  if (data.outros_rollup) middle.push(data.outros_rollup)
  for (const d of middle) {
    run += d.contribution_brl
    pts.push(run)
  }
  pts.push(data.current_anchor_value)
  const lo = Math.min(...pts)
  const hi = Math.max(...pts)
  const pad = (hi - lo) * 0.18 || Math.abs(hi) * 0.002 || 1
  return lo - pad
}

function buildBars(data: Operacoes2VarianceBridgeData, floor = 0): BridgeBar[] {
  const bars: BridgeBar[] = []
  // Prior anchor — anchors usam o mesmo label em axis e tooltip. Com `floor`
  // (zoomToActivity), a ancora desenha do piso ao valor (barra "flutuante"),
  // nao do zero — senao o nivel do PL esmaga as variacoes.
  bars.push({
    category: data.prior_anchor_label,
    fullLabel: data.prior_anchor_label,
    bar: data.prior_anchor_value - floor,
    base: floor,
    color: COLOR_ANCHOR,
    colorDark: COLOR_ANCHOR_DARK,
    kind: "anchor",
    realValue: data.prior_anchor_value,
  })

  let running = data.prior_anchor_value

  // Drivers + outros (na ordem)
  const middle = [...data.drivers]
  if (data.outros_rollup) middle.push(data.outros_rollup)

  for (const d of middle) {
    const contrib = d.contribution_brl
    const isOutros = d.member_id === "__outros__"
    const positive = contrib >= 0
    const base = positive ? running : running + contrib
    bars.push({
      category: shortAxisLabel(d.member_id, d.member_label),
      fullLabel: d.member_label,
      bar: Math.abs(contrib),
      base,
      color: positive ? COLOR_POSITIVE : COLOR_NEGATIVE,
      kind: isOutros ? "outros" : "driver",
      driver: d,
      realValue: contrib,
    })
    running += contrib
  }

  // Current anchor (do piso quando zoom, senao do zero)
  bars.push({
    category: data.current_anchor_label,
    fullLabel: data.current_anchor_label,
    bar: data.current_anchor_value - floor,
    base: floor,
    color: COLOR_ANCHOR,
    colorDark: COLOR_ANCHOR_DARK,
    kind: "anchor",
    realValue: data.current_anchor_value,
  })

  return bars
}

export interface VarianceBridgeCardProps {
  /** Dados da decomposicao. */
  data: Operacoes2VarianceBridgeData
  /** Titulo do card. Ex.: "VOP". */
  title: string
  /** Sub-titulo (caption) — costuma trazer o delta total formatado. */
  caption?: string
  /**
   * KPI editorial no header. Default: auto-derivado de
   * `current_anchor_value` + `delta_brl`/`delta_pct`. Passe `null`
   * para suprimir e voltar ao header classico.
   */
  headerKpi?: EChartsCardHeaderKpi | null
  /** Callback quando user clica num driver (anchors nao disparam). */
  onDriverClick?: (driver: Operacoes2DriverContribution) => void
  /** Altura do chart em px. Default 280. */
  height?: number
  /** Slot footer (ex.: link "Ver projecao" ou label adicional). */
  footer?: React.ReactNode
  /** Slot actions no header. */
  actions?: React.ReactNode
  /** Forca dark colors (provider deve detectar de useEChartsTheme normalmente). */
  className?: string
  /**
   * Zoom dinamico na faixa de atividade: o eixo Y vai de (menor nivel - folga)
   * ao (maior nivel + folga) e as ancoras flutuam do piso, em vez de barras
   * plenas do zero. Use quando o NIVEL (PL de fundo, NAV) e ordens de magnitude
   * maior que as VARIACOES — senao o eixo do-zero esmaga os drivers. Serve a
   * qualquer escala de PL. Default false (mantem o comportamento do operacoes2).
   */
  zoomToActivity?: boolean
}

export function VarianceBridgeCard({
  data,
  title,
  caption,
  headerKpi,
  onDriverClick,
  height = 280,
  footer,
  actions,
  className,
  zoomToActivity = false,
}: VarianceBridgeCardProps) {
  const floor = React.useMemo(
    () => (zoomToActivity ? computeFloor(data) : 0),
    [data, zoomToActivity],
  )
  const bars = React.useMemo(() => buildBars(data, floor), [data, floor])

  // KPI auto-derivado quando o caller nao passou explicitamente:
  // value = current anchor (ex.: VOP MTD), delta = delta_pct (MTD same-period).
  const autoHeaderKpi = React.useMemo<EChartsCardHeaderKpi | undefined>(() => {
    if (headerKpi !== undefined) return headerKpi ?? undefined
    return {
      value: fmtBRLCompact.format(data.current_anchor_value),
      delta:
        data.delta_pct == null
          ? undefined
          : { value: data.delta_pct, suffix: "%" },
      deltaSub: data.current_anchor_label,
    }
  }, [headerKpi, data])

  // Caption omitida quando headerKpi auto-derivado: o periodo "abr/26 →
  // mai/26" e comunicado via labels em negrito do eixo X (anchors). Sem
  // headerKpi, mantemos o auto-caption legacy com o delta total.
  const autoCaption = React.useMemo<string | undefined>(() => {
    if (caption) return caption
    if (autoHeaderKpi) return undefined
    const sinal = data.delta_brl >= 0 ? "+" : "−"
    const valor = fmtBRLCompact.format(Math.abs(data.delta_brl))
    if (data.delta_pct === null || data.delta_pct === undefined) {
      return `Δ ${sinal} ${valor}`
    }
    return `Δ ${sinal} ${valor} (${fmtPct1(data.delta_pct)})`
  }, [data, caption, autoHeaderKpi])

  const option: EChartsOption = React.useMemo(
    () => ({
      grid: { top: 24, right: 16, bottom: 28, left: 56 },
      // Sem legend — 1 chart = 1 metrica, "Base/Valor" e ruido visual.
      legend: { show: false },
      xAxis: {
        type: "category",
        data: bars.map((b) => b.category),
        axisLabel: {
          fontSize: 11,
          interval: 0,
          rotate: bars.length > 6 ? 25 : 0,
          hideOverlap: true,
          // Anchors (primeiro e ultimo bar) renderizados em negrito para
          // chamar atencao dos dois periodos em analise. Substitui a caption
          // "prior_label → current_label" que era redundante com o eixo.
          // Cor herda do tema ECharts (light/dark) — so o weight muda.
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
        // scale=true: eixo nao parte do zero, encaixa nos dados. Faz com que
        // os segments de drivers (que sao pequenos vs anchors) ocupem fracao
        // legivel da altura do chart. Com zoomToActivity, ancora explicitamente
        // no piso calculado (anchors flutuam — zoom na faixa do nivel do PL).
        scale: true,
        min: zoomToActivity ? floor : undefined,
        axisLabel: {
          formatter: (v: number) => fmtBRLCompact.format(v),
          fontSize: 10,
        },
        splitLine: { show: true, lineStyle: { type: "dashed", opacity: 0.5 } },
      },
      tooltip: {
        trigger: "item",
        formatter: (params: unknown) => {
          // params arrives as array (axis trigger) or object (item trigger)
          const p = params as {
            dataIndex: number
            seriesName: string
          }
          const bar = bars[p.dataIndex]
          if (!bar) return ""
          if (bar.kind === "anchor") {
            return `<b>${bar.fullLabel}</b><br/>${fmtBRLFull.format(bar.realValue)}`
          }
          const sinal = bar.realValue >= 0 ? "+" : "−"
          const lines = [
            `<b>${bar.fullLabel}</b>`,
            `${sinal} ${fmtBRLFull.format(Math.abs(bar.realValue))}`,
          ]
          if (bar.driver) {
            lines.push(
              `Anterior: ${fmtBRLFull.format(bar.driver.prior_value)}`,
              `Atual: ${fmtBRLFull.format(bar.driver.current_value)}`,
            )
            if (bar.driver.contribution_pct !== null) {
              lines.push(
                `${fmtPct1(bar.driver.contribution_pct)} do |Δ total|`,
              )
            }
          }
          return lines.join("<br/>")
        },
      },
      series: [
        {
          // Placeholder INVISIVEL. ECharts nao respeita color: "transparent"
          // direto (cai na paleta do tema), entao usamos rgba(0,0,0,0) + opacity:0.
          name: "Base",
          type: "bar",
          stack: "waterfall",
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
          // Barras visiveis
          name: "Valor",
          type: "bar",
          stack: "waterfall",
          barCategoryGap: "30%",
          data: bars.map((b) => ({
            value: b.bar,
            itemStyle: { color: b.color },
          })),
          label: {
            show: true,
            position: "top",
            fontSize: 10,
            // Rotulos de dados usam 1 casa decimal (fmtBRLCompact1) — menos
            // ruido visual. Axis e tooltip continuam com mais precisao.
            formatter: (params: { dataIndex: number }) => {
              const bar = bars[params.dataIndex]
              if (!bar) return ""
              if (bar.kind === "anchor") {
                return fmtBRLCompact1.format(bar.realValue)
              }
              const sinal = bar.realValue >= 0 ? "+" : "−"
              return `${sinal}${fmtBRLCompact1.format(Math.abs(bar.realValue))}`
            },
          },
          cursor: "pointer",
        },
      ],
    }),
    [bars],
  )

  const handleEvents = React.useMemo(
    () => ({
      click: (params: { dataIndex: number; componentType: string }) => {
        if (params.componentType !== "series") return
        const bar = bars[params.dataIndex]
        if (!bar || bar.kind === "anchor") return
        if (bar.driver && onDriverClick) {
          onDriverClick(bar.driver)
        }
      },
    }),
    [bars, onDriverClick],
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
