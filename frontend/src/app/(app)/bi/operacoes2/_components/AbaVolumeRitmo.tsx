// src/app/(app)/bi/operacoes2/_components/AbaVolumeRitmo.tsx
//
// Aba 1 da pagina /bi/operacoes2 — Volume & Ritmo.
//
// Estrutura segue os 4 padroes de linha (CLAUDE.md §7 — Operacoes2):
//   Linha 1 (Padrao C)  · Hero combo evolucao mensal (6) + Donut VOP por UA (6).
//                          Hero NUNCA full-width — feedback usuario 2026-05-03.
//                          Hero tem seletor LOCAL de UA (filtragem client-side
//                          a partir de `evolucao_12m_por_ua` — sem nova ida ao
//                          backend). Donut UA cabe pq tipicamente FIDCs tem 2-5
//                          UAs (regra "donut com ate 3 fatias" do brief —
//                          `QuebraDonut` agrega top 3 + Outros quando >3).
//   Linha 2 (Padrao B)  · Ritmo do mes corrente + Projecao + Pace
//                          (degraded mode quando wh_dim_dia_util esta vazia)
//   Linha 3 (Padrao A)  · 4 KPIs secundarios de volume
//   Linha 4 (Padrao D)  · VOP por Produto (full-width — barra horizontal).
//                          Produto tem ate 10 categorias — barra ordenada e
//                          a forma certa (regra do brief: >3 fatias → barra).
//   Linha 5 (Padrao C)  · Heatmap dow x semana + Por dia da semana
//
// Strip dual em quebras (Opcao 4 paradigma 2026-05-03):
//   - QuebraCard (Produto na L4): toggle "Periodo | Mes | Ambos" + "Volume |
//     Δ MoM | Δ YoY". "Ambos" sobrepoe as duas barras (clara=periodo /
//     saturada=mes corrente).
//   - QuebraDonut (UA na L1): toggle simplificado "Periodo | Mes" + "Volume".
//     Donut nao representa MoM/YoY bem; "Ambos" precisaria 2 donuts
//     concentricos — preferimos toggle simples e legivel.

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import {
  RiBuilding2Line,
  RiCalendarEventLine,
  RiCheckLine,
} from "@remixicon/react"
import type { EChartsOption } from "echarts"

import { Card } from "@/components/tremor/Card"
import { EChartsCard } from "@/design-system/components/EChartsCard"
import {
  EditorialChartCard,
  buildEditorialAreaOption,
  editorialChartColors,
} from "@/design-system/components/EditorialChartCard"
import { FilterChip } from "@/design-system/components/FilterBar"
import { VizParam } from "@/design-system/components/VizParam"
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
      {/*
        Linha 0 (PROVA DE CONCEITO — paradigma editorial Goldman/FT 2026-05-04):
        chart hero "naked" (sem Card), tipografia editorial, source row pinned
        com watermark Strata. Mesmos dados de `evolucao_12m` que a Linha 1 usa
        — coexistem propositalmente para comparativo lado a lado:
          - Linha 0: editorial layered area (VOP + MM3M) — manchete
          - Linha 1: combo bar+line dentro de Card — widget denso
        Proxima decisao depois da revisao visual: manter o paradigma editorial
        para chart hero (e remover Linha 1 redundante) ou voltar pro padrao
        atual.
      */}
      <Linha0HeroEditorial evolucao={data.evolucao_12m} />
      <Linha1HeroComUa
        evolucao={data.evolucao_12m}
        evolucaoPorUa={data.evolucao_12m_por_ua}
        melhorMes={data.melhor_mes}
        piorMes={data.pior_mes}
        mesVsMedia={data.mes_corrente_vs_media}
        porUa={data.por_ua}
        presetLabel={preset ? PRESET_TO_LABEL[preset] : "Personalizado"}
      />
      <Linha2Ritmo ritmo={data.ritmo} pace={data.pace_diario} />
      <Linha3Kpis kpis={data.kpis_secundarios} />
      <Linha4Produto porProduto={data.por_produto} />
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
      {/* Linha 0 (editorial — sem borda, mais alto) */}
      <div className="px-1 py-2">
        <div className="h-5 w-40 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
        <div className="mt-2 h-7 w-72 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
        <div className="mt-2 h-4 w-[420px] max-w-full animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
        <div className="mt-5 h-[360px] animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
      </div>
      <div className="h-72 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="h-48 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900 lg:col-span-6" />
        <div className="h-48 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900 lg:col-span-3" />
        <div className="h-48 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900 lg:col-span-3" />
      </div>
    </div>
  )
}

