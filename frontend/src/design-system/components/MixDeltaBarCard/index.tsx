// src/design-system/components/MixDeltaBarCard/index.tsx
//
// Diverging bar para variacao de share (Mix de produtos): bars verticais
// centradas em zero. Cada produto tem 1 bar com altura = delta_share_pp.
// Positivos (ganhou share) sobem em verde, negativos (perdeu) descem em rosa.
//
// Substitui o DumbbellCard no AbaMesCorrente desde 2026-05-09 — escolha por
// consistencia visual com os waterfalls dos outros 4 cards de decomposicao
// (VOP, Receita, Taxa, Prazo). Dumbbell continua disponivel como componente
// generico ("antes vs depois em duas escalas comparaveis"); este e a versao
// "delta vertical" especializada pra Mix.
//
// Por que NAO e waterfall propriamente: Mix e zero-sum (shares somam 100%),
// nao tem anchors numericos validos. O diverging bar preserva a intuicao
// visual do waterfall (bars verticais, verde/rosa) sem violar a aditividade.

"use client"

import * as React from "react"
import type { EChartsOption } from "echarts"

import {
  EChartsCard,
  type EChartsCardHeaderKpi,
} from "@/design-system/components/EChartsCard"
import type { Operacoes2DumbbellSeriesData } from "@/lib/api-client"

// Hex literais espelham a paleta dos waterfalls (VarianceBridgeCard /
// PvmBridgeCard). Tailwind nao alcanca o canvas ECharts — excecao §4.
const COLOR_POSITIVE = "#10B981" // emerald-500
const COLOR_NEGATIVE = "#F43F5E" // rose-500

const fmtPct1 = (v: number) => `${v.toFixed(1).replace(".", ",")}%`
const fmtPctSigned = (v: number) =>
  `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(1).replace(".", ",")}pp`

/**
 * Heuristica espelhada de `VarianceBridgeCard.shortAxisLabel` para manter
 * o eixo X consistente entre os waterfalls e este card: usa `member_id`
 * (sigla) quando parece codigo curto alfanumerico iniciando por letra
 * (ex.: "FAT", "DMS"). Caso contrario, fallback para `member_label`.
 *
 * Por que duplicado: VarianceBridgeCard tem a mesma logica inline. Se
 * surgir um 3o consumidor, vale extrair pra `lib/chartUtils.ts`.
 */
function shortAxisLabel(memberId: string, memberLabel: string): string {
  const isShortCode =
    memberId.length <= 8 &&
    memberId !== memberLabel &&
    memberId === memberId.toUpperCase() &&
    /^[A-Z][A-Z0-9]*$/.test(memberId)
  return isShortCode ? memberId : memberLabel
}

export interface MixDeltaBarCardProps {
  data: Operacoes2DumbbellSeriesData
  title: string
  /**
   * Caption do card. Default: "prior_anchor_label → current_anchor_label"
   * (ex.: "abr/26 → mai/26"). Diferente dos waterfalls, este card NAO tem
   * anchors no eixo X — entao o periodo precisa viver no caption.
   */
  caption?: string
  /** KPI editorial no header (opt-in). */
  headerKpi?: EChartsCardHeaderKpi
  height?: number
  footer?: React.ReactNode
  actions?: React.ReactNode
  className?: string
}

export function MixDeltaBarCard({
  data,
  title,
  caption,
  headerKpi,
  height = 280,
  footer,
  actions,
  className,
}: MixDeltaBarCardProps) {
  // Pontos vem ordenados por |delta_share_pp| desc do backend.
  // Mantem essa ordem (maior |delta| a esquerda).
  const points = data.points

  const autoCaption =
    caption ?? `${data.prior_anchor_label} → ${data.current_anchor_label}`

  const option: EChartsOption = React.useMemo(() => {
    return {
      grid: { top: 24, right: 16, bottom: 28, left: 56 },
      legend: { show: false },
      xAxis: {
        type: "category",
        // Sigla curta no eixo (FAT, DMS, INT...) — alinha com VarianceBridge
        // e PvmBridge. Tooltip mostra o nome completo.
        data: points.map((p) => shortAxisLabel(p.member_id, p.member_label)),
        axisTick: { show: false },
        axisLabel: {
          fontSize: 11,
          interval: 0,
          rotate: points.length > 6 ? 25 : 0,
          hideOverlap: true,
        },
      },
      yAxis: {
        type: "value",
        axisLabel: {
          formatter: (v: number) => fmtPctSigned(v),
          fontSize: 10,
        },
        splitLine: {
          show: true,
          lineStyle: { type: "dashed", opacity: 0.5 },
        },
      },
      tooltip: {
        trigger: "item",
        formatter: (params: unknown) => {
          const p = params as { dataIndex: number }
          const point = points[p.dataIndex]
          if (!point) return ""
          return [
            `<b>${point.member_label}</b>`,
            `Anterior: ${fmtPct1(point.prior_share_pct)}`,
            `Atual: ${fmtPct1(point.current_share_pct)}`,
            `Δ ${fmtPctSigned(point.delta_share_pp)}`,
          ].join("<br/>")
        },
      },
      series: [
        {
          type: "bar",
          barCategoryGap: "30%",
          barMaxWidth: 32,
          data: points.map((p) => ({
            value: p.delta_share_pp,
            itemStyle: {
              color: p.delta_share_pp >= 0 ? COLOR_POSITIVE : COLOR_NEGATIVE,
              // Cantos arredondados no topo da barra (positiva sobe, negativa desce).
              borderRadius:
                p.delta_share_pp >= 0
                  ? ([3, 3, 0, 0] as [number, number, number, number])
                  : ([0, 0, 3, 3] as [number, number, number, number]),
            },
            label: {
              show: true,
              // position: "top" para positivas (acima do bar), "bottom" para
              // negativas (abaixo do bar — fora do range, na area negativa do
              // eixo Y). Resultado: label sempre fora da barra, longe do zero.
              position: p.delta_share_pp >= 0 ? "top" : "bottom",
              fontSize: 10,
              formatter: () => fmtPctSigned(p.delta_share_pp),
            },
          })),
        },
      ],
    }
  }, [points])

  if (points.length === 0) {
    return (
      <EChartsCard
        option={{}}
        title={title}
        caption={autoCaption}
        headerKpi={headerKpi}
        height={height}
        actions={actions}
        footer={footer}
        className={className}
        // Empty state via error message — EChartsCard ja renderiza area
        // de placeholder quando error e setado, sem instanciar ECharts.
        error="Sem movimentos relevantes de share entre os períodos."
      />
    )
  }

  return (
    <EChartsCard
      option={option}
      title={title}
      caption={autoCaption}
      headerKpi={headerKpi}
      height={height}
      actions={actions}
      footer={footer}
      className={className}
    />
  )
}
