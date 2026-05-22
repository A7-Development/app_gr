// src/app/(app)/bi/operacoes3/_components/DrillOperacoesDoDia.tsx
//
// Conteudo do DrillDownSheet ao clicar numa barra do VOP DIARIO.
//
// Estrutura:
//   1. Mini-resumo (KPIs do dia): VOP, nº ops, ticket medio, taxa, prazo
//   2. Mini chart de quebra por produto/UA (pizza/barra horizontal)
//   3. Tabela canonica de operacoes do dia

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import type { ColumnDef } from "@tanstack/react-table"
import type { EChartsOption } from "echarts"

import { Card } from "@/components/tremor/Card"
import { DataTable, CurrencyCell } from "@/design-system/components"
import { EChartsCard } from "@/design-system/components/EChartsCard"
import { biOperacoes2 } from "@/lib/api-client"
import type {
  Operacoes2OperacaoDoDiaItem,
  Operacoes2OperacoesDoDiaData,
} from "@/lib/api-client"
import { useBiFilters } from "@/lib/hooks/useBiFilters"
import { cardTokens } from "@/design-system/tokens/card"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 2,
})

const fmtBRLFull = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
})

const fmtInt = new Intl.NumberFormat("pt-BR")
const fmtPct1 = (v: number) => `${v.toFixed(1).replace(".", ",")}%`
const fmtDias1 = (v: number) => `${v.toFixed(1).replace(".", ",")} d`

// Paleta canonica de chart series (hex inline — excecao §4 EChartsOption).
const PIE_COLORS = [
  "#64748B", // slate-500
  "#0EA5E9", // sky-500
  "#14B8A6", // teal-500
  "#10B981", // emerald-500
  "#F59E0B", // amber-500
  "#F43F5E", // rose-500
  "#8B5CF6", // violet-500
  "#6366F1", // indigo-500
]

export function DrillOperacoesDoDia({ dataISO }: { dataISO: string }) {
  const { filtersWithFocus } = useBiFilters()
  const q = useQuery({
    queryKey: ["bi", "operacoes2", "operacoes-do-dia", dataISO, filtersWithFocus],
    queryFn: () => biOperacoes2.operacoesDoDia(filtersWithFocus, dataISO),
  })

  const bundle = q.data?.data

  if (q.isLoading) {
    return (
      <div className="flex flex-col gap-3 p-6">
        <Card className={cx(cardTokens.body, "h-24 animate-pulse")} />
        <Card className={cx(cardTokens.body, "h-48 animate-pulse")} />
        <Card className={cx(cardTokens.body, "h-64 animate-pulse")} />
      </div>
    )
  }
  if (q.isError || !bundle) {
    return (
      <div className="p-6 text-center">
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Não foi possível carregar as operações do dia.
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4 p-6">
      <KpisDoDia bundle={bundle} />
      <QuebraGrid
        porProduto={bundle.por_produto}
        porUa={bundle.por_ua}
        vopDia={bundle.vop_do_dia}
      />
      <TabelaOperacoes operacoes={bundle.operacoes} />
    </div>
  )
}

// ─── Mini-resumo (KPIs do dia) ─────────────────────────────────────────────

function KpisDoDia({ bundle }: { bundle: Operacoes2OperacoesDoDiaData }) {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
      <KpiInline label="VOP do dia" value={fmtBRLFull.format(bundle.vop_do_dia)} />
      <KpiInline label="Nº operações" value={fmtInt.format(bundle.n_operacoes)} />
      <KpiInline label="Ticket médio" value={fmtBRLFull.format(bundle.ticket_medio)} />
      <KpiInline
        label="Taxa média"
        value={bundle.taxa_media != null ? fmtPct1(bundle.taxa_media) : "—"}
      />
      <KpiInline
        label="Prazo médio"
        value={bundle.prazo_medio != null ? fmtDias1(bundle.prazo_medio) : "—"}
      />
    </div>
  )
}

function KpiInline({ label, value }: { label: string; value: string }) {
  return (
    <Card className={cx(cardTokens.body, "flex flex-col gap-0.5 p-3")}>
      <span className="text-[11px] uppercase tracking-wider text-gray-500 dark:text-gray-400">
        {label}
      </span>
      <span className="text-base font-semibold tabular-nums text-gray-900 dark:text-gray-50">
        {value}
      </span>
    </Card>
  )
}

// ─── Quebra por produto / UA (2 mini charts lado a lado) ──────────────────

function QuebraGrid({
  porProduto,
  porUa,
  vopDia,
}: {
  porProduto: Array<{ label: string; valor: number; share_pct: number }>
  porUa: Array<{ label: string; valor: number; share_pct: number }>
  vopDia: number
}) {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
      <QuebraChart title="Por produto" quebra={porProduto} vopDia={vopDia} />
      <QuebraChart title="Por UA" quebra={porUa} vopDia={vopDia} />
    </div>
  )
}

