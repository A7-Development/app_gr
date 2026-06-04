// L3 do redesign /bi/operacoes4 (handoff 2026-05-21).
//
// 4 cards 25% — todos com altura de chart 215px:
//   1. Distribuicao de taxas · MTD            (histograma 5 buckets, pill DRILL)
//   2. Distribuicao de taxas · por produto    (bar vertical, ordenado desc)
//   3. Prazo · distribuicao                   (histograma 6 buckets, cauda >90 orange)
//   4. Composicao receita · MTD               (tabela 4 linhas Origem/Valor/Share)
//
// Cards 1, 2, 3 usam MOCKS (PR1) — backend ainda nao expoe. Ver _mocks.ts.
// Card 4 consome `Operacoes4LensReceitasData.composicao` real do bundle.

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import type { EChartsOption } from "echarts"
import { RiArrowRightUpLine } from "@remixicon/react"

import { Card } from "@/components/tremor/Card"
import { cardTokens } from "@/design-system/tokens/card"
import { EChartsCard } from "@/design-system/components/EChartsCard"
import { biOperacoes4 } from "@/lib/api-client"
import type {
  BIFilters,
  Operacoes4ReceitaTipo,
} from "@/lib/api-client"
import { cx } from "@/lib/utils"

import {
  MOCK_HIST_PRAZO,
  MOCK_PRAZO_DELTA_DIAS,
  MOCK_PRAZO_MEDIO_MTD,
  MOCK_TAXA_MEDIA_POR_PRODUTO,
  MOCK_WAVG_TAXAS_MTD,
  type HistogramBucket,
} from "./_mocks"

// ─── Constantes visuais ─────────────────────────────────────────────────────

const COLOR_NAVY = "#1B2B4B"
const COLOR_RED = "#ef4444"
const COLOR_ORANGE = "#F05A28"
const COLOR_BLUE_HOVER = "#3B82F6"

const CHART_HEIGHT = 215

const fmtBRLFull = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
})
const fmtBRLCompact = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 1,
})

function fmtPct(v: number, casas = 2): string {
  return `${v.toFixed(casas).replace(".", ",")}%`
}

// ─── Card 1: Distribuição de taxas · MTD (histograma + drill stub) ─────────

function HistTaxasCard({
  filters,
  onBucketClick,
}: {
  filters: BIFilters
  onBucketClick?: (bucketIdx: number) => void
}) {
  // Dados reais do mes (substitui MOCK_HIST_TAXAS_MTD): histograma ponderado
  // por VOP MTD + wavg (identica ao termometro) + mediana ponderada por VOP.
  const q = useQuery({
    queryKey: ["bi", "operacoes4", "lens-taxas", filters],
    queryFn: () => biOperacoes4.lensTaxas(filters),
  })
  const data = q.data?.data

  const buckets = React.useMemo<HistogramBucket[]>(
    () =>
      (data?.histograma ?? []).map((b) => ({
        label: b.label,
        vop_mtd: typeof b.vop_mtd === "string" ? Number(b.vop_mtd) : b.vop_mtd,
        is_tail: b.is_tail,
      })),
    [data],
  )
  const option = React.useMemo<EChartsOption>(
    () => buildHistOption(buckets, COLOR_NAVY, COLOR_RED, COLOR_BLUE_HOVER),
    [buckets],
  )

  const echartsProps = React.useMemo(() => {
    if (!onBucketClick) return undefined
    return {
      onEvents: {
        click: (params: { dataIndex?: number; seriesType?: string }) => {
          if (params.seriesType !== "bar") return
          if (params.dataIndex == null) return
          onBucketClick(params.dataIndex)
        },
      },
    }
  }, [onBucketClick])

  return (
    <div className={onBucketClick ? "cursor-pointer" : undefined}>
      <EChartsCard
        title="Distribuição de taxas · MTD"
        caption="5 faixas · ponderado por VOP MTD"
        headerKpi={{
          value: data ? fmtPct(data.wavg_pct) : "—",
          delta:
            data?.delta_pct != null
              ? { value: data.delta_pct, suffix: "%", fractionDigits: 1 }
              : undefined,
          deltaSub: "ponderada",
        }}
        actions={<DrillPill />}
        option={option}
        height={CHART_HEIGHT}
        echartsProps={echartsProps}
      />
    </div>
  )
}

