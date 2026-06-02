// src/app/(app)/bi/panorama/page.tsx
//
// BI · Panorama — Observatorio FIDC (analise ampla do segmento CVM).
//
// Pattern: DashboardBiPadrao (composicao direta, estilo /bi/operacoes4).
// Fonte: Informe Mensal CVM via postgres_fdw (cvm_remote.*) — dado PUBLICO,
// sem tenant (CLAUDE.md §13.1). Backend: /bi/panorama/visao-geral.
//
// Fase 1 (vertical slice): aba Visao Geral — 5 KPIs macro + evolucao do PL
// (28m) + split por condominio + distribuicao de tamanho. Filtros globais
// (condominio, porte, tipo de carteira) aplicados a 100% dos agregados
// (§7.2 — helper unico `_filter_where` no backend).
//
// Follow-ups conscientes (proximas fases):
//   - Filtro de Competencia + Administrador (precisam endpoint de catalogo).
//   - URL-sync dos filtros (nuqs) — hoje estado local.
//   - Abas Players / Risco & Liquidez / Lastro & Prazo / Concentracao.
//   - Padronizado x NP + situacao cadastral (gated no ETL cad_fi_classe_fidc).

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { RiCheckLine, RiRefreshLine, RiStackLine } from "@remixicon/react"
import { toast } from "sonner"
import type { EChartsOption } from "echarts"

import { cx } from "@/lib/utils"
import { Button } from "@/components/tremor/Button"
import { Card } from "@/components/tremor/Card"

import { PageHeader } from "@/design-system/components/PageHeader"
import { DashboardHeaderActions } from "@/design-system/components/DashboardHeaderActions"
import { FilterChip } from "@/design-system/components/FilterBar"
import { KpiStrip, KpiCard } from "@/design-system/components/KpiStrip"
import { EChartsCard } from "@/design-system/components/EChartsCard"
import {
  AIPanel,
  useAIPanel,
  type AIInsight,
} from "@/design-system/components/AIPanel"
import { AIQuotaIndicator } from "@/design-system/components/AIQuotaIndicator"
import { cardTokens } from "@/design-system/tokens/card"

import { ProvenanceFooter } from "@/components/bi/ProvenanceFooter"
import { useScrollShadow } from "@/lib/hooks/use-scroll-shadow"
import { useAIChat, useAIInsights, useAIQuota } from "@/lib/hooks/ai"
import { biPanorama } from "@/lib/api-client"
import type {
  PanoramaCondom,
  PanoramaFaixaPl,
  PanoramaFilters,
  PanoramaTipoCarteira,
  PanoramaVisaoGeralData,
} from "@/lib/api-client"

// ─── Opcoes de filtro (estruturadas — campos CVM) ──────────────────────────

const CONDOM_OPTS: ReadonlyArray<{ value: PanoramaCondom; label: string }> = [
  { value: "aberto", label: "Aberto" },
  { value: "fechado", label: "Fechado" },
]
const FAIXA_PL_OPTS: ReadonlyArray<{ value: PanoramaFaixaPl; label: string }> = [
  { value: "lt50", label: "< R$ 50 mi" },
  { value: "50_200", label: "R$ 50–200 mi" },
  { value: "200_500", label: "R$ 200–500 mi" },
  { value: "500_1000", label: "R$ 500 mi–1 bi" },
  { value: "gt1000", label: "> R$ 1 bi" },
]
const TIPO_CARTEIRA_OPTS: ReadonlyArray<{
  value: PanoramaTipoCarteira
  label: string
}> = [
  { value: "propria", label: "Carteira própria" },
  { value: "cotas", label: "Fundo de cotas" },
]

