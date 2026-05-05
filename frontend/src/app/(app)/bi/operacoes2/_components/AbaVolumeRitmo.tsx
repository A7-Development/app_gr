// src/app/(app)/bi/operacoes2/_components/AbaVolumeRitmo.tsx
//
// Aba 1 da pagina /bi/operacoes2 — Volume & Ritmo.
//
// Estrutura (refatorada 2026-05-04 — Linha 1 absorveu Produto):
//   Linha 1  · 3 colunas: Hero combo Evolucao Mensal + Donut VOP por UA +
//              Lista VOP por Produto. Hero tem seletor LOCAL de UA
//              (filtragem client-side a partir de `evolucao_12m_por_ua` —
//              sem nova ida ao backend).
//   Linha 2 (Padrao B)  · Ritmo do mes corrente + Projecao + Pace
//                          (degraded mode quando wh_dim_dia_util esta vazia)
//   Linha 3 (Padrao A)  · 4 KPIs secundarios de volume
//   Linha 4 (Padrao C)  · Heatmap dow x semana + Por dia da semana
//
// Strip dual em quebras (Opcao 4 paradigma 2026-05-03):
//   - QuebraCard (Produto na L1 col 3): toggle "Periodo | Mes | Ambos" +
//     "Volume | Δ MoM | Δ YoY". "Ambos" sobrepoe as duas barras
//     (clara=periodo / saturada=mes corrente).
//   - QuebraDonut (UA na L1 col 2): toggle simplificado "Periodo | Mes" +
//     "Volume". Donut nao representa MoM/YoY bem; "Ambos" precisaria 2
//     donuts concentricos — preferimos toggle simples e legivel.

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import {
  RiArrowDownLine,
  RiArrowUpLine,
  RiBuilding2Line,
  RiCalendarEventLine,
  RiSubtractLine,
} from "@remixicon/react"
import type { EChartsOption } from "echarts"

import { Card } from "@/components/tremor/Card"
import { cardTokens } from "@/design-system/tokens/card"
import { EChartsCard } from "@/design-system/components/EChartsCard"
import {
  EvolucaoMensalCard,
  type EvolucaoMensalPonto,
} from "@/design-system/components/EvolucaoMensalCard"
import { VizParam } from "@/design-system/components/VizParam"
import { tableTokens } from "@/design-system/tokens/table"
import { biOperacoes2 } from "@/lib/api-client"
import type {
  Operacoes2DiaSemanaResumo,
  Operacoes2EvolucaoMensalPonto,
  Operacoes2EvolucaoPorUaPonto,
  Operacoes2HeatmapPonto,
  Operacoes2KpiSecundario,
  Operacoes2KpisSecundariosVolume,
  Operacoes2MesDestaque,
  Operacoes2MesCorrenteVsMedia,
  Operacoes2PaceDiario,
  Operacoes2QuebraDimensaoLinha,
  Operacoes2RitmoMesCorrente,
} from "@/lib/api-client"
import { useBiFilters, type PresetKey } from "@/lib/hooks/useBiFilters"
import { cx } from "@/lib/utils"

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
const fmtInt = new Intl.NumberFormat("pt-BR")
const fmtPct1 = (v: number) => `${v.toFixed(1).replace(".", ",")}%`
const fmtBRLNumeric = (v: number) => fmtBRL.format(v)

function fmtMonthShort(iso: string): string {
  const [y, m] = iso.split("-").map(Number)
  return new Date(y, (m ?? 1) - 1, 1)
    .toLocaleString("pt-BR", { month: "short", year: "2-digit" })
    .replace(".", "")
}

/**
 * Linha de tendencia por regressao linear (minimos quadrados).
 * Devolve um array do mesmo tamanho de `values`, onde cada posicao i
 * contem o valor predito pela reta y = a + b*i.
 * Para n < 2 ou variancia zero em x, devolve uma linha horizontal na media.
 */
