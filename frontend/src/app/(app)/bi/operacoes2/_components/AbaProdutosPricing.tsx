// src/app/(app)/bi/operacoes2/_components/AbaProdutosPricing.tsx
//
// BI Operacoes2 — Aba 2 (Produtos & Pricing).
//
// Lente sobre 3 dos 5 KPIs do strip global (Volume/Taxa por Produto, Taxa
// Media, Prazo Medio). Responde "qual produto esta rendendo o que, e a que
// custo de prazo/taxa?".
//
// Layout:
//   L1 (full-width): MixTemporalCard — stacked bar 12M fechados por produto
//                    + footer com 3 mini-stats (lider / +alta / -queda MoM)
//   L2 (6+6):        RankingProdutosCard + ScatterProdutosCard
//   L3 (6+6):        HistogramaTaxasCard  + HistogramaPrazosCard
//
// Filtros globais (periodo, produto, UA) aplicam em TUDO via useBiFilters
// (regra dura sec 7.2 do CLAUDE.md). Chips multi-select de produto nos
// histogramas L3 sao FILTROS LOCAIS de visualizacao — operam client-side
// sobre os buckets quebrados por produto que o backend ja entregou.
//
// Hex literals nas option de ECharts sao excecao canonica do CLAUDE.md sec 4
// (Tailwind nao alcanca o canvas).

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import type { EChartsOption } from "echarts"
import { RiInformationLine } from "@remixicon/react"

import { Card } from "@/components/tremor/Card"
import { EChartsCard } from "@/design-system/components/EChartsCard"
import { cardTokens } from "@/design-system/tokens/card"
import { tableTokens } from "@/design-system/tokens/table"
import {
  biOperacoes2,
  type Operacoes2AbaProdutosPricingData,
  type Operacoes2HistogramaProdutoBucket,
  type Operacoes2HistogramaTaxasResumo,
  type Operacoes2HistogramaPrazosResumo,
  type Operacoes2MixTemporalProdutoPonto,
  type Operacoes2ProdutoDestaque,
  type Operacoes2RankingProdutoLinha,
  type Operacoes2ScatterProdutoPonto,
} from "@/lib/api-client"
import { useBiFilters } from "@/lib/hooks/useBiFilters"
import { cx } from "@/lib/utils"

// ─── Paleta canonica A7 Credit (8 cores em ordem de iteracao) ─────────────
//
// Hex literais espelham `chartColors` de `lib/chartUtils` — tailwind nao
// chega no canvas ECharts. Mesmas cores que o usuario veria via
// `getColorClassName(key, "bg")` num <span> Tailwind.
const PRODUTO_COLOR_CYCLE = [
  "#64748B", // slate-500
  "#0EA5E9", // sky-500
  "#14B8A6", // teal-500
  "#10B981", // emerald-500
  "#F59E0B", // amber-500
  "#F43F5E", // rose-500
  "#8B5CF6", // violet-500
  "#6366F1", // indigo-500
]

function colorFor(idx: number): string {
  return PRODUTO_COLOR_CYCLE[idx % PRODUTO_COLOR_CYCLE.length]
}

// ─── Formatadores ──────────────────────────────────────────────────────────

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
const fmtBRLMi = (v: number) =>
  `R$ ${(v / 1_000_000).toFixed(2).replace(".", ",")} mi`
const fmtInt = new Intl.NumberFormat("pt-BR")
const fmtPct1 = (v: number) => `${v.toFixed(1).replace(".", ",")}%`
const fmtPct2 = (v: number) => `${v.toFixed(2).replace(".", ",")}%`
const fmtPp1 = (v: number) =>
  `${v >= 0 ? "+" : ""}${v.toFixed(1).replace(".", ",")} pp`
const fmtDays = (v: number) => `${v.toFixed(1).replace(".", ",")} d`

function fmtMonthShort(iso: string): string {
  const d = new Date(iso)
  return d
    .toLocaleString("pt-BR", { month: "short", year: "2-digit" })
    .replace(".", "")
}

// ─── EmptyChartArea ────────────────────────────────────────────────────────
//
// Placeholder no lugar do canvas ECharts quando nao ha dados. Evita o bug
// "Cannot read properties of undefined (reading 'getRawIndex')" que dispara
// quando o handler de mousemove tenta dispatchar para uma serie sem data
// (ECharts nao guarda graceful em mousemove sobre option vazia, especialmente
// em stacked bar com axisPointer="shadow" + notMerge=true).

