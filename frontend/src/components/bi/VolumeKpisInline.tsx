"use client"

import * as React from "react"
import { RiArrowDownSLine, RiArrowUpSLine, RiSubtractLine } from "@remixicon/react"

import { DonutChart } from "@/components/charts/DonutChart"
import { SparkAreaChart } from "@/components/charts/SparkChart"
import { cx } from "@/lib/utils"
import type {
  CategoryValueDelta,
  Point,
  VolumeResumoDeltas,
} from "@/lib/api-client"

//
// Formatters pt-BR
//

const moedaCompacta = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 1,
})

const numero = new Intl.NumberFormat("pt-BR")

const pct1 = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`
const pp1 = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(1)} pp`

//
// DeltaBadge — pequeno e discreto
//

function DeltaBadge({
  value,
  format = pct1,
}: {
  value: number | null
  format?: (v: number) => string
}) {
  if (value === null || Number.isNaN(value)) {
    return (
      <span className="inline-flex items-center gap-0.5 text-[11px] font-medium text-gray-400 tabular-nums">
        <RiSubtractLine aria-hidden="true" className="size-3" />—
      </span>
    )
  }
  const isPositive = value > 0
  const isNegative = value < 0
  return (
    <span
      className={cx(
        "inline-flex items-center gap-0.5 text-[11px] font-medium tabular-nums",
        isPositive && "text-emerald-600 dark:text-emerald-500",
        isNegative && "text-rose-600 dark:text-rose-500",
        !isPositive && !isNegative && "text-gray-500",
      )}
    >
      {isPositive && <RiArrowUpSLine aria-hidden="true" className="size-3" />}
      {isNegative && <RiArrowDownSLine aria-hidden="true" className="size-3" />}
      {format(value)}
    </span>
  )
}

//
// Item com sparkline (padrao dos KPIs de texto)
//

// Cor do spark deriva SEMANTICAMENTE do delta principal do KPI — nao iteracao
// arbitraria de paleta. §4 do CLAUDE.md: delta > 0 "emerald" / < 0 "rose" /
// zero|null "slate". Mesmo padrao ja usado no DeltaBadge.
function colorFromDelta(
  delta: number | null,
): "emerald" | "rose" | "slate" {
  if (delta === null || Number.isNaN(delta) || delta === 0) return "slate"
  return delta > 0 ? "emerald" : "rose"
}

function KpiTextItem({
  label,
  value,
  deltas,
  spark,
  deltaValue,
}: {
  label: string
  value: React.ReactNode
  deltas: React.ReactNode
  spark: Point[]
  deltaValue: number | null
}) {
  const sparkData = React.useMemo(
    () =>
      spark.map((p) => ({
        periodo: typeof p.periodo === "string" ? p.periodo : String(p.periodo),
        valor: p.valor,
      })),
    [spark],
  )

  const sparkColor = colorFromDelta(deltaValue)

  return (
    <div className="flex items-center gap-3">
      <div className="flex flex-col gap-0.5">
        <span className="text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
          {label}
        </span>
        <div className="flex items-baseline gap-2">
          <span className="text-base font-semibold tabular-nums text-gray-900 dark:text-gray-50">
            {value}
          </span>
          {deltas}
        </div>
      </div>
      {sparkData.length > 1 && (
        <SparkAreaChart
          data={sparkData}
          index="periodo"
          categories={["valor"]}
          colors={[sparkColor]}
          className="h-8 w-20 shrink-0"
        />
      )}
    </div>
  )
}

//
// Item com mini donut (KPI "Volume / UA")
//
// Substitui o sparkline por um DonutChart compacto clicavel. Hover exibe
// tooltip com nome + valor da UA. Click numa fatia aplica filtro global
// daquela UA.
//

type UaDonutDatum = { name: string; uaId: string; amount: number }

function KpiUaDonut({
  label,
  data,
  valueTotal,
  onUaClick,
}: {
  label: string
  data: UaDonutDatum[]
  valueTotal: number
  onUaClick?: (uaId: string) => void
}) {
  // Encontra UA lider (maior) para display textual
  const lider = React.useMemo(() => {
    if (data.length === 0) return null
    const top = [...data].sort((a, b) => b.amount - a.amount)[0]
    const pct = valueTotal > 0 ? (top.amount / valueTotal) * 100 : 0
    return { nome: top.name, pct }
  }, [data, valueTotal])

  return (
    <div className="flex items-center gap-3">
      <div className="flex flex-col gap-0.5">
        <span className="text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
          {label}
        </span>
        {lider ? (
          <div className="flex items-baseline gap-2">
            <span className="truncate text-sm font-semibold text-gray-900 dark:text-gray-50">
              {lider.nome}
            </span>
            <span className="text-xs font-medium tabular-nums text-gray-500">
              {lider.pct.toFixed(1)}%
            </span>
          </div>
        ) : (
          <span className="text-xs text-gray-400">—</span>
        )}
        <span className="text-[10px] text-gray-400">
          {data.length} {data.length === 1 ? "UA ativa" : "UAs ativas"}
        </span>
      </div>
      {data.length > 0 && (
        <DonutChart
          data={data}
          category="name"
          value="amount"
          colors={["slate", "sky", "teal", "emerald", "amber", "rose"]}
          valueFormatter={(v) => moedaCompacta.format(v)}
          className="size-14 shrink-0"
          showTooltip
          onValueChange={(e) => {
            if (!e) {
              onUaClick?.("")
              return
            }
            // `categoryClicked` vem com o name; precisamos do uaId para filtrar.
            const clicked = data.find((d) => d.name === e.categoryClicked)
            if (clicked && onUaClick) onUaClick(clicked.uaId)
          }}
        />
      )}
    </div>
  )
}