function computeLinearTrend(values: number[]): number[] {
  const n = values.length
  if (n === 0) return []
  if (n === 1) return [values[0]]
  let sumX = 0,
    sumY = 0,
    sumXY = 0,
    sumX2 = 0
  for (let i = 0; i < n; i++) {
    sumX += i
    sumY += values[i]
    sumXY += i * values[i]
    sumX2 += i * i
  }
  const denom = n * sumX2 - sumX * sumX
  if (denom === 0) {
    const mean = sumY / n
    return values.map(() => mean)
  }
  const slope = (n * sumXY - sumX * sumY) / denom
  const intercept = (sumY - slope * sumX) / n
  return values.map((_, i) => intercept + slope * i)
}

const PRESET_TO_LABEL: Record<PresetKey, string> = {
  ytd: "Ano até hoje",
  "3m": "Últimos 3 meses",
  "6m": "Últimos 6 meses",
  "12m": "Últimos 12 meses",
  "24m": "Últimos 24 meses",
  "36m": "Últimos 36 meses",
  all: "Todo histórico",
}

// ─── Componente principal ──────────────────────────────────────────────────

export function AbaVolumeRitmo() {
  const { filtersWithFocus, preset } = useBiFilters()
  const q = useQuery({
    queryKey: ["bi", "operacoes2", "aba1", filtersWithFocus],
    queryFn: () => biOperacoes2.abaVolumeRitmo(filtersWithFocus),
  })

  if (q.isLoading) return <AbaSkeleton />
  if (!q.data) return null
  const data = q.data.data

  return (
    <div className="flex flex-col gap-6">
      <Linha1HeroComUa
        evolucao={data.evolucao_12m}
        evolucaoPorUa={data.evolucao_12m_por_ua}
        melhorMes={data.melhor_mes}
        piorMes={data.pior_mes}
        mesVsMedia={data.mes_corrente_vs_media}
        porUa={data.por_ua}
        porProduto={data.por_produto}
        presetLabel={preset ? PRESET_TO_LABEL[preset] : "Personalizado"}
      />
      <Linha2Ritmo ritmo={data.ritmo} pace={data.pace_diario} />
      <Linha3Kpis kpis={data.kpis_secundarios} />
      <Linha5Sazonalidade
        heatmap={data.heatmap_dow_semana}
        porDia={data.por_dia_semana}
      />
    </div>
  )
}

function AbaSkeleton() {
  return (
    <div className="flex flex-col gap-6">
      {/* Linha 1: Hero 50% + Donut UA 25% + Lista Produto 25% */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
        <div className="h-64 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900 lg:col-span-2" />
        <div className="h-64 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900" />
        <div className="h-64 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900" />
      </div>
      {/* Demais linhas */}
      <div className="h-48 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900" />
      <div className="h-32 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900" />
    </div>
  )
}

// ─── Linha 1 — 3 colunas: Hero Evolucao + Donut UA + Lista Produto ────────

function Linha1HeroComUa({
  evolucao,
  evolucaoPorUa,
  melhorMes,
  piorMes,
  mesVsMedia,
  porUa,
  porProduto,
  presetLabel,
}: {
  evolucao: Operacoes2EvolucaoMensalPonto[]
  evolucaoPorUa: Operacoes2EvolucaoPorUaPonto[]
  melhorMes: Operacoes2MesDestaque | null
  piorMes: Operacoes2MesDestaque | null
  mesVsMedia: Operacoes2MesCorrenteVsMedia | null
  porUa: Operacoes2QuebraDimensaoLinha[]
  porProduto: Operacoes2QuebraDimensaoLinha[]
  presetLabel: string
}) {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
      <div className="lg:col-span-2">
        <HeroEvolucao
          evolucao={evolucao}
          evolucaoPorUa={evolucaoPorUa}
          melhorMes={melhorMes}
          piorMes={piorMes}
          mesVsMedia={mesVsMedia}
          presetLabel={presetLabel}
        />
      </div>
      <QuebraDonut
        title="VOP por Unidade Administrativa"
        rows={porUa}
      />
      <QuebraCard title="VOP por Produto" rows={porProduto} topN={10} />
    </div>
  )
}