function DrillPill() {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-1.5 py-0.5 text-[9.5px] font-medium uppercase tracking-wider text-blue-700 ring-1 ring-inset ring-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:ring-blue-500/30"
      title="Clique numa barra para ver cedentes da faixa"
    >
      <RiArrowRightUpLine className="size-3" aria-hidden />
      drill
    </span>
  )
}

// ─── Card 2: Taxa média por produto (bar vertical) ──────────────────────────

function TaxasPorProdutoCard() {
  // MOCK_PR3: ordena por taxa desc.
  const sorted = React.useMemo(
    () =>
      Object.entries(MOCK_TAXA_MEDIA_POR_PRODUTO).sort(
        ([, a], [, b]) => b - a,
      ),
    [],
  )
  const labels = sorted.map(([k]) => k)
  const values = sorted.map(([, v]) => v)

  const option = React.useMemo<EChartsOption>(
    () => ({
      grid: { left: 36, right: 12, top: 16, bottom: 28 },
      xAxis: {
        type: "category",
        data: labels,
        axisLine: { lineStyle: { color: "#e5e7eb" } },
        axisTick: { show: false },
        axisLabel: { color: "#6B7280", fontSize: 10 },
      },
      yAxis: {
        type: "value",
        min: 2.4,
        max: 3.2,
        splitNumber: 4,
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: "#f3f4f6", type: "dashed" } },
        axisLabel: {
          color: "#9CA3AF",
          fontSize: 9,
          formatter: (v: number) => fmtPct(v, 1),
        },
      },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        formatter: (ps: { name: string; value: number }[] | unknown) => {
          const p = Array.isArray(ps) ? ps[0] : null
          if (!p) return ""
          return `${p.name}<br/><b>${fmtPct(p.value)}</b>`
        },
      },
      series: [
        {
          type: "bar",
          data: values,
          barWidth: "60%",
          itemStyle: { color: COLOR_NAVY, borderRadius: [2, 2, 0, 0] },
          label: {
            show: true,
            position: "top",
            formatter: (params) => {
              const v = (params as { value: number | string }).value
              return fmtPct(typeof v === "number" ? v : Number(v))
            },
            fontSize: 10.5,
            fontWeight: 600,
            color: "#374151",
          },
        },
      ],
    }),
    [labels, values],
  )

  return (
    <EChartsCard
      title="Distribuição de taxas · por produto"
      caption="Taxa média ponderada por produto"
      headerKpi={{
        value: fmtPct(MOCK_WAVG_TAXAS_MTD),
        deltaSub: "wavg geral",
      }}
      option={option}
      height={CHART_HEIGHT}
    />
  )
}

// ─── Card 3: Prazo · distribuição (histograma 6 buckets) ────────────────────

function PrazoHistCard() {
  const option = React.useMemo<EChartsOption>(
    () =>
      buildHistOption(
        MOCK_HIST_PRAZO,
        COLOR_NAVY,
        COLOR_ORANGE,
        COLOR_BLUE_HOVER,
      ),
    [],
  )

  return (
    <EChartsCard
      title="Prazo · distribuição"
      caption="Buckets de 15d. Cauda >90d destacada."
      headerKpi={{
        value: `${MOCK_PRAZO_MEDIO_MTD.toFixed(1).replace(".", ",")} d`,
        delta: { value: MOCK_PRAZO_DELTA_DIAS, suffix: " d", good: false },
        deltaSub: "média",
      }}
      option={option}
      height={CHART_HEIGHT}
    />
  )
}

// ─── Card 4: Composição receita · MTD (tabela) ─────────────────────────────

const COMPOSICAO_LABEL: Record<Operacoes4ReceitaTipo, string> = {
  desagio: "Cessão",
  tarifa_cessao: "Tarifas",
  tarifas_operacionais: "Juros",
  outras: "Outros",
}
const COMPOSICAO_COR: Record<Operacoes4ReceitaTipo, string> = {
  desagio: "#1B2B4B",
  tarifa_cessao: "#4b5d80",
  tarifas_operacionais: "#7d8aa4",
  outras: "#10b981",
}