function EmptyChartArea({
  message = "Sem dados no período.",
  height = 240,
}: {
  message?: string
  height?: number
}) {
  return (
    <div
      role="status"
      className="flex items-center justify-center text-sm text-gray-400 dark:text-gray-600"
      style={{ height }}
    >
      {message}
    </div>
  )
}

// ─── Componente principal ──────────────────────────────────────────────────

export function AbaProdutosPricing() {
  const { filtersWithFocus } = useBiFilters()
  const q = useQuery({
    queryKey: ["bi", "operacoes2", "aba2", filtersWithFocus],
    queryFn: () => biOperacoes2.abaProdutosPricing(filtersWithFocus),
  })

  if (q.isLoading) return <AbaSkeleton />
  if (!q.data) return null
  const data = q.data.data

  return (
    <div className="flex flex-col gap-4">
      {/* L1 (full-width) — Hero stacked bar 12M */}
      <MixTemporalCard
        mix={data.mix_temporal_12m}
        lider={data.lider_periodo}
        alta={data.maior_alta_mom}
        queda={data.maior_queda_mom}
      />

      {/* L2 (6+6) — Ranking + Scatter */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <RankingProdutosCard ranking={data.ranking} />
        <ScatterProdutosCard pontos={data.scatter_produtos} />
      </div>

      {/* L3 (6+6) — Histogramas */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <HistogramaTaxasCard resumo={data.histograma_taxas} />
        <HistogramaPrazosCard resumo={data.histograma_prazos} />
      </div>
    </div>
  )
}

function AbaSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <div className="h-72 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-900 dark:bg-gray-925" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="h-80 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-900 dark:bg-gray-925" />
        <div className="h-80 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-900 dark:bg-gray-925" />
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="h-72 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-900 dark:bg-gray-925" />
        <div className="h-72 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-900 dark:bg-gray-925" />
      </div>
    </div>
  )
}

// ─── L1 — MixTemporalCard ─────────────────────────────────────────────────

type MixViewMode = "vop" | "share" | "n_ops"