function HeroEvolucao({
  evolucao,
  evolucaoPorUa,
  melhorMes,
  piorMes,
  mesVsMedia,
  presetLabel,
}: {
  evolucao: Operacoes2EvolucaoMensalPonto[]
  evolucaoPorUa: Operacoes2EvolucaoPorUaPonto[]
  melhorMes: Operacoes2MesDestaque | null
  piorMes: Operacoes2MesDestaque | null
  mesVsMedia: Operacoes2MesCorrenteVsMedia | null
  presetLabel: string
}) {
  // Seletor LOCAL de UA — nao mexe no filtro global (que ja existe na toolbar).
  // Funciona como "lente" para visualizar a evolucao 12M de uma UA especifica
  // ou agregada (Todas). Filtragem client-side a partir de `evolucaoPorUa`.
  const [selectedUaId, setSelectedUaId] = React.useState<number | null>(null)

  // Lista unica de UAs disponiveis (extraida da serie segmentada).
  const uaOptions = React.useMemo(() => {
    const map = new Map<number, string>()
    for (const p of evolucaoPorUa) {
      if (!map.has(p.ua_id)) map.set(p.ua_id, p.ua_nome)
    }
    return Array.from(map.entries())
      .map(([id, nome]) => ({ id, nome }))
      .sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"))
  }, [evolucaoPorUa])

  // Adapta a serie de dominio para o ponto canonico do EvolucaoMensalCard.
  // `comparativo` recebe a linha de tendencia (regressao linear sobre o VOP),
  // substituindo a antiga MM 3M.
  // Quando UA selecionada, n_operacoes/ticket_medio nao sao apurados por UA
  // hoje — entao tooltipExtras e omitido nesse caso.
  const data = React.useMemo<EvolucaoMensalPonto[]>(() => {
    const base =
      selectedUaId === null
        ? evolucao.map((p) => ({
            periodo: p.periodo,
            vop: p.vop,
            tooltipExtras: [
              { label: "Operações", value: fmtInt.format(p.n_operacoes) },
              { label: "Ticket médio", value: fmtBRLFull.format(p.ticket_medio) },
            ] as Array<{ label: string; value: string }>,
          }))
        : evolucaoPorUa
            .filter((p) => p.ua_id === selectedUaId)
            .map((p) => ({
              periodo: p.periodo,
              vop: p.vop,
              tooltipExtras: undefined as
                | Array<{ label: string; value: string }>
                | undefined,
            }))

    const trend = computeLinearTrend(base.map((p) => p.vop))
    return base.map((p, i) => ({
      periodo: p.periodo,
      valor: p.vop,
      comparativo: trend[i],
      tooltipExtras: p.tooltipExtras,
    }))
  }, [evolucao, evolucaoPorUa, selectedUaId])

  return (
    <EvolucaoMensalCard
      title="Evolução do VOP"
      presetLabel={presetLabel}
      data={data}
      dimension={{
        label: "UA",
        icon: RiBuilding2Line,
        options: uaOptions,
        value: selectedUaId,
        onChange: (v) => setSelectedUaId(v as number | null),
        allLabel: "Todas as UAs",
      }}
      comparativoLabel="Tendência"
      destaques={{
        melhor: melhorMes
          ? { periodo: melhorMes.periodo, valor: melhorMes.vop }
          : null,
        pior: piorMes
          ? { periodo: piorMes.periodo, valor: piorMes.vop }
          : null,
        vsMedia: mesVsMedia ? { pct: mesVsMedia.pct } : null,
      }}
      valueFormatter={(v) => fmtBRLFull.format(v)}
      axisFormatter={(v) => fmtBRL.format(v)}
      dataLabelFormatter={(v) =>
        (v / 1_000_000).toFixed(1).replace(".", ",")
      }
      height={248}
    />
  )
}

// ─── QuebraDonut — UA via donut ECharts (top 3 + Outros) ──────────────────

// Paleta monocromatica de azul para fatias do donut. Hex inline e excecao
// canonica do CLAUDE.md §4 (Tailwind nao alcanca canvas ECharts).
const DONUT_PALETTE = [
  "#1E3A8A", // blue-900
  "#2563EB", // blue-600
  "#60A5FA", // blue-400
  "#93C5FD", // blue-300 — usado para "Outros"
] as const

const DONUT_ESCOPO_TOGGLES = ["Período", "Mês"] as const
type DonutEscopoToggle = (typeof DONUT_ESCOPO_TOGGLES)[number]