export default function BiPanoramaPage() {
  const [filters, setFilters] = React.useState<PanoramaFilters>({})

  const q = useQuery({
    queryKey: ["bi", "panorama", "visao-geral", filters],
    queryFn: () => biPanorama.visaoGeral(filters),
  })
  const data = q.data?.data

  // AI (mesmo padrao das demais paginas BI).
  const quotaQ = useAIQuota()
  const [conversationId, setConversationId] = React.useState<string | null>(null)
  const insightsQ = useAIInsights({ page: "/bi/panorama", period: "all" })
  const { send } = useAIChat({
    conversationId,
    onConversationCreated: setConversationId,
  })
  const insights: AIInsight[] = React.useMemo(
    () => (insightsQ.data?.insights ?? []).map((i) => ({ text: i.text })),
    [insightsQ.data],
  )
  const ai = useAIPanel()
  const aiContext = React.useMemo(
    () => ({
      page: "BI · Panorama do mercado FIDC (CVM)",
      period: data?.competencia ?? "última competência",
      filters: activeFilterSummary(filters),
    }),
    [data?.competencia, filters],
  )

  const [scrollRef, scrolled] = useScrollShadow<HTMLDivElement>()
  const handleShare = React.useCallback(
    () => toast.info("Compartilhar — em breve"),
    [],
  )
  const handleExport = React.useCallback(
    () => toast.info("Exportar — em breve"),
    [],
  )

  const setFilter = React.useCallback(
    (patch: Partial<PanoramaFilters>) =>
      setFilters((prev) => ({ ...prev, ...patch })),
    [],
  )
  const resetFilters = React.useCallback(() => setFilters({}), [])
  const hasFiltros =
    !!filters.condom || !!filters.faixaPl || !!filters.tipoCarteira

  return (
    <div className="flex h-[calc(100vh-3rem)] overflow-hidden">
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Title row (Z1) */}
        <div className="shrink-0 bg-white px-6 pt-3.5 pb-3 dark:bg-gray-950">
          <PageHeader
            title="BI · Panorama do mercado FIDC"
            info="Analise ampla do segmento FIDC a partir do Informe Mensal CVM (dado publico via postgres_fdw). Todos os agregados respeitam os filtros globais. Padronizado x NP e situacao cadastral entram quando o cadastro CVM for ingerido."
            subtitle={
              data
                ? `Competência ${formatCompetencia(data.competencia)} · ${fmtInt.format(
                    data.kpis.n_fidc,
                  )} fundos com PL positivo`
                : "Informe Mensal CVM · dados públicos"
            }
            actions={
              <div className="flex items-center gap-2">
                <AIQuotaIndicator quota={quotaQ.data} loading={quotaQ.isLoading} />
                <DashboardHeaderActions
                  ai={{ open: ai.open, onToggle: ai.toggle }}
                  onShare={handleShare}
                  onExport={handleExport}
                />
              </div>
            }
          />
        </div>

        {/* Toolbar de filtros (Z3) */}
        <div
          className={cx(
            "shrink-0 border-b border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
            scrolled && "scroll-shadow",
          )}
        >
          <div className="flex h-[52px] items-center gap-2 px-6">
            <FilterChip
              label="Condomínio"
              value={
                CONDOM_OPTS.find((o) => o.value === filters.condom)?.label ??
                "Todos"
              }
              active={!!filters.condom}
              icon={RiStackLine}
            >
              <SingleSelectList
                options={CONDOM_OPTS}
                selected={filters.condom ?? null}
                onSelect={(v) => setFilter({ condom: v })}
              />
            </FilterChip>

            <FilterChip
              label="Porte"
              value={
                FAIXA_PL_OPTS.find((o) => o.value === filters.faixaPl)?.label ??
                "Todos"
              }
              active={!!filters.faixaPl}
            >
              <SingleSelectList
                options={FAIXA_PL_OPTS}
                selected={filters.faixaPl ?? null}
                onSelect={(v) => setFilter({ faixaPl: v })}
              />
            </FilterChip>

            <FilterChip
              label="Carteira"
              value={
                TIPO_CARTEIRA_OPTS.find((o) => o.value === filters.tipoCarteira)
                  ?.label ?? "Todas"
              }
              active={!!filters.tipoCarteira}
            >
              <SingleSelectList
                options={TIPO_CARTEIRA_OPTS}
                selected={filters.tipoCarteira ?? null}
                onSelect={(v) => setFilter({ tipoCarteira: v })}
              />
            </FilterChip>

            <Button
              variant="ghost"
              onClick={resetFilters}
              disabled={!hasFiltros}
              className="ml-1"
            >
              <RiRefreshLine className="size-3.5 shrink-0" aria-hidden="true" />
              Resetar
            </Button>

            <span className="ml-auto shrink-0 text-[11px] text-gray-500 dark:text-gray-400">
              {q.isFetching ? "Atualizando…" : "Atualizado"}
            </span>
          </div>
        </div>

        {/* Conteudo (Z4) */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-4">
          <div className="flex flex-col gap-4">
            {q.isLoading && <PaginaSkeleton />}
            {q.isError && (
              <Card className={cx(cardTokens.body, "py-12 text-center")}>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Não foi possível carregar o Panorama do mercado.
                </p>
                <Button variant="ghost" className="mt-2" onClick={() => q.refetch()}>
                  Tentar novamente
                </Button>
              </Card>
            )}
            {data && <VisaoGeral data={data} />}
          </div>
        </div>

        <ProvenanceFooter provenance={q.data?.provenance} />
      </div>

      <AIPanel
        open={ai.open}
        onClose={() => ai.setOpen(false)}
        context={aiContext}
        insights={insights}
        sendMessage={send}
      />
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════
// Aba Visao Geral
// ════════════════════════════════════════════════════════════════════════

function VisaoGeral({ data }: { data: PanoramaVisaoGeralData }) {
  const { kpis, evolucao_pl, por_condominio, distribuicao_tamanho } = data

  // Delta MoM do PL a partir da serie (ultimo vs penultimo ponto).
  const plDeltaPct = React.useMemo(() => {
    if (evolucao_pl.length < 2) return null
    const ult = evolucao_pl[evolucao_pl.length - 1].pl
    const ant = evolucao_pl[evolucao_pl.length - 2].pl
    if (!ant) return null
    return (100 * (ult - ant)) / ant
  }, [evolucao_pl])

  const sparkPl = React.useMemo(
    () => evolucao_pl.map((p) => p.pl),
    [evolucao_pl],
  )

  return (
    <>
      {/* L1 — KpiStrip (5 KPIs macro) */}
      <KpiStrip cols={5}>
        <KpiCard
          label="PL total"
          value={fmtBRLCompact(kpis.pl_total)}
          sub="patrimônio líquido"
          delta={
            plDeltaPct != null
              ? { value: Number(plDeltaPct.toFixed(1)), suffix: "%" }
              : undefined
          }
          deltaSub="vs mês anterior"
          sparkData={sparkPl}
          sparkColor="#3B82F6"
        />
        <KpiCard
          label="Nº FIDCs"
          value={fmtInt.format(kpis.n_fidc)}
          sub="com PL positivo"
        />
        <KpiCard
          label="PL médio"
          value={fmtBRLCompact(kpis.pl_medio)}
          sub="por fundo"
        />
        <KpiCard
          label="Variação de fundos"
          value={signedInt(kpis.delta_fundos)}
          sub="vs competência anterior"
        />
        <KpiCard
          label="Liquidez / PL"
          value={fmtPct(kpis.liquidez_pct)}
          sub="caixa + aplicações"
        />
      </KpiStrip>

      {/* L2 — Hero: evolucao do PL (full width) */}
      <EChartsCard
        title="EVOLUÇÃO DO PL"
        caption="Patrimônio líquido do segmento · série mensal (CVM)"
        option={evolucaoOption(evolucao_pl)}
        height={260}
      />

      {/* L3 — 50/50: condominio (donut) + tamanho (barras) */}
      <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <EChartsCard
          title="PL POR CONDOMÍNIO"
          caption="Aberto vs Fechado"
          option={condominioOption(por_condominio)}
          height={240}
        />
        <EChartsCard
          title="DISTRIBUIÇÃO DE TAMANHO"
          caption="Número de fundos por faixa de PL"
          option={tamanhoOption(distribuicao_tamanho)}
          height={240}
        />
      </section>
    </>
  )
}

// ════════════════════════════════════════════════════════════════════════
// ECharts options
// ════════════════════════════════════════════════════════════════════════

const _MES_ABREV = [
  "jan",
  "fev",
  "mar",
  "abr",
  "mai",
  "jun",
  "jul",
  "ago",
  "set",
  "out",
  "nov",
  "dez",
]

function competenciaShort(yyyymm: string): string {
  const [y, m] = yyyymm.split("-").map(Number)
  if (!y || !m) return yyyymm
  return `${_MES_ABREV[m - 1]}/${String(y).slice(2)}`
}

function evolucaoOption(serie: PanoramaVisaoGeralData["evolucao_pl"]): EChartsOption {
  return {
    grid: { top: 16, right: 16, bottom: 28, left: 56 },
    xAxis: {
      type: "category",
      data: serie.map((p) => competenciaShort(p.competencia)),
      axisTick: { show: false },
      axisLabel: { fontSize: 11, color: "#6B7280" },
    },
    yAxis: {
      type: "value",
      axisLabel: {
        fontSize: 11,
        color: "#6B7280",
        formatter: (v: number) => `${(v / 1e9).toFixed(0)} bi`,
      },
      splitLine: { lineStyle: { color: "rgba(107,114,128,0.15)" } },
    },
    series: [
      {
        type: "line",
        // operacoes4 style: linha + gradiente, sem suavizacao.
        smooth: false,
        symbol: "none",
        data: serie.map((p) => p.pl),
        lineStyle: { color: "#3B82F6", width: 2 },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(59,130,246,0.20)" },
              { offset: 1, color: "rgba(59,130,246,0)" },
            ],
          },
        },
      },
    ],
    tooltip: {
      trigger: "axis",
      valueFormatter: (v) => fmtBRLCompact(Number(v)),
    },
  }
}