function QuebraChart({
  title,
  quebra,
  vopDia,
}: {
  title: string
  quebra: Array<{ label: string; valor: number; share_pct: number }>
  vopDia: number
}) {
  if (quebra.length === 0 || vopDia === 0) {
    return (
      <Card className={cx(cardTokens.body, "py-8 text-center")}>
        <p className="text-xs text-gray-500 dark:text-gray-400">{title}</p>
        <p className="mt-1 text-xs text-gray-400 dark:text-gray-600">
          Sem dados no dia.
        </p>
      </Card>
    )
  }

  // Backend ja entrega ordenado por valor desc. ECharts plota bottom-up no
  // yAxis category — invertemos para o maior aparecer no topo.
  const sorted = [...quebra].reverse()
  const labels = sorted.map((q) => q.label)
  const valores = sorted.map((q) => q.valor)
  const shares = sorted.map((q) => q.share_pct)

  // Altura proporcional ao numero de barras (22px/barra + 60px de chrome).
  const chartHeight = Math.max(140, sorted.length * 26 + 60)

  const option: EChartsOption = {
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (params: unknown) => {
        const arr = params as Array<{ name: string; value: number; dataIndex: number }>
        if (!Array.isArray(arr) || arr.length === 0) return ""
        const p = arr[0]
        const share = shares[p.dataIndex] ?? 0
        return `${p.name}<br/><strong>${fmtBRL.format(p.value)}</strong> · ${share.toFixed(1).replace(".", ",")}%`
      },
    },
    legend: { show: false },
    grid: { left: 8, right: 80, top: 8, bottom: 24, containLabel: true },
    xAxis: {
      type: "value",
      axisLabel: { formatter: (v: number) => fmtBRL.format(v), fontSize: 10 },
      splitLine: { lineStyle: { type: "dashed" } },
    },
    yAxis: {
      type: "category",
      data: labels,
      axisTick: { show: false },
      axisLabel: { fontSize: 11 },
    },
    series: [
      {
        type: "bar",
        barMaxWidth: 18,
        // Label na ponta da barra: "R$ X,X mi · YY%"
        label: {
          show: true,
          position: "right",
          formatter: (p) => {
            const idx = (p as { dataIndex: number }).dataIndex
            const v = (p as { value: number }).value
            const share = shares[idx] ?? 0
            return `${fmtBRL.format(v)} · ${share.toFixed(1).replace(".", ",")}%`
          },
          fontSize: 10,
          fontWeight: 500,
          color: "#374151", // gray-700
        },
        data: valores.map((v, i) => ({
          value: v,
          itemStyle: {
            color: PIE_COLORS[(sorted.length - 1 - i) % PIE_COLORS.length],
            borderRadius: [0, 3, 3, 0],
          },
        })),
      },
    ],
  }

  return (
    <EChartsCard
      title={title}
      caption={`${quebra.length} categorias · soma R$ ${(vopDia / 1_000_000).toFixed(2).replace(".", ",")} mi`}
      option={option}
      height={chartHeight}
    />
  )
}

// ─── Tabela canonica de operacoes do dia ──────────────────────────────────

function TabelaOperacoes({
  operacoes,
}: {
  operacoes: Operacoes2OperacaoDoDiaItem[]
}) {
  const columns = React.useMemo<ColumnDef<Operacoes2OperacaoDoDiaItem, unknown>[]>(
    () => [
      {
        // Cedente ocupa ~55% da largura disponivel; demais colunas tem
        // width fixo. DrillDownSheet `xl` = 880px - paddings ~= 830px uteis.
        // Soma: 460 + 95 + 60 + 110 + 70 + 70 = 865px (cabe sem scroll,
        // com truncate na cedente apenas em nomes muito longos).
        accessorKey: "cedente",
        header: "Cedente",
        size: 460,
        cell: ({ row }) => (
          <div
            className={cx(tableTokens.cellText, "block w-full truncate")}
            title={row.original.cedente ?? undefined}
          >
            {row.original.cedente ?? "—"}
          </div>
        ),
      },
      {
        accessorKey: "produto_nome",
        header: "Produto",
        size: 95,
        cell: ({ row }) => (
          <div className={cx(tableTokens.cellText, "block w-full truncate")}>
            {row.original.produto_nome ?? row.original.produto_sigla ?? "—"}
          </div>
        ),
      },
      {
        accessorKey: "ua_nome",
        header: "UA",
        size: 60,
        cell: ({ row }) => (
          <div className={cx(tableTokens.cellText, "block w-full truncate")}>
            {row.original.ua_nome ?? "—"}
          </div>
        ),
      },
      {
        accessorKey: "valor_bruto",
        header: () => <div className="text-right">Valor bruto</div>,
        size: 110,
        cell: ({ row }) => (
          <CurrencyCell value={row.original.valor_bruto} />
        ),
      },
      {
        accessorKey: "taxa",
        header: () => <div className="text-right">Taxa</div>,
        size: 70,
        cell: ({ row }) => (
          <div className={cx(tableTokens.cellNumber, "text-right")}>
            {row.original.taxa != null ? fmtPct1(row.original.taxa) : "—"}
          </div>
        ),
      },
      {
        accessorKey: "prazo_medio",
        header: () => <div className="text-right">Prazo</div>,
        size: 70,
        cell: ({ row }) => (
          <div className={cx(tableTokens.cellNumber, "text-right")}>
            {row.original.prazo_medio != null
              ? fmtDias1(row.original.prazo_medio)
              : "—"}
          </div>
        ),
      },
    ],
    [],
  )

  return (
    <DataTable
      data={operacoes}
      columns={columns}
      density="compact"
      showDensityToggle={false}
      showColumnManager={false}
    />
  )
}