function QuebraDonut({
  title,
  rows,
}: {
  title: string
  rows: Operacoes2QuebraDimensaoLinha[]
}) {
  const [escopo, setEscopo] = React.useState<DonutEscopoToggle>("Período")

  const valFor = React.useCallback(
    (r: Operacoes2QuebraDimensaoLinha) =>
      escopo === "Mês" ? r.vop_mes_corrente : r.vop,
    [escopo],
  )

  // Top 3 + agregacao em "Outros" (regra do brief: donut com ate 3 fatias).
  const fatias = React.useMemo(() => {
    const sorted = [...rows].sort((a, b) => valFor(b) - valFor(a))
    const top = sorted.slice(0, 3).map((r) => ({
      name: r.categoria,
      value: valFor(r),
    }))
    const outros = sorted.slice(3)
    const outrosTotal = outros.reduce((acc, r) => acc + valFor(r), 0)
    if (outrosTotal > 0) {
      top.push({ name: "Outros", value: outrosTotal })
    }
    return top.filter((f) => f.value > 0)
  }, [rows, valFor])

  const total = fatias.reduce((acc, f) => acc + f.value, 0)

  const option: EChartsOption = React.useMemo(
    () => ({
      tooltip: {
        trigger: "item",
        formatter: (params: unknown) => {
          const p = params as { name: string; value: number; percent: number }
          return `<strong>${p.name}</strong><br/>${fmtBRLFull.format(p.value)} · ${p.percent.toFixed(1).replace(".", ",")}%`
        },
      },
      legend: {
        orient: "vertical",
        right: 8,
        top: "middle",
        itemWidth: 8,
        itemHeight: 8,
        textStyle: { fontSize: 11 },
        formatter: (name: string) => {
          const f = fatias.find((x) => x.name === name)
          if (!f) return name
          const pct = total > 0 ? (f.value / total) * 100 : 0
          return `${name}  ${pct.toFixed(0)}%`
        },
      },
      series: [
        {
          type: "pie",
          radius: ["45%", "65%"],
          center: ["32%", "50%"],
          avoidLabelOverlap: true,
          label: {
            show: true,
            position: "outside",
            // Valor em milhoes, 1 casa decimal, sem R$ (ex.: "12,3 M").
            formatter: (p) =>
              `${((p as { value: number }).value / 1_000_000)
                .toFixed(1)
                .replace(".", ",")} M`,
            fontSize: 11,
            color: "#374151",
          },
          labelLine: { show: true, length: 6, length2: 8 },
          data: fatias.map((f, i) => ({
            ...f,
            itemStyle: {
              color: DONUT_PALETTE[i % DONUT_PALETTE.length],
              borderColor: "#FFFFFF",
              borderWidth: 2,
            },
          })),
        },
      ],
    }),
    [fatias, total],
  )

  return (
    <EChartsCard
      title={title}
      caption={
        escopo === "Mês"
          ? "Mês corrente · top 3 + Outros"
          : "Período do filtro · top 3 + Outros"
      }
      option={option}
      height={270}
      actions={
        <VizParam
          options={DONUT_ESCOPO_TOGGLES}
          value={escopo}
          onChange={setEscopo}
        />
      }
    />
  )
}

// ─── Linha 2 (Padrao B) — Ritmo + Projecao + Pace ─────────────────────────

function Linha2Ritmo({
  ritmo,
  pace,
}: {
  ritmo: Operacoes2RitmoMesCorrente | null
  pace: Operacoes2PaceDiario | null
}) {
  if (!ritmo) {
    return <Linha2Empty />
  }
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
      <Linha2HeroRitmo ritmo={ritmo} className="lg:col-span-6" />
      <Linha2Projecao ritmo={ritmo} className="lg:col-span-3" />
      <Linha2Pace pace={pace} className="lg:col-span-3" />
    </div>
  )
}

function Linha2Empty() {
  return (
    <Card className="flex flex-col items-center justify-center gap-2 px-6 py-10 text-center">
      <RiCalendarEventLine
        className="size-8 text-gray-300 dark:text-gray-700"
        aria-hidden="true"
      />
      <p className="text-sm font-medium text-gray-700 dark:text-gray-200">
        Ritmo do mês corrente · indisponível
      </p>
      <p className="max-w-md text-xs text-gray-500 dark:text-gray-400">
        Esta análise depende de <code>wh_dim_dia_util</code>. Rode{" "}
        <code className="rounded bg-gray-100 px-1 py-0.5 dark:bg-gray-800">
          python -m scripts.populate_dia_util --tenant a7-credit
        </code>{" "}
        para popular o calendário (feriados nacionais via Bitfin).
      </p>
    </Card>
  )
}