function MixTemporalCard({
  mix,
  lider,
  alta,
  queda,
}: {
  mix: Operacoes2MixTemporalProdutoPonto[]
  lider: Operacoes2ProdutoDestaque | null
  alta: Operacoes2ProdutoDestaque | null
  queda: Operacoes2ProdutoDestaque | null
}) {
  const [mode, setMode] = React.useState<MixViewMode>("vop")

  // Lista unica de produtos (ordenada pelo VOP total desc).
  const produtos = React.useMemo(() => {
    const totals = new Map<string, number>()
    for (const p of mix) {
      totals.set(p.produto_sigla, (totals.get(p.produto_sigla) ?? 0) + p.vop)
    }
    return Array.from(totals.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([sigla]) => sigla)
  }, [mix])

  const periodos = React.useMemo(() => {
    const set = new Set<string>()
    for (const p of mix) set.add(p.periodo)
    return Array.from(set).sort()
  }, [mix])

  // Constroi matriz [produto][periodo] -> valor segundo o mode.
  const series: EChartsOption["series"] = React.useMemo(() => {
    const byProduto = new Map<string, Map<string, number>>()
    for (const p of mix) {
      if (!byProduto.has(p.produto_sigla)) byProduto.set(p.produto_sigla, new Map())
      const v = mode === "vop" ? p.vop : mode === "n_ops" ? p.n_operacoes : p.vop
      byProduto.get(p.produto_sigla)!.set(p.periodo, v)
    }
    // Para mode='share': normalizar por periodo (somatorio = 100%).
    if (mode === "share") {
      const totalsByPeriodo = new Map<string, number>()
      for (const periodo of periodos) {
        let total = 0
        for (const sigla of produtos) {
          total += byProduto.get(sigla)?.get(periodo) ?? 0
        }
        totalsByPeriodo.set(periodo, total)
      }
      // Substitui valores por % (0-100).
      for (const m of Array.from(byProduto.values())) {
        for (const periodo of periodos) {
          const v = m.get(periodo) ?? 0
          const total = totalsByPeriodo.get(periodo) ?? 1
          m.set(periodo, total > 0 ? (v / total) * 100 : 0)
        }
      }
    }
    return produtos.map((sigla, idx) => ({
      name: sigla,
      type: "bar" as const,
      stack: "total",
      barMaxWidth: 32,
      itemStyle: { color: colorFor(idx) },
      data: periodos.map((periodo) => byProduto.get(sigla)?.get(periodo) ?? 0),
    }))
  }, [mix, mode, periodos, produtos])

  const yAxisFormatter = (v: number) => {
    if (mode === "vop") return fmtBRL.format(v)
    if (mode === "share") return `${v.toFixed(0)}%`
    return fmtInt.format(v)
  }

  const tooltipValueFormatter = (v: number) => {
    if (mode === "vop") return fmtBRL.format(v)
    if (mode === "share") return fmtPct1(v)
    return fmtInt.format(v)
  }

  // Paleta explicita por posicao — alinhada com a legenda e com `itemStyle.color`
  // por serie. Necessario porque o merge do EChartsCard (notMerge=false) as vezes
  // nao reaplica `itemStyle.color` quando o set de series muda; expor `color`
  // na option garante que ECharts use nossa sequencia.
  const option: EChartsOption = {
    color: produtos.map((_, idx) => colorFor(idx)),
    grid: { top: 16, right: 12, bottom: 28, left: 64 },
    legend: { show: false },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      valueFormatter: (v) => tooltipValueFormatter(Number(v) || 0),
    },
    xAxis: {
      type: "category",
      data: periodos.map(fmtMonthShort),
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      max: mode === "share" ? 100 : undefined,
      axisLabel: { formatter: yAxisFormatter },
    },
    series,
  }

  return (
    <Card className="flex flex-col p-0">
      <div
        className={cx(
          cardTokens.header,
          "flex flex-row items-start justify-between gap-3",
        )}
      >
        <div>
          <h3 className={cardTokens.headerTitle}>Mix de produtos no tempo</h3>
          <p className={cx(cardTokens.headerSubtitle, "mt-0.5")}>
            Stacked por mês · {periodos.length}{" "}
            {periodos.length === 1 ? "mês" : "meses"} no período · {produtos.length}{" "}
            {produtos.length === 1 ? "produto" : "produtos"}
          </p>
        </div>
        <ViewModeToggle mode={mode} onChange={setMode} />
      </div>

      <div className={cx(cardTokens.body, "flex flex-wrap items-center gap-3")}>
        {produtos.map((sigla, idx) => (
          <span
            key={sigla}
            className="inline-flex items-center gap-1.5 text-[11px] text-gray-600 dark:text-gray-300"
          >
            <span
              aria-hidden="true"
              className="size-2 rounded-sm"
              style={{ backgroundColor: colorFor(idx) }}
            />
            {sigla}
          </span>
        ))}
      </div>

      <div className="px-2 pb-2">
        {produtos.length === 0 ? (
          <EmptyChartArea height={260} />
        ) : (
          <EChartsCard
            option={option}
            height={260}
            className="border-0 bg-transparent p-0 shadow-none"
            // notMerge=true: replace option full a cada render. Default do
            // EChartsCard e merge (notMerge=false), o que em stacked bar com
            // itemStyle.color por serie + mudanca de set de produtos causava
            // ECharts pintar todas as series com a mesma cor da paleta.
            echartsProps={{ notMerge: true }}
          />
        )}
      </div>

      <div
        className={cx(
          cardTokens.footer,
          "flex flex-wrap items-center gap-x-6 gap-y-2 text-[11px] text-gray-500 dark:text-gray-400",
        )}
      >
        <MiniDestaque
          label="Líder do período"
          icon="•"
          d={lider}
          fmt={(v) => fmtPct1(v)}
        />
        <MiniDestaque
          label="Maior alta MoM"
          icon="↑"
          d={alta}
          fmt={fmtPp1}
          tone="up"
        />
        <MiniDestaque
          label="Maior queda MoM"
          icon="↓"
          d={queda}
          fmt={fmtPp1}
          tone="down"
        />
      </div>
    </Card>
  )
}