function condominioOption(
  itens: PanoramaVisaoGeralData["por_condominio"],
): EChartsOption {
  const colorByName: Record<string, string> = {
    Fechado: "#3B82F6",
    Aberto: "#94A3B8",
  }
  return {
    tooltip: {
      trigger: "item",
      valueFormatter: (v) => fmtBRLCompact(Number(v)),
    },
    legend: { bottom: 0, textStyle: { fontSize: 11, color: "#6B7280" } },
    series: [
      {
        type: "pie",
        radius: ["48%", "72%"],
        center: ["50%", "45%"],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: "#fff", borderWidth: 2 },
        label: { show: true, formatter: "{b}\n{d}%", fontSize: 11 },
        data: itens.map((c) => ({
          name: c.condom,
          value: c.pl,
          itemStyle: { color: colorByName[c.condom] ?? "#CBD5E1" },
        })),
      },
    ],
  }
}

function tamanhoOption(
  buckets: PanoramaVisaoGeralData["distribuicao_tamanho"],
): EChartsOption {
  return {
    grid: { top: 16, right: 16, bottom: 36, left: 44 },
    xAxis: {
      type: "category",
      data: buckets.map((b) => b.faixa),
      axisTick: { show: false },
      axisLabel: { fontSize: 10, color: "#6B7280", interval: 0, rotate: 0 },
    },
    yAxis: {
      type: "value",
      axisLabel: { fontSize: 11, color: "#6B7280" },
      splitLine: { lineStyle: { color: "rgba(107,114,128,0.15)" } },
    },
    series: [
      {
        type: "bar",
        data: buckets.map((b) => b.n_fidc),
        itemStyle: { color: "#3B82F6", borderRadius: [3, 3, 0, 0] },
        barWidth: "55%",
      },
    ],
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (params: unknown) => {
        const p = (params as Array<{ dataIndex: number }>)[0]
        const b = buckets[p.dataIndex]
        if (!b) return ""
        return `${b.faixa}<br/>${fmtInt.format(b.n_fidc)} fundos · ${fmtBRLCompact(b.pl)}`
      },
    },
  }
}