function Linha2HeroRitmo({
  ritmo,
  className,
}: {
  ritmo: Operacoes2RitmoMesCorrente
  className?: string
}) {
  const deltaTxt =
    ritmo.delta_pct == null
      ? "—"
      : `${ritmo.delta_pct >= 0 ? "+" : ""}${fmtPct1(ritmo.delta_pct)}`
  const isAhead = (ritmo.delta_pct ?? 0) >= 0
  const badgeClass = isAhead
    ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
    : "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300"

  // Mini chart acumulado dia-a-dia.
  const option: EChartsOption = {
    grid: { top: 8, right: 8, bottom: 24, left: 56 },
    tooltip: { trigger: "axis" },
    xAxis: {
      type: "category",
      data: ritmo.acumulado_dia_a_dia.map((p) => `DU ${p.du_index}`),
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      axisLabel: { formatter: (v: number) => fmtBRL.format(v) },
    },
    series: [
      {
        name: "Mês corrente",
        type: "line",
        smooth: true,
        symbol: "none",
        data: ritmo.acumulado_dia_a_dia.map((p) => p.corrente),
        lineStyle: { color: "#2A4D7A", width: 2 },
      },
      {
        name: "Mês anterior",
        type: "line",
        smooth: true,
        symbol: "none",
        data: ritmo.acumulado_dia_a_dia.map((p) => p.anterior),
        lineStyle: { color: "#9CA3AF", width: 1.5, type: "dashed" },
      },
    ],
  }

  return (
    <Card className={cx("flex flex-col gap-3 p-5", className)}>
      <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
        Ritmo do mês corrente
      </p>
      <p className="text-[18px] font-semibold leading-snug text-gray-900 dark:text-gray-50">
        Estamos{" "}
        <span
          className={cx(
            "inline-flex items-center rounded px-1.5 py-0.5 text-[16px] tabular-nums",
            badgeClass,
          )}
        >
          {deltaTxt}
        </span>{" "}
        <span className="text-gray-700 dark:text-gray-300">
          {isAhead ? "à frente" : "atrás"}
        </span>{" "}
        do mês anterior nos mesmos {ritmo.du_corridos} dias úteis.
      </p>
      <p className="text-[11px] text-gray-500 dark:text-gray-400">
        {ritmo.du_corridos} DU corridos de {ritmo.du_total_mes} · projeção fim
        do mês:{" "}
        <strong className="text-gray-900 dark:text-gray-50">
          {fmtBRLFull.format(ritmo.projecao_fim_mes)}
        </strong>
      </p>
      <div className="-mx-2 mt-1">
        <EChartsCardInline option={option} height={160} />
      </div>
    </Card>
  )
}

function Linha2Projecao({
  ritmo,
  className,
}: {
  ritmo: Operacoes2RitmoMesCorrente
  className?: string
}) {
  const restantes = Math.max(0, ritmo.du_total_mes - ritmo.du_corridos)
  return (
    <Card className={cx("flex flex-col gap-3 p-5", className)}>
      <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
        Projeção fim do mês
      </p>
      <p className="text-[24px] font-semibold leading-none tabular-nums text-gray-900 dark:text-gray-50">
        {fmtBRLFull.format(ritmo.projecao_fim_mes)}
      </p>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
        <dt className="text-gray-500 dark:text-gray-400">VOP atual</dt>
        <dd className="text-right tabular-nums text-gray-900 dark:text-gray-50">
          {fmtBRL.format(ritmo.vop_acumulado)}
        </dd>
        <dt className="text-gray-500 dark:text-gray-400">DUs corridos</dt>
        <dd className="text-right tabular-nums text-gray-900 dark:text-gray-50">
          {ritmo.du_corridos} / {ritmo.du_total_mes}
        </dd>
        <dt className="text-gray-500 dark:text-gray-400">DUs restantes</dt>
        <dd className="text-right tabular-nums text-gray-900 dark:text-gray-50">
          {restantes}
        </dd>
      </dl>
    </Card>
  )
}