// ─── Linha 0 (PROVA DE CONCEITO) — Editorial chart hero ────────────────────
//
// Mesma serie temporal da Linha 1, renderizada com `EditorialChartCard`
// (sem Card, tipografia editorial). VOP e MM 3M como areas layered (nao
// stacked), endLabel inline na ponta direita, source row + watermark.
// Comparar visualmente contra `Linha1HeroComUa` logo abaixo.

function Linha0HeroEditorial({
  evolucao,
}: {
  evolucao: Operacoes2EvolucaoMensalPonto[]
}) {
  const option = React.useMemo(() => {
    const xAxis = evolucao.map((p) => fmtMonthShort(p.periodo))
    const vop = evolucao.map((p) => p.vop)
    const mm3 = evolucao.map((p) => (p.mm_3m == null ? null : p.mm_3m))
    return buildEditorialAreaOption({
      xAxis,
      series: [
        {
          name: "VOP mensal",
          endLabel: "VOP",
          data: vop,
          color: editorialChartColors[0], // slate
        },
        {
          name: "Média móvel 3M",
          endLabel: "MM 3M",
          data: mm3,
          color: editorialChartColors[1], // sky
        },
      ],
      yFormatter: (v) => fmtBRL.format(v),
      tooltipValueFormatter: (v) => (v == null ? "—" : fmtBRLFull.format(v)),
    })
  }, [evolucao])

  const ultimoMes = evolucao.length > 0 ? evolucao[evolucao.length - 1] : null
  const sourceLine = ultimoMes
    ? `Bitfin · última competência ${fmtMonthShort(ultimoMes.periodo)}`
    : "Bitfin"

  return (
    <EditorialChartCard
      eyebrow="BI · Operação"
      title="Evolução do VOP"
      subtitle="Volume mensal de operações confrontado com a média móvel de 3 meses — uma leitura rápida para enxergar se o ritmo recente está acima ou abaixo da tendência."
      source={sourceLine}
      updatedAt="Série apurada mensalmente"
      option={option}
      height={360}
    />
  )
}


// ─── Linha 1 (Padrao C) — Hero combo (6) + VOP por UA (6) ──────────────────