// ════════════════════════════════════════════════════════════════════════
// Formatters + helpers
// ════════════════════════════════════════════════════════════════════════

const fmtInt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 })

const _fmtBRLCompact = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 1,
})
function fmtBRLCompact(v: number): string {
  return _fmtBRLCompact.format(v)
}

function fmtPct(v: number): string {
  return `${v.toFixed(2).replace(".", ",")}%`
}

function signedInt(v: number): string {
  const sign = v > 0 ? "+" : v < 0 ? "−" : ""
  return `${sign}${fmtInt.format(Math.abs(v))}`
}

function formatCompetencia(yyyymm: string): string {
  const [y, m] = yyyymm.split("-").map(Number)
  if (!y || !m) return yyyymm
  return `${_MES_ABREV[m - 1]}/${y}`
}

function activeFilterSummary(f: PanoramaFilters): string {
  const parts: string[] = []
  if (f.condom) parts.push(`Condomínio: ${f.condom}`)
  if (f.faixaPl) {
    const lbl = FAIXA_PL_OPTS.find((o) => o.value === f.faixaPl)?.label
    if (lbl) parts.push(`Porte: ${lbl}`)
  }
  if (f.tipoCarteira) parts.push(`Carteira: ${f.tipoCarteira}`)
  return parts.length > 0 ? parts.join(", ") : "Nenhum"
}

// ─── Single-select popover list (anatomy do menu do FilterChip) ────────────

function SingleSelectList<T extends string>({
  options,
  selected,
  onSelect,
}: {
  options: ReadonlyArray<{ value: T; label: string }>
  selected: T | null
  onSelect: (value: T | null) => void
}) {
  return (
    <div className="py-1">
      <button
        type="button"
        onClick={() => onSelect(null)}
        className={cx(
          "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
          selected === null
            ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
            : "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800",
        )}
      >
        <span className="flex-1 text-left">Todos</span>
        {selected === null && (
          <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />
        )}
      </button>
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onSelect(opt.value)}
          className={cx(
            "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
            selected === opt.value
              ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
              : "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800",
          )}
        >
          <span className="flex-1 text-left">{opt.label}</span>
          {selected === opt.value && (
            <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />
          )}
        </button>
      ))}
    </div>
  )
}

// ─── Skeleton ──────────────────────────────────────────────────────────────

function PaginaSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <div className="h-24 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900" />
      <div className="h-64 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900" />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="h-60 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900" />
        <div className="h-60 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900" />
      </div>
    </div>
  )
}