function Linha2Pace({
  pace,
  className,
}: {
  pace: Operacoes2PaceDiario | null
  className?: string
}) {
  return (
    <Card className={cx("flex flex-col gap-3 p-5", className)}>
      <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
        Pace diário
      </p>
      {pace ? (
        <>
          <p className="text-[24px] font-semibold leading-none tabular-nums text-gray-900 dark:text-gray-50">
            {fmtBRL.format(pace.vop_du_corrente)}
          </p>
          <DeltaTextRow value={pace.delta_pct} label="vs mês anterior" />
          <p className="text-[11px] text-gray-500 dark:text-gray-400">
            Mês anterior:{" "}
            <strong className="tabular-nums text-gray-900 dark:text-gray-50">
              {fmtBRL.format(pace.vop_du_anterior)}
            </strong>{" "}
            / DU
          </p>
        </>
      ) : (
        <p className="text-[11px] text-gray-500 dark:text-gray-400">—</p>
      )}
    </Card>
  )
}

// ─── Linha 3 (Padrao A) — 4 KPIs secundarios ──────────────────────────────

function Linha3Kpis({ kpis }: { kpis: Operacoes2KpisSecundariosVolume }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <KpiSecundarioCard
        label="Nº de operações"
        kpi={kpis.n_operacoes}
        format={(v) => fmtInt.format(v)}
      />
      <KpiSecundarioCard
        label="Ticket médio (op.)"
        kpi={kpis.ticket_op}
        format={(v) => fmtBRLFull.format(v)}
      />
      <KpiSecundarioCard
        label="Ticket médio (título)"
        kpi={kpis.ticket_titulo}
        format={(v) => fmtBRLFull.format(v)}
      />
      <KpiSecundarioCard
        label="VOP por DU médio"
        kpi={kpis.vop_du_medio}
        format={(v) => fmtBRL.format(v)}
        unavailableHint="Depende de wh_dim_dia_util"
      />
    </div>
  )
}

function KpiSecundarioCard({
  label,
  kpi,
  format,
  unavailableHint,
}: {
  label: string
  kpi: Operacoes2KpiSecundario | null
  format: (v: number) => string
  unavailableHint?: string
}) {
  return (
    <Card className="flex flex-col gap-2 p-5">
      <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
        {label}
      </p>
      {kpi ? (
        <>
          <p className="text-[22px] font-semibold leading-none tabular-nums text-gray-900 dark:text-gray-50">
            {format(kpi.valor)}
          </p>
          <DeltaTextRow value={kpi.delta_pct} label="MoM" />
        </>
      ) : (
        <p className="text-[11px] italic text-gray-400 dark:text-gray-600">
          {unavailableHint ?? "—"}
        </p>
      )}
    </Card>
  )
}

function DeltaTextRow({
  value,
  label,
}: {
  value: number | null
  label: string
}) {
  if (value == null) {
    return (
      <p className="text-[11px] text-gray-400 dark:text-gray-600">— · {label}</p>
    )
  }
  const isUp = value >= 0
  const colorClass = isUp
    ? "text-emerald-600 dark:text-emerald-400"
    : "text-red-600 dark:text-red-400"
  return (
    <p className="text-[11px] text-gray-500 dark:text-gray-400">
      <span className={cx("font-medium tabular-nums", colorClass)}>
        {isUp ? "+" : ""}
        {fmtPct1(value)}
      </span>{" "}
      · {label}
    </p>
  )
}