function ViewModeToggle({
  mode,
  onChange,
}: {
  mode: MixViewMode
  onChange: (m: MixViewMode) => void
}) {
  const opts: { key: MixViewMode; label: string }[] = [
    { key: "vop", label: "Volume" },
    { key: "share", label: "% mix" },
    { key: "n_ops", label: "Nº ops" },
  ]
  return (
    <div className="inline-flex shrink-0 items-center gap-1 rounded border border-gray-200 bg-gray-50 p-0.5 text-[11px] dark:border-gray-800 dark:bg-gray-900">
      {opts.map((o) => (
        <button
          key={o.key}
          type="button"
          onClick={() => onChange(o.key)}
          className={cx(
            "rounded px-2 py-0.5 transition-colors",
            mode === o.key
              ? "bg-white font-medium text-gray-900 shadow-xs dark:bg-gray-950 dark:text-gray-50"
              : "text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-200",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

function MiniDestaque({
  label,
  icon,
  d,
  fmt,
  tone,
}: {
  label: string
  icon: string
  d: Operacoes2ProdutoDestaque | null
  fmt: (v: number) => string
  tone?: "up" | "down"
}) {
  if (!d) {
    return (
      <span className="inline-flex items-center gap-1.5">
        <span className="text-gray-400 dark:text-gray-600">{icon}</span>
        <strong className="text-gray-500 dark:text-gray-400">{label}:</strong>{" "}
        <span className="text-gray-400 dark:text-gray-600">—</span>
      </span>
    )
  }
  const valueClass =
    tone === "up"
      ? "text-emerald-600 dark:text-emerald-400"
      : tone === "down"
        ? "text-red-600 dark:text-red-400"
        : "text-gray-900 dark:text-gray-50"
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="text-gray-400 dark:text-gray-600">{icon}</span>
      <strong className="text-gray-500 dark:text-gray-400">{label}:</strong>{" "}
      <strong className="text-gray-900 dark:text-gray-50">
        {d.nome ?? d.sigla}
      </strong>{" "}
      <span className={cx("tabular-nums font-medium", valueClass)}>
        {fmt(d.valor)}
      </span>
    </span>
  )
}

// ─── L2 Card A — RankingProdutosCard ──────────────────────────────────────

const RANKING_GRID =
  "grid grid-cols-[16px_minmax(0,1.5fr)_72px_56px_56px_56px_56px_56px_44px_72px_56px] items-center gap-x-2"

function RankingProdutosCard({
  ranking,
}: {
  ranking: Operacoes2RankingProdutoLinha[]
}) {
  const sorted = React.useMemo(
    () => [...ranking].sort((a, b) => b.vop - a.vop),
    [ranking],
  )
  return (
    <Card className="flex flex-col p-0">
      <div className={cardTokens.header}>
        <h3 className={cardTokens.headerTitle}>Ranking de produtos</h3>
        <p className={cx(cardTokens.headerSubtitle, "mt-0.5")}>
          Período · taxa/prazo/spread ponderados por VOP · 2 colunas finais
          são MTD do mês corrente
        </p>
      </div>
      <div className={cx(cardTokens.body, "flex flex-col gap-2 overflow-x-auto")}>
        {/* Header */}
        <div
          className={cx(
            RANKING_GRID,
            tableTokens.header,
            "min-w-[680px] border-b border-gray-100 pb-1.5 text-gray-500 dark:border-gray-900 dark:text-gray-400",
          )}
        >
          <span className="text-right">#</span>
          <span>Produto</span>
          <span className="text-right">VOP</span>
          <span className="text-right">% mix</span>
          <span className="text-right">Δ MoM</span>
          <span className="text-right">Taxa</span>
          <span className="text-right">Prazo</span>
          <span className="text-right">Spread</span>
          <span className="text-right">Nº ops</span>
          <span
            className="text-right text-gray-400 dark:text-gray-600"
            title="VOP MTD do mês corrente"
          >
            VOP mês
          </span>
          <span
            className="text-right text-gray-400 dark:text-gray-600"
            title="Taxa média MTD do mês corrente"
          >
            Taxa mês
          </span>
        </div>
        {sorted.map((r, i) => (
          <RankingRow key={r.sigla} r={r} rank={i + 1} />
        ))}
      </div>
    </Card>
  )
}

function RankingRow({ r, rank }: { r: Operacoes2RankingProdutoLinha; rank: number }) {
  const deltaClass =
    r.delta_mom_pp == null
      ? "text-gray-400 dark:text-gray-600"
      : r.delta_mom_pp >= 0
        ? "text-emerald-600 dark:text-emerald-400"
        : "text-red-600 dark:text-red-400"
  return (
    <div className={cx(RANKING_GRID, "min-w-[680px] py-0.5")}>
      <span className={cx(tableTokens.cellNumberSecondary, "text-right")}>
        {rank}
      </span>
      <span className={cx(tableTokens.cellText, "truncate")} title={r.sigla}>
        {r.nome ?? r.sigla}
      </span>
      <span className={cx(tableTokens.cellNumber, "text-right")}>
        {fmtBRLMi(r.vop)}
      </span>
      <span className={cx(tableTokens.cellNumber, "text-right")}>
        {fmtPct1(r.pct)}
      </span>
      <span
        className={cx(
          tableTokens.cellNumber,
          "text-right tabular-nums font-medium",
          deltaClass,
        )}
      >
        {r.delta_mom_pp == null ? "—" : fmtPp1(r.delta_mom_pp)}
      </span>
      <span className={cx(tableTokens.cellNumber, "text-right")}>
        {fmtPct2(r.taxa_media)}
      </span>
      <span className={cx(tableTokens.cellNumber, "text-right")}>
        {fmtDays(r.prazo_medio)}
      </span>
      <span className={cx(tableTokens.cellNumber, "text-right")}>
        {fmtPct2(r.spread_medio)}
      </span>
      <span className={cx(tableTokens.cellNumberSecondary, "text-right")}>
        {fmtInt.format(r.n_operacoes)}
      </span>
      <span
        className={cx(tableTokens.cellNumberSecondary, "text-right")}
        title={fmtBRLFull.format(r.vop_mes_corrente)}
      >
        {fmtBRLMi(r.vop_mes_corrente)}
      </span>
      <span className={cx(tableTokens.cellNumberSecondary, "text-right")}>
        {fmtPct2(r.taxa_media_mes_corrente)}
      </span>
    </div>
  )
}

// ─── L2 Card B — ScatterProdutosCard ──────────────────────────────────────

function ScatterProdutosCard({
  pontos,
}: {
  pontos: Operacoes2ScatterProdutoPonto[]
}) {
  // Tamanho do simbolo: raiz quadrada do VOP normalizada — area ~ VOP.
  const maxVop = Math.max(1, ...pontos.map((p) => p.vop))
  function symbolSize(vop: number): number {
    // 8px (vop=0) -> 36px (vop=maxVop)
    if (maxVop <= 0) return 8
    return 8 + Math.sqrt(vop / maxVop) * 28
  }

  // Cada produto vira 2 series scatter: solido (periodo) + halo (mes corrente).
  const sortedByVop = [...pontos].sort((a, b) => b.vop - a.vop)
  const series: EChartsOption["series"] = sortedByVop.flatMap((p, idx) => {
    const c = colorFor(idx)
    return [
      {
        name: p.sigla,
        type: "scatter" as const,
        symbol: "circle" as const,
        symbolSize: symbolSize(p.vop),
        itemStyle: { color: c, opacity: 0.85 },
        data: [
          {
            value: [p.prazo_medio, p.taxa_media],
            sigla: p.sigla,
            nome: p.nome,
            vop: p.vop,
            kind: "periodo",
          },
        ],
      },
      {
        name: `${p.sigla} (mês)`,
        type: "scatter" as const,
        symbol: "circle" as const,
        symbolSize: symbolSize(p.vop_mes_corrente),
        itemStyle: {
          color: "transparent",
          borderColor: c,
          borderWidth: 1.5,
          opacity: 0.7,
        },
        data: [
          {
            value: [p.prazo_medio_mes_corrente, p.taxa_media_mes_corrente],
            sigla: p.sigla,
            nome: p.nome,
            vop: p.vop_mes_corrente,
            kind: "mes",
          },
        ],
      },
    ]
  })

  const option: EChartsOption = {
    grid: { top: 24, right: 16, bottom: 36, left: 56 },
    legend: { show: false },
    tooltip: {
      trigger: "item",
      formatter: (params) => {
        // ECharts entrega `params` como any em scatter; cast pontual.
        const d = (params as { data: Record<string, unknown> }).data
        const sigla = String(d.sigla ?? "")
        const nome = String(d.nome ?? sigla)
        const kindLabel =
          d.kind === "mes" ? "MTD mês" : "Período"
        return [
          `<b>${sigla}</b> ${nome === sigla ? "" : ` — ${nome}`}`,
          `<span style="color:#9CA3AF">${kindLabel}</span>`,
          `Prazo: ${fmtDays(Number((d.value as number[])[0]))}`,
          `Taxa: ${fmtPct2(Number((d.value as number[])[1]))}`,
          `VOP: ${fmtBRL.format(Number(d.vop ?? 0))}`,
        ].join("<br/>")
      },
    },
    xAxis: {
      type: "value",
      name: "Prazo (dias)",
      nameLocation: "middle",
      nameGap: 24,
      axisLabel: { formatter: (v: number) => `${v.toFixed(0)}d` },
    },
    yAxis: {
      type: "value",
      name: "Taxa (% a.m.)",
      nameLocation: "middle",
      nameGap: 40,
      axisLabel: { formatter: (v: number) => `${v.toFixed(1)}%` },
    },
    series,
  }

  return (
    <Card className="flex flex-col p-0">
      <div className={cardTokens.header}>
        <h3 className={cardTokens.headerTitle}>Taxa × Prazo por produto</h3>
        <p className={cx(cardTokens.headerSubtitle, "mt-0.5")}>
          Tamanho ∝ VOP · ponto sólido = período · halo = MTD mês corrente
        </p>
      </div>
      <div className={cx(cardTokens.body, "flex flex-wrap items-center gap-3 pb-2")}>
        {sortedByVop.map((p, idx) => (
          <span
            key={p.sigla}
            className="inline-flex items-center gap-1.5 text-[11px] text-gray-600 dark:text-gray-300"
          >
            <span
              aria-hidden="true"
              className="size-2 rounded-full"
              style={{ backgroundColor: colorFor(idx) }}
            />
            {p.sigla}
          </span>
        ))}
      </div>
      <div className="px-2 pb-2">
        {sortedByVop.length === 0 ? (
          <EmptyChartArea height={300} />
        ) : (
          <EChartsCard option={option} height={300} className="border-0 bg-transparent p-0 shadow-none" />
        )}
      </div>
    </Card>
  )
}

// ─── L3 Card A — HistogramaTaxasCard ──────────────────────────────────────

function HistogramaTaxasCard({
  resumo,
}: {
  resumo: Operacoes2HistogramaTaxasResumo
}) {
  // Lista unica de produtos no histograma (default: todos selecionados).
  const allProdutos = React.useMemo(() => {
    const set = new Set<string>()
    for (const b of resumo.buckets) set.add(b.produto_sigla)
    return Array.from(set).sort()
  }, [resumo.buckets])
  const [selected, setSelected] = React.useState<Set<string>>(
    () => new Set(allProdutos),
  )
  // Re-sincroniza quando muda o filtro global (allProdutos pode mudar).
  React.useEffect(() => {
    setSelected(new Set(allProdutos))
  }, [allProdutos])

  return (
    <HistogramaCard
      title="Distribuição de taxas"
      subtitle={`Bucket dinâmico de ${resumo.bucket_size_pp.toFixed(2)} pp · ponderado por VOP · média e mediana sobrepostas`}
      buckets={resumo.buckets}
      allProdutos={allProdutos}
      selected={selected}
      onSelectedChange={setSelected}
      bucketAxisFormatter={(lower) => `${lower.toFixed(2)}%`}
      tooltipBucketFormatter={(lower, upper) =>
        `${lower.toFixed(2)}% – ${upper.toFixed(2)}%`
      }
      markLines={[
        { value: resumo.media_ponderada, label: "Média" },
        { value: resumo.mediana, label: "Mediana" },
      ]}
      showVopToggle
      defaultYMode="vop"
    />
  )
}

// ─── L3 Card B — HistogramaPrazosCard ─────────────────────────────────────

function HistogramaPrazosCard({
  resumo,
}: {
  resumo: Operacoes2HistogramaPrazosResumo
}) {
  const allProdutos = React.useMemo(() => {
    const set = new Set<string>()
    for (const b of resumo.buckets) set.add(b.produto_sigla)
    return Array.from(set).sort()
  }, [resumo.buckets])
  const [selected, setSelected] = React.useState<Set<string>>(
    () => new Set(allProdutos),
  )
  React.useEffect(() => {
    setSelected(new Set(allProdutos))
  }, [allProdutos])

  return (
    <HistogramaCard
      title="Distribuição de prazos"
      subtitle="Buckets fixos: 0-30, 31-60, 61-90, 91-180, 180+ dias"
      buckets={resumo.buckets}
      allProdutos={allProdutos}
      selected={selected}
      onSelectedChange={setSelected}
      bucketAxisFormatter={(_lower, label) => label}
      tooltipBucketFormatter={(_lower, _upper, label) => label}
      markLines={[]}
      showVopToggle
    />
  )
}

// ─── Histograma genérico (compartilhado entre taxas e prazos) ─────────────

type HistogramaYMode = "count" | "vop"

function HistogramaCard({
  title,
  subtitle,
  buckets,
  allProdutos,
  selected,
  onSelectedChange,
  bucketAxisFormatter,
  tooltipBucketFormatter,
  markLines,
  showVopToggle,
  defaultYMode = "count",
}: {
  title: string
  subtitle: string
  buckets: Operacoes2HistogramaProdutoBucket[]
  allProdutos: string[]
  selected: Set<string>
  onSelectedChange: (next: Set<string>) => void
  bucketAxisFormatter: (lower: number, label: string) => string
  tooltipBucketFormatter: (lower: number, upper: number, label: string) => string
  markLines: { value: number; label: string }[]
  showVopToggle: boolean
  /** Eixo Y inicial. Default "count" (nº ops) — taxas usam "vop" porque
   * uma operação grande de R$10M pesa mais para "taxa típica praticada"
   * que 100 operações de R$10k. Estatísticas sobrepostas (média/mediana)
   * já vêm ponderadas por VOP — manter o eixo em count seria dissonante. */
  defaultYMode?: HistogramaYMode
}) {
  const [yMode, setYMode] = React.useState<HistogramaYMode>(defaultYMode)

  // Agrega buckets selecionados por (lower, upper, label) somando count e vop.
  type Agg = { lower: number; upper: number; label: string; count: number; vop: number }
  const agg: Agg[] = React.useMemo(() => {
    const map = new Map<string, Agg>()
    for (const b of buckets) {
      if (!selected.has(b.produto_sigla)) continue
      const key = `${b.bucket_lower}|${b.bucket_label}`
      const cur = map.get(key)
      if (cur) {
        cur.count += b.count
        cur.vop += b.vop
      } else {
        map.set(key, {
          lower: b.bucket_lower,
          upper: b.bucket_upper,
          label: b.bucket_label,
          count: b.count,
          vop: b.vop,
        })
      }
    }
    return Array.from(map.values()).sort((a, b) => a.lower - b.lower)
  }, [buckets, selected])

  const xLabels = agg.map((a) => bucketAxisFormatter(a.lower, a.label))
  const yValues = agg.map((a) => (yMode === "vop" ? a.vop : a.count))

  const option: EChartsOption = {
    grid: { top: 16, right: 12, bottom: 36, left: 56 },
    legend: { show: false },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (params) => {
        const arr = params as Array<{ dataIndex: number; value: number }>
        if (arr.length === 0) return ""
        const i = arr[0].dataIndex
        const a = agg[i]
        if (!a) return ""
        const range = tooltipBucketFormatter(a.lower, a.upper, a.label)
        return [
          `<b>${range}</b>`,
          `Nº ops: ${fmtInt.format(a.count)}`,
          `VOP: ${fmtBRL.format(a.vop)}`,
        ].join("<br/>")
      },
    },
    xAxis: {
      type: "category",
      data: xLabels,
      axisTick: { show: false },
      axisLabel: { rotate: xLabels.length > 12 ? 45 : 0 },
    },
    yAxis: {
      type: "value",
      axisLabel: {
        formatter: (v: number) =>
          yMode === "vop" ? fmtBRL.format(v) : fmtInt.format(v),
      },
    },
    series: [
      {
        type: "bar",
        data: yValues,
        barMaxWidth: 28,
        itemStyle: { color: "#2A4D7A", borderRadius: [3, 3, 0, 0] },
        markLine:
          markLines.length > 0
            ? {
                symbol: "none",
                lineStyle: { color: "#9CA3AF", width: 1.5 },
                data: markLines.map((ml, idx) => ({
                  xAxis: nearestBucketIndex(agg, ml.value),
                  name: ml.label,
                  label: { formatter: ml.label, color: "#6B7280" },
                  lineStyle: {
                    color: "#9CA3AF",
                    type: idx === 0 ? "solid" : "dashed",
                  },
                })),
              }
            : undefined,
      },
    ],
  }

  return (
    <Card className="flex flex-col p-0">
      <div
        className={cx(
          cardTokens.header,
          "flex flex-row items-start justify-between gap-3",
        )}
      >
        <div>
          <h3 className={cardTokens.headerTitle}>{title}</h3>
          <p className={cx(cardTokens.headerSubtitle, "mt-0.5")}>{subtitle}</p>
        </div>
        {showVopToggle && (
          <YModeToggle mode={yMode} onChange={setYMode} />
        )}
      </div>
      <div className={cx(cardTokens.body, "flex flex-col gap-3")}>
        <ProdutoChipFilter
          all={allProdutos}
          selected={selected}
          onChange={onSelectedChange}
        />
        <div className="-mx-2">
          {agg.length === 0 ? (
            <EmptyChartArea height={220} />
          ) : (
            <EChartsCard option={option} height={220} className="border-0 bg-transparent p-0 shadow-none" />
          )}
        </div>
      </div>
    </Card>
  )
}

function YModeToggle({
  mode,
  onChange,
}: {
  mode: HistogramaYMode
  onChange: (m: HistogramaYMode) => void
}) {
  const opts: { key: HistogramaYMode; label: string }[] = [
    { key: "count", label: "Nº ops" },
    { key: "vop", label: "VOP" },
  ]
  return (
    <div className="inline-flex shrink-0 items-center gap-1 rounded border border-gray-200 bg-gray-50 p-0.5 text-[11px] dark:border-gray-800 dark:bg-gray-900">
      {opts.map((o) => (
        <button
          key={o.key}
          type="button"
          onClick={() => onChange(o.key)}
          className={cx(
            "rounded px-2 py-0.5 transition-colors",
            mode === o.key
              ? "bg-white font-medium text-gray-900 shadow-xs dark:bg-gray-950 dark:text-gray-50"
              : "text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-200",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

function ProdutoChipFilter({
  all,
  selected,
  onChange,
}: {
  all: string[]
  selected: Set<string>
  onChange: (next: Set<string>) => void
}) {
  function toggle(sigla: string) {
    const next = new Set(selected)
    if (next.has(sigla)) {
      if (next.size > 1) next.delete(sigla) // não permite zerar tudo
    } else {
      next.add(sigla)
    }
    onChange(next)
  }
  const allOn = selected.size === all.length
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="inline-flex items-center gap-1 text-[11px] text-gray-500 dark:text-gray-400">
        <RiInformationLine
          aria-hidden="true"
          className="size-3 text-gray-400 dark:text-gray-600"
        />
        Filtra só este card
      </span>
      <button
        type="button"
        onClick={() => onChange(new Set(all))}
        disabled={allOn}
        className={cx(
          "rounded border px-2 py-0.5 text-[11px] transition-colors",
          allOn
            ? "border-blue-500 bg-blue-50 text-blue-700 dark:border-blue-500/40 dark:bg-blue-500/10 dark:text-blue-300"
            : "border-gray-200 text-gray-600 hover:bg-gray-50 dark:border-gray-800 dark:text-gray-400 dark:hover:bg-gray-900",
        )}
      >
        Todos
      </button>
      {all.map((sigla, idx) => {
        const on = selected.has(sigla)
        return (
          <button
            key={sigla}
            type="button"
            onClick={() => toggle(sigla)}
            className={cx(
              "inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[11px] transition-colors",
              on
                ? "border-gray-300 bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-50"
                : "border-gray-200 bg-gray-50 text-gray-400 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-600",
            )}
          >
            <span
              aria-hidden="true"
              className="size-1.5 rounded-full"
              style={{
                backgroundColor: on ? colorFor(idx) : "#D1D5DB",
              }}
            />
            {sigla}
          </button>
        )
      })}
    </div>
  )
}

function nearestBucketIndex(
  agg: { lower: number; upper: number }[],
  value: number,
): number {
  if (agg.length === 0) return 0
  for (let i = 0; i < agg.length; i++) {
    if (value >= agg[i].lower && value < agg[i].upper) return i
  }
  return agg.length - 1
}