function ComposicaoReceitaCard({ filters }: { filters: BIFilters }) {
  const q = useQuery({
    queryKey: ["bi", "operacoes4", "lens-receitas", filters],
    queryFn: () => biOperacoes4.lensReceitas(filters),
  })
  const data = q.data?.data

  return (
    <Card className={cx(cardTokens.body, "flex flex-col")}>
      <header className="pb-3">
        <div className="text-[10.5px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
          Composição receita · MTD
        </div>
        <p className="mt-1 flex flex-wrap items-baseline gap-x-2 tabular-nums">
          <span className="text-[20px] font-semibold leading-none tracking-tight text-gray-900 dark:text-gray-50">
            {data
              ? fmtBRLCompact.format(
                  typeof data.total_mtd === "string"
                    ? Number(data.total_mtd)
                    : data.total_mtd,
                )
              : "—"}
          </span>
          {data?.delta_pct != null && (
            <span
              className={cx(
                "text-xs font-medium",
                data.delta_pct >= 0
                  ? "text-emerald-600 dark:text-emerald-400"
                  : "text-red-600 dark:text-red-400",
              )}
            >
              {data.delta_pct >= 0 ? "+" : "−"}
              {Math.abs(data.delta_pct).toFixed(1).replace(".", ",")}%
            </span>
          )}
        </p>
        <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
          vs mesmo DU mês ant. · regime caixa
        </p>
      </header>

      <div
        style={{ height: CHART_HEIGHT }}
        className="flex flex-col justify-center gap-1.5 overflow-y-auto"
      >
        {data?.composicao.map((item) => {
          const valor =
            typeof item.valor === "string" ? Number(item.valor) : item.valor
          return (
            <div
              key={item.tipo}
              className="flex items-center justify-between gap-3 border-b border-gray-50 py-1 last:border-b-0 dark:border-gray-900/60"
            >
              <div className="flex items-center gap-2 min-w-0">
                <span
                  className="inline-block size-2 shrink-0 rounded-sm"
                  style={{ backgroundColor: COMPOSICAO_COR[item.tipo] }}
                  aria-hidden
                />
                <span className="truncate text-[12px] text-gray-900 dark:text-gray-100">
                  {COMPOSICAO_LABEL[item.tipo]}
                </span>
              </div>
              <div className="flex items-baseline gap-3 tabular-nums">
                <span className="text-[12px] text-gray-900 dark:text-gray-100">
                  {fmtBRLFull.format(valor)}
                </span>
                <span className="w-[44px] text-right text-[11px] text-gray-500 dark:text-gray-400">
                  {item.share_pct.toFixed(1).replace(".", ",")}%
                </span>
              </div>
            </div>
          )
        })}
        {!data && q.isLoading && (
          <p className="text-center text-[11px] italic text-gray-400">
            Carregando…
          </p>
        )}
        {!data && !q.isLoading && (
          <p className="text-center text-[11px] italic text-gray-400">
            Sem dados disponíveis.
          </p>
        )}
      </div>
    </Card>
  )
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function buildHistOption(
  buckets: HistogramBucket[],
  baseColor: string,
  tailColor: string,
  hoverColor: string,
): EChartsOption {
  return {
    grid: { left: 36, right: 12, top: 16, bottom: 28 },
    xAxis: {
      type: "category",
      data: buckets.map((b) => b.label),
      axisLine: { lineStyle: { color: "#e5e7eb" } },
      axisTick: { show: false },
      axisLabel: { color: "#6B7280", fontSize: 10 },
    },
    yAxis: {
      type: "value",
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: "#f3f4f6", type: "dashed" } },
      axisLabel: {
        color: "#9CA3AF",
        fontSize: 9,
        formatter: (v: number) => {
          if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(0)}M`
          if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K`
          return String(v)
        },
      },
    },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (ps: { name: string; value: number }[] | unknown) => {
        const p = Array.isArray(ps) ? ps[0] : null
        if (!p) return ""
        return `${p.name}<br/><b>${fmtBRLCompact.format(p.value)}</b>`
      },
    },
    series: [
      {
        type: "bar",
        data: buckets.map((b) => ({
          value: b.vop_mtd,
          itemStyle: {
            color: b.is_tail && b.vop_mtd > 0 ? tailColor : baseColor,
            borderRadius: [2, 2, 0, 0],
          },
          emphasis: { itemStyle: { color: hoverColor } },
        })),
        barWidth: "60%",
      },
    ],
  }
}

// ─── Public composite ──────────────────────────────────────────────────────

export function L3CardsRow({
  filters,
  onBucketTaxasClick,
}: {
  filters: BIFilters
  onBucketTaxasClick?: (bucketIdx: number) => void
}) {
  return (
    <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <HistTaxasCard filters={filters} onBucketClick={onBucketTaxasClick} />
      <TaxasPorProdutoCard />
      <PrazoHistCard />
      <ComposicaoReceitaCard filters={filters} />
    </section>
  )
}