// ─── QuebraCard — Lista vitrine de VOP por Produto ────────────────────────
//
// Lista estilizada (grid 5 cols) num <Card>, NAO uma tabela. CLAUDE.md §6
// proibe Tremor <Table> cru em pagina; e este caso (vitrine top-N estatica
// numa coluna de 25%) nao se encaixa em nenhum dos 4 buckets canonicos
// (DataTableShell / DataTable / CompactSeriesTable / hierarquica) — todos
// trazem peso de UI (filtros, sort, virtualizacao) excessivo. Optamos por
// lista de divs alinhados por grid: respeita §6 e mantem alinhamento
// vertical das colunas como uma tabela faria.
//
// Colunas: # | Produto | %Período | %Mês | Δpp
//   - %Período = r.pct (participacao % do produto no periodo do filtro)
//   - %Mês     = r.pct_mes_corrente (participacao % no mes corrente)
//   - Δpp      = r.pct_mes_corrente - r.pct (variacao em pontos percentuais)
//
// Decisao 2026-05-04: exibir % (e nao volume R$ absoluto). Quando o fundo
// cresce em VOP, todas as categorias tendem a crescer em valor — a leitura
// de VOLUME nao revela mudanca de mix. Ja a participacao % e a metrica que
// expoe ganho/perda de share entre produtos.
//
// Sinalizacao do Δpp por sinal: > +1pp = crescendo (emerald), < -1pp =
// reduzindo (red), entre = estavel (gray). Threshold de 1pp escolhido para
// nao reagir a flutuacao trivial de mes.

const PARTICIPACAO_THRESHOLD_PP = 1.0

const ROW_GRID =
  "grid grid-cols-[20px_minmax(0,1fr)_auto_auto_auto] items-center gap-x-3"