//
// VolumeKpisInline
//

type Props = {
  resumo: VolumeResumoDeltas | undefined
  /** Decomposicao por UA — alimenta o mini donut "Volume / UA". */
  porUa: CategoryValueDelta[] | undefined
  /** Volume total (usado no donut para calcular fatia % do lider). */
  volumeTotal: number | undefined
  loading?: boolean
  onUaClick?: (uaId: string) => void
  className?: string
}

export function VolumeKpisInline({
  resumo,
  porUa,
  volumeTotal,
  loading,
  onUaClick,
  className,
}: Props) {
  if (loading || !resumo) {
    return (
      <div
        className={cx(
          "flex flex-wrap items-center gap-x-8 gap-y-3 border-b border-gray-200 pb-3 dark:border-gray-800",
          className,
        )}
      >
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <div
            key={i}
            className="h-10 w-36 animate-pulse rounded bg-gray-100 dark:bg-gray-900"
          />
        ))}
      </div>
    )
  }

  const uaDonutData: UaDonutDatum[] = (porUa ?? []).map((u) => ({
    name: u.categoria,
    uaId: u.categoria_id ?? "",
    amount: u.valor,
  }))

  return (
    <div
      className={cx(
        "flex flex-wrap items-center gap-x-8 gap-y-3 border-b border-gray-200 pb-3 dark:border-gray-800",
        className,
      )}
    >
      <KpiTextItem
        label="Volume"
        value={moedaCompacta.format(resumo.volume_total)}
        deltas={
          <>
            <DeltaBadge value={resumo.volume_mom_pct} />
            <span className="text-[10px] text-gray-400">MoM</span>
            {resumo.volume_yoy_pct !== null && (
              <>
                <DeltaBadge value={resumo.volume_yoy_pct} />
                <span className="text-[10px] text-gray-400">YoY</span>
              </>
            )}
          </>
        }
        spark={resumo.volume_sparkline_12m}
        deltaValue={resumo.volume_mom_pct}
      />

      <KpiTextItem
        label="Ticket médio / Op."
        value={moedaCompacta.format(resumo.ticket_medio)}
        deltas={
          <>
            <DeltaBadge value={resumo.ticket_mom_pct} />
            <span className="text-[10px] text-gray-400">MoM</span>
          </>
        }
        spark={resumo.ticket_sparkline_12m}
        deltaValue={resumo.ticket_mom_pct}
      />

      <KpiTextItem
        label="Ticket médio / Tít."
        value={moedaCompacta.format(resumo.ticket_medio_titulo)}
        deltas={
          <>
            <DeltaBadge value={resumo.ticket_medio_titulo_mom_pct} />
            <span className="text-[10px] text-gray-400">MoM</span>
          </>
        }
        spark={resumo.ticket_medio_titulo_sparkline_12m}
        deltaValue={resumo.ticket_medio_titulo_mom_pct}
      />

      <KpiTextItem
        label="Nº operações"
        value={numero.format(resumo.n_operacoes)}
        deltas={
          <>
            <DeltaBadge value={resumo.n_operacoes_mom_pct} />
            <span className="text-[10px] text-gray-400">MoM</span>
          </>
        }
        spark={resumo.n_operacoes_sparkline_12m}
        deltaValue={resumo.n_operacoes_mom_pct}
      />

      <KpiTextItem
        label="Produto líder"
        value={
          <span className="flex items-baseline gap-1.5">
            <span className="text-sm font-semibold">
              {resumo.produto_lider_sigla}
            </span>
            <span>{resumo.produto_lider_pct.toFixed(1)}%</span>
          </span>
        }
        deltas={
          <>
            <DeltaBadge value={resumo.produto_lider_delta_pp} format={pp1} />
            <span className="text-[10px] text-gray-400">vs anterior</span>
          </>
        }
        spark={resumo.produto_lider_sparkline_12m}
        deltaValue={resumo.produto_lider_delta_pp}
      />

      <KpiUaDonut
        label="Volume / UA"
        data={uaDonutData}
        valueTotal={volumeTotal ?? resumo.volume_total}
        onUaClick={onUaClick}
      />
    </div>
  )
}
