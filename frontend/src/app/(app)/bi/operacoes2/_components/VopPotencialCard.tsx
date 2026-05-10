// src/app/(app)/bi/operacoes2/_components/VopPotencialCard.tsx
//
// Card "VOP Potencial" — quanto o fundo "ainda pode" gerar de VOP ate o fim
// do mes corrente, decomposto em 3 componentes:
//
//   vop_potencial = vop_realizado_mtd + caixa_disponivel + liquidacoes_previstas
//
// - vop_realizado_mtd: VOP efetivado entre dia 1 do mes e hoje (passado).
// - caixa_disponivel: saldo livre nas contas das UAs (presente).
// - liquidacoes_previstas: titulos com vencimento ate o fim do mes (futuro).
//
// Visual: stacked horizontal bar, uma barra por UA. Header carrega total
// consolidado das UAs incluidas (default = FIDC + Securitizadora).
//
// Cores (chartColors.AvailableChartColors[0..2]):
//   slate  -> realizado (passado / neutral base)
//   sky    -> caixa     (presente / liquidez existente)
//   teal   -> a liquidar (futuro / entradas previstas)
//
// Filtros aplicados:
// - `ua_id`: aplica a TUDO. Quando vazio, default e UAs `tipo IN (1, 2)`.
// - `produto_sigla`: aplica APENAS a `vop_realizado_mtd` (caixa e titulos
//   nao tem dimensao produto canonica).
// - Periodo: IGNORADO (VOP Potencial e sempre sobre o mes corrente).

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import type { EChartsOption } from "echarts"

import { Card } from "@/components/tremor/Card"
import { EChartsCard } from "@/design-system/components/EChartsCard"
import { biOperacoes2 } from "@/lib/api-client"
import type { Operacoes2VopPotencialPorUa } from "@/lib/api-client"
import { useBiFilters } from "@/lib/hooks/useBiFilters"
import { cardTokens } from "@/design-system/tokens/card"
import { cx } from "@/lib/utils"

// Hex literais sao OK em EChartsOption (CLAUDE.md §4 excecao explicita).
// Mantemos nos 500-shades da paleta canonica de chart series (chartUtils.ts).
const COLOR_REALIZADO = "#64748B" // slate-500
const COLOR_CAIXA = "#0EA5E9" // sky-500
const COLOR_LIQUIDACOES = "#14B8A6" // teal-500

const fmtBRL = new Intl.NumberFormat("pt-BR", {
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

const fmtMonthYearPt = (iso: string): string => {
  const [year, month] = iso.split("-")
  const meses = [
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez",
  ]
  return `${meses[Number(month) - 1]}/${year.slice(2)}`
}

export function VopPotencialCard() {
  const { filtersWithFocus } = useBiFilters()

  const q = useQuery({
    queryKey: ["bi", "operacoes2", "vop-potencial", filtersWithFocus],
    queryFn: () => biOperacoes2.vopPotencial(filtersWithFocus),
  })

  const data = q.data?.data

  if (q.isLoading) {
    return <Card className={cx(cardTokens.body, "h-64 animate-pulse")} />
  }
  if (q.isError || !data) {
    return (
      <Card className={cx(cardTokens.body, "py-8 text-center")}>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Não foi possível carregar VOP Potencial.
        </p>
      </Card>
    )
  }

  // Empty state: sync de caixa ainda nao rodou ou tenant sem dados.
  if (data.por_ua.length === 0) {
    return (
      <Card className={cx(cardTokens.body, "py-10 text-center")}>
        <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
          VOP Potencial
        </p>
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          Aguardando próxima sincronização Bitfin para popular caixa do mês.
        </p>
      </Card>
    )
  }

  // ECharts option — stacked horizontal bar.
  const uaNomes = data.por_ua.map((u) => u.ua_nome)
  const realizado = data.por_ua.map((u) => u.vop_realizado_mtd)
  const caixa = data.por_ua.map((u) => u.caixa_disponivel)
  const liquidacoes = data.por_ua.map((u) => u.liquidacoes_previstas)

  const option: EChartsOption = {
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      valueFormatter: (v) => fmtBRLFull.format(Number(v ?? 0)),
    },
    legend: {
      data: ["Realizado MTD", "Caixa disponível", "A liquidar"],
      bottom: 0,
      itemWidth: 10,
      itemHeight: 10,
      icon: "circle",
      textStyle: { fontSize: 11 },
    },
    grid: { left: 8, right: 16, top: 8, bottom: 36, containLabel: true },
    xAxis: {
      type: "value",
      axisLabel: {
        formatter: (v: number) => fmtBRL.format(Number(v ?? 0)),
        fontSize: 10,
      },
      splitLine: { lineStyle: { type: "dashed" } },
    },
    yAxis: {
      type: "category",
      data: uaNomes,
      axisLabel: { fontSize: 11 },
      axisTick: { show: false },
    },
    series: [
      {
        name: "Realizado MTD",
        type: "bar",
        stack: "total",
        emphasis: { focus: "series" },
        itemStyle: { color: COLOR_REALIZADO },
        data: realizado,
      },
      {
        name: "Caixa disponível",
        type: "bar",
        stack: "total",
        emphasis: { focus: "series" },
        itemStyle: { color: COLOR_CAIXA },
        data: caixa,
      },
      {
        name: "A liquidar",
        type: "bar",
        stack: "total",
        emphasis: { focus: "series" },
        itemStyle: { color: COLOR_LIQUIDACOES },
        // Label so na ultima serie (final da barra empilhada) — mostra total.
        label: {
          show: true,
          position: "right",
          formatter: (params) => {
            const idx = params.dataIndex as number
            const total = data.por_ua[idx]?.vop_potencial ?? 0
            return fmtBRL.format(total)
          },
          fontSize: 11,
          fontWeight: 600,
          color: "#374151", // gray-700
        },
        data: liquidacoes,
      },
    ],
  }

  // Altura proporcional a numero de UAs (45px/barra + 80px de chrome).
  const chartHeight = Math.max(160, data.por_ua.length * 45 + 80)

  return (
    <EChartsCard
      title="VOP POTENCIAL"
      caption={`Realizado ${fmtMonthYearPt(data.mes_inicio)} (até ${data.hoje.split("-").reverse().join("/")}) + caixa + a liquidar até fim do mês`}
      headerKpi={{
        value: fmtBRL.format(data.vop_potencial),
        deltaSub: data.por_ua.length === 1 ? "1 UA" : `${data.por_ua.length} UAs`,
      }}
      option={option}
      height={chartHeight}
    />
  )
}