function QuebraCard({
  title,
  rows,
  topN,
}: {
  title: string
  rows: Operacoes2QuebraDimensaoLinha[]
  topN: number
}) {
  const sorted = React.useMemo(
    () => [...rows].sort((a, b) => b.pct - a.pct).slice(0, topN),
    [rows, topN],
  )

  if (sorted.length === 0) {
    return (
      <Card className="flex flex-col p-0">
        <div className={cardTokens.header}>
          <h3 className={cardTokens.headerTitle}>{title}</h3>
        </div>
        <div className={cardTokens.body}>
          <p className="py-6 text-center text-xs text-gray-400 dark:text-gray-600">
            Sem dados no período.
          </p>
        </div>
      </Card>
    )
  }

  return (
    <Card className="flex flex-col p-0">
      <div className={cardTokens.header}>
        <h3 className={cardTokens.headerTitle}>{title}</h3>
        <p className={cx(cardTokens.headerSubtitle, "mt-0.5")}>
          Top {sorted.length} · participação % e variação (pp)
        </p>
      </div>

      <div className={cx(cardTokens.body, "flex flex-col gap-2")}>
        {/* Header row */}
        <div
          className={cx(
            ROW_GRID,
            "border-b border-gray-100 pb-1.5 text-gray-500 dark:border-gray-900 dark:text-gray-400",
            tableTokens.header,
          )}
        >
          <span className="text-right">#</span>
          <span>Produto</span>
          <span className="text-right">%Per.</span>
          <span className="text-right">%Mês</span>
          <span className="text-right">Δpp</span>
        </div>

        {/* Data rows */}
        <div className="flex flex-col gap-1">
          {sorted.map((r, i) => {
            const deltaPp = r.pct_mes_corrente - r.pct
            const isUp = deltaPp > PARTICIPACAO_THRESHOLD_PP
            const isDown = deltaPp < -PARTICIPACAO_THRESHOLD_PP
            const SignalIcon = isUp
              ? RiArrowUpLine
              : isDown
                ? RiArrowDownLine
                : RiSubtractLine
            const signalClass = isUp
              ? "text-emerald-600 dark:text-emerald-400"
              : isDown
                ? "text-red-600 dark:text-red-400"
                : "text-gray-400 dark:text-gray-600"
            const deltaTxt = `${deltaPp >= 0 ? "+" : ""}${deltaPp.toFixed(1).replace(".", ",")}`
            const tooltip = `Participação ${fmtPct1(r.pct)} → ${fmtPct1(r.pct_mes_corrente)} (${deltaTxt} pp)`
            return (
              <div key={r.categoria} className={cx(ROW_GRID, "py-1")}>
                <span
                  className={cx(tableTokens.cellNumberSecondary, "text-right")}
                >
                  {i + 1}
                </span>
                <span className={cx(tableTokens.cellText, "truncate")}>
                  {r.categoria}
                </span>
                <span className={cx(tableTokens.cellNumber, "text-right")}>
                  {fmtPct1(r.pct)}
                </span>
                <span className={cx(tableTokens.cellNumber, "text-right")}>
                  {fmtPct1(r.pct_mes_corrente)}
                </span>
                <span
                  className={cx(
                    "inline-flex items-center justify-end gap-0.5 tabular-nums text-xs",
                    signalClass,
                  )}
                  title={tooltip}
                >
                  <SignalIcon className="size-3.5" aria-hidden="true" />
                  <span aria-label={tooltip}>{deltaTxt}</span>
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </Card>
  )
}

// ─── Linha 5 (Padrao C) — Heatmap dow x semana + Por dia da semana ────────

function Linha5Sazonalidade({
  heatmap,
  porDia,
}: {
  heatmap: Operacoes2HeatmapPonto[]
  porDia: Operacoes2DiaSemanaResumo[]
}) {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <HeatmapDowSemana points={heatmap} />
      <PorDiaSemana rows={porDia} />
    </div>
  )
}

function HeatmapDowSemana({ points }: { points: Operacoes2HeatmapPonto[] }) {
  const option: EChartsOption = React.useMemo(() => {
    const dows = ["Seg", "Ter", "Qua", "Qui", "Sex"]
    const semanas = ["S1", "S2", "S3", "S4", "S5"]
    const data = points.map((p) => [p.dow - 1, p.semana_do_mes - 1, p.vop_medio])
    const max = Math.max(0, ...points.map((p) => p.vop_medio))
    return {
      tooltip: {
        position: "top",
        formatter: (params: unknown) => {
          const p = params as { value: number[] }
          if (!p?.value) return ""
          const [dowIdx, semanaIdx, valor] = p.value
          return `${dows[dowIdx]} · ${semanas[semanaIdx]}: ${fmtBRL.format(valor)}`
        },
      },
      grid: { top: 8, right: 16, bottom: 28, left: 32 },
      xAxis: {
        type: "category",
        data: dows,
        splitArea: { show: true },
        axisTick: { show: false },
      },
      yAxis: {
        type: "category",
        data: semanas,
        splitArea: { show: true },
      },
      visualMap: {
        min: 0,
        max: max || 1,
        show: false,
        inRange: {
          color: ["#EFF6FF", "#3B82F6", "#1E3A8A"],
        },
      },
      series: [
        {
          name: "VOP médio",
          type: "heatmap",
          data,
          label: { show: false },
        },
      ],
    }
  }, [points])

  return (
    <EChartsCard
      title="Sazonalidade · Dia da semana × Semana do mês"
      caption="VOP médio por célula no período filtrado"
      option={option}
      height={240}
    />
  )
}

function PorDiaSemana({ rows }: { rows: Operacoes2DiaSemanaResumo[] }) {
  const option: EChartsOption = React.useMemo(() => {
    const labels = rows.map((r) => r.nome.slice(0, 3))
    return {
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        formatter: (params: unknown) => {
          const arr = params as Array<{ dataIndex: number }>
          if (!Array.isArray(arr) || arr.length === 0) return ""
          const r = rows[arr[0].dataIndex]
          if (!r) return ""
          return [
            `<strong>${r.nome}</strong>`,
            `VOP médio: ${fmtBRLFull.format(r.vop_medio)}`,
            `Operações médias: ${r.n_ops_medio.toFixed(1)}`,
            `% da semana útil: ${fmtPct1(r.pct_total_semana)}`,
          ].join("<br/>")
        },
      },
      grid: { top: 8, right: 16, bottom: 28, left: 56 },
      xAxis: { type: "category", data: labels, axisTick: { show: false } },
      yAxis: {
        type: "value",
        axisLabel: { formatter: (v: number) => fmtBRL.format(v) },
      },
      series: [
        {
          type: "bar",
          barMaxWidth: 36,
          data: rows.map((r) => ({
            value: r.vop_medio,
            itemStyle: { color: "#2A4D7A", borderRadius: [3, 3, 0, 0] },
          })),
        },
      ],
    }
  }, [rows])

  return (
    <EChartsCard
      title="VOP médio por dia da semana"
      caption="Apenas dias úteis (Segunda–Sexta)"
      option={option}
      height={240}
    />
  )
}

// ─── EChartsCardInline (sem moldura — usado dentro de outras cards) ───────

function EChartsCardInline({
  option,
  height,
}: {
  option: EChartsOption
  height: number
}) {
  return <EChartsCard option={option} height={height} className="border-0 p-0" />
}