function Linha1HeroComUa({
  evolucao,
  evolucaoPorUa,
  melhorMes,
  piorMes,
  mesVsMedia,
  porUa,
  presetLabel,
}: {
  evolucao: Operacoes2EvolucaoMensalPonto[]
  evolucaoPorUa: Operacoes2EvolucaoPorUaPonto[]
  melhorMes: Operacoes2MesDestaque | null
  piorMes: Operacoes2MesDestaque | null
  mesVsMedia: Operacoes2MesCorrenteVsMedia | null
  porUa: Operacoes2QuebraDimensaoLinha[]
  presetLabel: string
}) {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <HeroEvolucao
        evolucao={evolucao}
        evolucaoPorUa={evolucaoPorUa}
        melhorMes={melhorMes}
        piorMes={piorMes}
        mesVsMedia={mesVsMedia}
        presetLabel={presetLabel}
      />
      <QuebraDonut
        title="VOP por Unidade Administrativa"
        rows={porUa}
      />
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

  // Slice — quando UA selecionada, deriva serie filtrada com mesma estrutura
  // de EvolucaoMensalPonto (n_operacoes/ticket_medio nao temos por UA, ficam 0).
  const slice = React.useMemo<Operacoes2EvolucaoMensalPonto[]>(() => {
    if (selectedUaId === null) return evolucao
    const filtered = evolucaoPorUa.filter((p) => p.ua_id === selectedUaId)
    // Reconstruir como EvolucaoMensalPonto (sem n_ops/ticket por UA por enquanto).
    return filtered.map((p) => ({
      periodo: p.periodo,
      vop: p.vop,
      n_operacoes: 0,
      ticket_medio: 0,
      mm_3m: null,
    }))
  }, [evolucao, evolucaoPorUa, selectedUaId])

  const option: EChartsOption = React.useMemo(() => {
    const labels = slice.map((p) => fmtMonthShort(p.periodo))
    const vops = slice.map((p) => p.vop)
    const mm3 = slice.map((p) => (p.mm_3m == null ? null : p.mm_3m))
    // Marker no ultimo ponto (mes corrente).
    const lastIdx = slice.length - 1
    return {
      grid: { top: 16, right: 12, bottom: 28, left: 64 },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        formatter: (params: unknown) => {
          const arr = params as Array<{
            name: string
            seriesName?: string
            value: number
            dataIndex: number
          }>
          if (!Array.isArray(arr) || arr.length === 0) return ""
          const idx = arr[0].dataIndex
          const p = slice[idx]
          const vop = fmtBRLFull.format(p.vop)
          const ops = fmtInt.format(p.n_operacoes)
          const ticket = fmtBRLFull.format(p.ticket_medio)
          const mm = p.mm_3m == null ? "—" : fmtBRLFull.format(p.mm_3m)
          return [
            `<strong>${arr[0].name}</strong>`,
            `VOP: ${vop}`,
            `MM 3M: ${mm}`,
            `Operações: ${ops}`,
            `Ticket médio: ${ticket}`,
          ].join("<br/>")
        },
      },
      xAxis: {
        type: "category",
        data: labels,
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        axisLabel: {
          formatter: (v: number) => fmtBRL.format(v),
        },
      },
      series: [
        {
          name: "VOP",
          type: "bar",
          barMaxWidth: 32,
          label: {
            show: true,
            position: "top",
            color: "#374151",
            fontSize: 10,
            fontWeight: 500,
            formatter: (p) => fmtBRL.format((p as { value: number }).value),
          },
          data: vops.map((v, i) => ({
            value: v,
            itemStyle: {
              color: i === lastIdx ? "#0EA5E9" : "#2A4D7A",
              borderRadius: [3, 3, 0, 0],
            },
          })),
        },
        {
          name: "MM 3M",
          type: "line",
          smooth: true,
          symbol: "none",
          data: mm3,
          lineStyle: { color: "#9CA3AF", width: 1.5, type: "dashed" },
        },
      ],
    }
  }, [slice])

  const uaSelectedNome =
    selectedUaId === null
      ? "Todas as UAs"
      : (uaOptions.find((u) => u.id === selectedUaId)?.nome ?? "(n/d)")

  return (
    <EChartsCard
      title="Evolução do VOP"
      caption={`${uaSelectedNome} · ${presetLabel} · barra clara = mês corrente · linha tracejada = MM 3M`}
      option={option}
      height={240}
      actions={
        <FilterChip
          label="UA"
          value={uaSelectedNome}
          active={selectedUaId !== null}
          icon={RiBuilding2Line}
        >
          <div className="py-1">
            <UaPickerItem
              label="Todas as UAs"
              selected={selectedUaId === null}
              onSelect={() => setSelectedUaId(null)}
            />
            {uaOptions.map((u) => (
              <UaPickerItem
                key={u.id}
                label={u.nome}
                selected={selectedUaId === u.id}
                onSelect={() => setSelectedUaId(u.id)}
              />
            ))}
          </div>
        </FilterChip>
      }
      footer={
        <div className="flex flex-wrap items-center gap-x-6 gap-y-1 pt-2 text-[11px] text-gray-500 dark:text-gray-400">
          {melhorMes && (
            <span>
              Melhor mês:{" "}
              <strong className="text-gray-900 dark:text-gray-50">
                {fmtMonthShort(melhorMes.periodo)}
              </strong>{" "}
              ({fmtBRL.format(melhorMes.vop)})
            </span>
          )}
          {piorMes && (
            <span>
              Pior mês:{" "}
              <strong className="text-gray-900 dark:text-gray-50">
                {fmtMonthShort(piorMes.periodo)}
              </strong>{" "}
              ({fmtBRL.format(piorMes.vop)})
            </span>
          )}
          {mesVsMedia && (
            <span>
              Mês corrente vs média 12M:{" "}
              <strong
                className={cx(
                  "font-semibold",
                  mesVsMedia.pct >= 0
                    ? "text-emerald-600 dark:text-emerald-400"
                    : "text-red-600 dark:text-red-400",
                )}
              >
                {mesVsMedia.pct >= 0 ? "+" : ""}
                {fmtPct1(mesVsMedia.pct)}
              </strong>
            </span>
          )}
        </div>
      }
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
          radius: ["55%", "80%"],
          center: ["32%", "50%"],
          avoidLabelOverlap: true,
          label: { show: false },
          labelLine: { show: false },
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
      height={260}
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

/**
 * Item do picker de UA dentro do FilterChip do Hero. Espelha o padrao
 * canonico dos popovers de filtro (page.tsx — lista de presets de Periodo).
 * Mantido aqui (vs no DS) porque e composicao especifica do hero.
 */
function UaPickerItem({
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

// ─── Linha 4 (Padrao D) — VOP por Produto (full-width) ────────────────────

const QUEBRA_TOGGLES = ["Volume", "Δ MoM", "Δ YoY"] as const
type QuebraToggle = (typeof QUEBRA_TOGGLES)[number]

// Strip dual (Opcao 4 paradigma 2026-05-03): toggle visualizacao
// "Periodo" (default) | "Mes" (so mes corrente) | "Ambos" (sobreposicao).
const ESCOPO_TOGGLES = ["Período", "Mês", "Ambos"] as const
type EscopoToggle = (typeof ESCOPO_TOGGLES)[number]

function Linha4Produto({
  porProduto,
}: {
  porProduto: Operacoes2QuebraDimensaoLinha[]
}) {
  return (
    <QuebraCard title="VOP por Produto" rows={porProduto} topN={10} />
  )
}

function QuebraCard({
  title,
  rows,
  topN,
}: {
  title: string
  rows: Operacoes2QuebraDimensaoLinha[]
  topN: number
}) {
  const [toggle, setToggle] = React.useState<QuebraToggle>("Volume")
  const [escopo, setEscopo] = React.useState<EscopoToggle>("Período")

  // Ordenacao usa o "Volume" do escopo selecionado (Periodo: vop; Mes: vop_mes_corrente).
  // Quando escopo=Ambos, ordena pelo periodo (referencia historica).
  const vopFor = React.useCallback(
    (r: Operacoes2QuebraDimensaoLinha) =>
      escopo === "Mês" ? r.vop_mes_corrente : r.vop,
    [escopo],
  )

  const sorted = React.useMemo(() => {
    const copy = [...rows]
    if (toggle === "Volume") copy.sort((a, b) => vopFor(b) - vopFor(a))
    else if (toggle === "Δ MoM")
      copy.sort((a, b) => (b.delta_mom_pct ?? -Infinity) - (a.delta_mom_pct ?? -Infinity))
    else
      copy.sort((a, b) => (b.delta_yoy_pct ?? -Infinity) - (a.delta_yoy_pct ?? -Infinity))
    return copy.slice(0, topN)
  }, [rows, toggle, topN, vopFor])

  // Max para a barra — depende do escopo (em Ambos, considera o maior dos 2).
  const maxVop = React.useMemo(() => {
    if (escopo === "Ambos") {
      return Math.max(1, ...sorted.flatMap((r) => [r.vop, r.vop_mes_corrente]))
    }
    return Math.max(1, ...sorted.map((r) => vopFor(r)))
  }, [sorted, escopo, vopFor])

  return (
    <Card className="flex flex-col gap-3 p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
          {title}
        </h3>
        <div className="flex items-center gap-2">
          <VizParam
            options={ESCOPO_TOGGLES}
            value={escopo}
            onChange={setEscopo}
            ariaLabel="Escopo do periodo"
          />
          <VizParam
            options={QUEBRA_TOGGLES}
            value={toggle}
            onChange={setToggle}
            ariaLabel="Metrica exibida"
          />
        </div>
      </div>
      {sorted.length === 0 ? (
        <p className="py-6 text-center text-xs text-gray-400 dark:text-gray-600">
          Sem dados no período.
        </p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {sorted.map((r) => (
            <QuebraRow
              key={r.categoria_id}
              row={r}
              maxVop={maxVop}
              toggle={toggle}
              escopo={escopo}
            />
          ))}
        </ul>
      )}
    </Card>
  )
}

function QuebraRow({
  row,
  maxVop,
  toggle,
  escopo,
}: {
  row: Operacoes2QuebraDimensaoLinha
  maxVop: number
  toggle: QuebraToggle
  escopo: EscopoToggle
}) {
  const vopAtivo = escopo === "Mês" ? row.vop_mes_corrente : row.vop
  const pctAtivo = escopo === "Mês" ? row.pct_mes_corrente : row.pct
  const widthPctPeriodo = Math.max(1, (row.vop / maxVop) * 100)
  const widthPctMes = Math.max(1, (row.vop_mes_corrente / maxVop) * 100)
  const widthPctAtivo = Math.max(1, (vopAtivo / maxVop) * 100)

  const rightLabel = (() => {
    if (toggle === "Δ MoM") {
      return row.delta_mom_pct == null
        ? "—"
        : `${row.delta_mom_pct >= 0 ? "+" : ""}${fmtPct1(row.delta_mom_pct)}`
    }
    if (toggle === "Δ YoY") {
      return row.delta_yoy_pct == null
        ? "—"
        : `${row.delta_yoy_pct >= 0 ? "+" : ""}${fmtPct1(row.delta_yoy_pct)}`
    }
    // Volume — depende do escopo
    if (escopo === "Ambos") {
      return `${fmtBRL.format(row.vop)} · mês ${fmtBRL.format(row.vop_mes_corrente)}`
    }
    return `${fmtBRL.format(vopAtivo)} · ${fmtPct1(pctAtivo)}`
  })()

  const rightColorClass =
    toggle === "Volume"
      ? "text-gray-600 dark:text-gray-400"
      : (toggle === "Δ MoM" ? row.delta_mom_pct : row.delta_yoy_pct) == null
        ? "text-gray-400 dark:text-gray-600"
        : ((toggle === "Δ MoM" ? row.delta_mom_pct : row.delta_yoy_pct) ?? 0) >= 0
          ? "text-emerald-600 dark:text-emerald-400"
          : "text-red-600 dark:text-red-400"

  return (
    <li className="grid grid-cols-[1fr_auto] items-center gap-2 text-[12px]">
      <div className="flex items-center gap-2">
        <span
          className="truncate text-gray-900 dark:text-gray-50"
          title={row.categoria}
        >
          {row.categoria}
        </span>
        <div className="relative h-1 flex-1 rounded-full bg-gray-100 dark:bg-gray-800">
          {escopo === "Ambos" ? (
            <>
              {/* Periodo (claro) */}
              <div
                className="absolute inset-y-0 left-0 rounded-full bg-blue-200 dark:bg-blue-500/30"
                style={{ width: `${widthPctPeriodo}%` }}
                aria-label={`Período: ${fmtBRL.format(row.vop)}`}
              />
              {/* Mes corrente (saturado, sobre) */}
              <div
                className="absolute inset-y-0 left-0 rounded-full bg-blue-600 dark:bg-blue-400"
                style={{ width: `${widthPctMes}%` }}
                aria-label={`Mês: ${fmtBRL.format(row.vop_mes_corrente)}`}
              />
            </>
          ) : (
            <div
              className="absolute inset-y-0 left-0 rounded-full bg-blue-500"
              style={{ width: `${widthPctAtivo}%` }}
              aria-hidden="true"
            />
          )}
        </div>
      </div>
      <span
        className={cx("shrink-0 text-right tabular-nums font-medium", rightColorClass)}
      >
        {rightLabel}
      </span>
    </li>
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
