// src/app/(app)/controladoria/receitas/page.tsx
//
// Receitas — 3 metodos de apuracao (Caixa | Competencia | Acruo) sobre o
// catalogo de receitas caixa-fiel (wh_receita_caixa / wh_receita_operacional
// / wh_receita_acruo_dia).
//
// ANATOMIA = /bi/operacoes4 (regua canonica de BI, exigencia 2026-06-12):
//   - root flex h-[calc(100vh-3rem)] overflow-hidden + scroll INTERNO
//   - title row (px-6 pt-3.5 pb-3) com PageHeader + AIQuota + HeaderActions
//   - Z2 TabNavigation (L3) em linha propria
//   - Z3 toolbar flat h-[52px] com FilterChips (popover) + Resetar +
//     status "Atualizado" — scroll-shadow quando rola
//   - InsightStrip + conteudo em flex-col gap-4 + ProvenanceFooter
//   - AIPanel in-layout (mesmo wiring de IA da operacoes4)
//
// Esqueleto funcional aprovado (2026-06-12): SegmentSwitch de METODO como
// lente global (§7.2), KpiStrip, hero mensal por familia, composicao por
// natureza, PONTE dos 3 metodos (§14.6), DataTable familia/stream com drill
// de titulos (?selected via nuqs), aba Conferencias (desconto de mora).

"use client"

import * as React from "react"
import { useQueryState } from "nuqs"
import {
  RiCalendarLine,
  RiCheckLine,
  RiRefreshLine,
} from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"
import type { EChartsOption } from "echarts"

import { cx } from "@/lib/utils"
import {
  TabNavigation,
  TabNavigationLink,
} from "@/components/tremor/TabNavigation"
import { Button } from "@/components/tremor/Button"
import { Card } from "@/components/tremor/Card"

import { PageHeader } from "@/design-system/components/PageHeader"
import { DashboardHeaderActions } from "@/design-system/components/DashboardHeaderActions"
import { ProvenanceFooter, type ProvenanceSource } from "@/design-system/components/ProvenanceFooter"
import { SegmentSwitch } from "@/design-system/components/SegmentSwitch"
import { KpiCard, KpiStrip } from "@/design-system/components/KpiStrip"
import { EChartsCard } from "@/design-system/components/EChartsCard"
import { FilterChip } from "@/design-system/components/FilterBar"
import { InsightStrip } from "@/design-system/components/InsightStrip"
import { DataTable } from "@/design-system/components/DataTable"
import { DrillDownSheet } from "@/design-system/components/DrillDownSheet"
import {
  AIPanel,
  useAIPanel,
  type AIInsight,
} from "@/design-system/components/AIPanel"
import { AIQuotaIndicator } from "@/design-system/components/AIQuotaIndicator"
import { cardTokens } from "@/design-system/tokens/card"
import { tableTokens } from "@/design-system/tokens/table"
import { useScrollShadow } from "@/lib/hooks/use-scroll-shadow"
import { useUAs } from "@/lib/hooks/cadastros"
import { useAIChat, useAIInsights, useAIQuota } from "@/lib/hooks/ai"
import {
  useReceitasCedentes,
  useReceitasConferencias,
  useReceitasDetalhe,
  useReceitasResumo,
  useReceitasTitulos,
} from "@/lib/hooks/controladoria"
import type {
  DescontoMoraCedente,
  ReceitaCedenteLinha,
  ReceitaDetalheLinha,
  ReceitasFilters,
  ReceitasMetodo,
  ReceitaTituloLinha,
} from "@/lib/api-client"

// ───────────────────────────────────────────────────────────────────────────
// Vocabulario de exibicao
// ───────────────────────────────────────────────────────────────────────────

const METODOS: { value: ReceitasMetodo; label: string }[] = [
  { value: "caixa",       label: "Caixa" },
  { value: "competencia", label: "Competência" },
  { value: "acruo",       label: "Acruo" },
]

const METODO_DESC: Record<ReceitasMetodo, string> = {
  caixa:       "deságio reconhecido na liquidação do título",
  competencia: "deságio integral na efetivação da operação",
  acruo:       "curva diária composta (D+1, dias úteis)",
}

const FAMILIA_LABEL: Record<string, string> = {
  operacao:         "Operação (deságio + tarifas)",
  mora_liquidacao:  "Mora na liquidação",
  mora_prorrogacao: "Prorrogação",
  mora_cartorio:    "Cartório",
  mora_acerto:      "Acertos",
  recompra:         "Recompra (encargos)",
  tarifa_servico:   "Tarifas de serviço",
  repasse_custo:    "Repasse de custos",
  financeira:       "Financeira",
}

// Cores fixas por familia (ECharts canvas — hex permitido, CLAUDE.md §4).
const FAMILIA_COR: Record<string, string> = {
  operacao:         "#64748B", // slate (1a serie A7)
  recompra:         "#0EA5E9", // sky
  mora_liquidacao:  "#14B8A6", // teal
  mora_prorrogacao: "#10B981", // emerald
  tarifa_servico:   "#F59E0B", // amber
  repasse_custo:    "#F43F5E", // rose
  mora_cartorio:    "#8B5CF6", // violet
  mora_acerto:      "#6366F1", // indigo
  financeira:       "#A8A29E",
}

const NATUREZA_LABEL: Record<string, string> = {
  DESAGIO:           "Deságio",
  AD_VALOREM:        "Ad valorem",
  TARIFA:            "Tarifas",
  JUROS_MORA:        "Juros de mora",
  MULTA_MORA:        "Multa",
  ENCARGO_NEGOCIADO: "Encargo negociado",
  REPASSE_CUSTO:     "Repasse de custos",
  FINANCEIRA:        "Financeira",
  NAO_CLASSIFICADO:  "Não classificado",
}

const STREAM_LABEL: Record<string, string> = {
  desagio_operacao:           "Deságio",
  tarifa_operacao:            "Tarifas de operação",
  ad_valorem:                 "Ad valorem",
  mora_liquidacao_juros:      "Juros (régua)",
  mora_liquidacao_multa:      "Multa (régua)",
  mora_liquidacao_negociado:  "Encargo negociado",
  prorrogacao_juros:          "Juros de prorrogação (028)",
  prorrogacao_multa:          "Multa de prorrogação (151)",
  cartorio_juros:             "Juros de cartório (024)",
  diferenca_pagamento:        "Diferença no pagamento (025)",
  recompra_juros:             "Juros de recompra",
  recompra_multa:             "Multa de recompra",
  recompra_desagio:           "Deságio de recompra",
  tarifa_servico:             "Tarifas de serviço",
  repasse_custo:              "Repasses",
  financeira_correcao_diaria: "Correção diária",
  liquidacao:        "Liquidação",
  baixa:             "Baixa",
  recompra:          "Recompra",
  reoperacao:        "Reoperação",
  acruo:             "Carrego diário",
  acruo_antecipacao: "Antecipação",
}

const PERIODOS = [
  { value: "3m",  label: "Últimos 3 meses" },
  { value: "6m",  label: "Últimos 6 meses" },
  { value: "12m", label: "Últimos 12 meses" },
  { value: "ano", label: "Este ano" },
] as const
type PeriodoKey = (typeof PERIODOS)[number]["value"]
const PERIODO_LABEL: Record<PeriodoKey, string> = Object.fromEntries(
  PERIODOS.map((p) => [p.value, p.label]),
) as Record<PeriodoKey, string>

const TABS = [
  { key: "visao",        label: "Visão geral" },
  { key: "familia",      label: "Por família" },
  { key: "cedente",      label: "Por cedente" },
  { key: "conferencias", label: "Conferências" },
] as const
type TabKey = (typeof TABS)[number]["key"]

// ───────────────────────────────────────────────────────────────────────────
// Helpers de formatacao (pt-BR)
// ───────────────────────────────────────────────────────────────────────────

const fmtBRL = (v: number) =>
  v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })

const fmtBRL0 = (v: number) =>
  v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 })

const fmtCompacto = (v: number) =>
  v >= 1_000_000 ? `${(v / 1_000_000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mi`
  : v >= 1_000   ? `${(v / 1_000).toLocaleString("pt-BR", { maximumFractionDigits: 0 })} mil`
  : v.toLocaleString("pt-BR", { maximumFractionDigits: 0 })

const MESES_CURTOS = ["jan", "fev", "mar", "abr", "mai", "jun",
                      "jul", "ago", "set", "out", "nov", "dez"]

function fmtCompetencia(iso: string): string {
  const [y, m] = iso.split("-")
  return `${MESES_CURTOS[Number(m) - 1]}/${y.slice(2)}`
}

function primeiraDoMes(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`
}

function janelaDoPeriodo(p: PeriodoKey): { de: string; ate: string } {
  const hoje = new Date()
  const ate = primeiraDoMes(hoje)
  if (p === "ano") return { de: `${hoje.getFullYear()}-01-01`, ate }
  const meses = p === "3m" ? 2 : p === "6m" ? 5 : 11
  const de = new Date(hoje.getFullYear(), hoje.getMonth() - meses, 1)
  return { de: primeiraDoMes(de), ate }
}

// ───────────────────────────────────────────────────────────────────────────
// Page
// ───────────────────────────────────────────────────────────────────────────

export default function ReceitasPage() {
  const [metodo, setMetodo] = useQueryState("metodo", {
    defaultValue: "caixa" as ReceitasMetodo,
    parse: (v): ReceitasMetodo =>
      v === "competencia" || v === "acruo" ? v : "caixa",
  })
  const [tab, setTab] = useQueryState("tab", {
    defaultValue: "visao" as TabKey,
    parse: (v): TabKey =>
      (TABS.some((t) => t.key === v) ? (v as TabKey) : "visao"),
  })
  const [periodo, setPeriodo] = useQueryState("periodo", {
    defaultValue: "6m" as PeriodoKey,
    parse: (v): PeriodoKey =>
      (PERIODOS.some((p) => p.value === v) ? (v as PeriodoKey) : "6m"),
  })
  const [selected, setSelected] = useQueryState("selected")

  const fundosQuery = useUAs({ ativa: true })
  const [fundoUuid, setFundoUuid] = React.useState<string>("")
  const fundoSelecionado = fundosQuery.data?.find((ua) => ua.id === fundoUuid)
  const fundoBitfinId = fundoSelecionado?.bitfin_ua_id ?? undefined
  const uaOptions = (fundosQuery.data ?? []).filter(
    (ua) => ua.bitfin_ua_id != null,
  )

  const { de, ate } = React.useMemo(() => janelaDoPeriodo(periodo), [periodo])

  const filters: ReceitasFilters = React.useMemo(
    () => ({ metodo, competenciaDe: de, competenciaAte: ate, fundoId: fundoBitfinId }),
    [metodo, de, ate, fundoBitfinId],
  )

  const resumoQ = useReceitasResumo(tab === "visao" ? filters : null)
  const detalheQ = useReceitasDetalhe(
    tab === "visao" || tab === "familia" ? filters : null,
  )
  const cedentesQ = useReceitasCedentes(tab === "cedente" ? filters : null)
  const conferenciasQ = useReceitasConferencias(
    tab === "conferencias"
      ? { competenciaDe: de, competenciaAte: ate, fundoId: fundoBitfinId }
      : null,
  )

  const [selFamilia, selStream] = (selected ?? "").split("|")
  const titulosQ = useReceitasTitulos(
    selected ? { ...filters, familia: selFamilia, stream: selStream } : null,
  )

  // AI hooks (mesmo padrao de operacoes4).
  const quotaQ = useAIQuota()
  const [conversationId, setConversationId] = React.useState<string | null>(null)
  const insightsQ = useAIInsights({
    page: "/controladoria/receitas",
    period: periodo,
  })
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
      page: "Controladoria · Receitas",
      period: PERIODO_LABEL[periodo],
      filters:
        [
          `Método: ${METODOS.find((m) => m.value === metodo)?.label}`,
          fundoSelecionado ? `UA: ${fundoSelecionado.nome}` : null,
        ]
          .filter(Boolean)
          .join(", ") || "Nenhum",
    }),
    [periodo, metodo, fundoSelecionado],
  )
  const insightStripItems = React.useMemo(
    () => insights.map((ins, idx) => ({ id: String(idx), text: ins.text })),
    [insights],
  )

  const [scrollRef, scrolled] = useScrollShadow<HTMLDivElement>()

  const isFetching =
    resumoQ.isFetching || detalheQ.isFetching || cedentesQ.isFetching ||
    conferenciasQ.isFetching

  const hasFiltrosAtivos = periodo !== "6m" || !!fundoUuid || metodo !== "caixa"

  const provenance: ProvenanceSource[] = [
    { label: "Bitfin (catálogo de receitas)", updated: "sync diário", sla: "24h", stale: false },
    { label: `Método: ${METODOS.find((m) => m.value === metodo)?.label}`, updated: METODO_DESC[metodo], sla: "—", stale: false },
  ]

  return (
    <div className="flex h-[calc(100vh-3rem)] overflow-hidden">
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Title row */}
        <div className="shrink-0 bg-white px-6 pt-3.5 pb-3 dark:bg-gray-950">
          <PageHeader
            title="Receitas"
            subtitle="Controladoria · Receitas e Resultado"
            info="Três métodos de apuração sobre o catálogo de streams caixa-fiel: Caixa (deságio na liquidação do título), Competência (integral na efetivação) e Acruo (curva diária do fundo). Mora, prorrogação, recompra e tarifas de serviço são idênticas nos três."
            actions={
              <div className="flex items-center gap-2">
                <AIQuotaIndicator quota={quotaQ.data} loading={quotaQ.isLoading} />
                <DashboardHeaderActions
                  ai={{ open: ai.open, onToggle: ai.toggle }}
                />
              </div>
            }
          />
        </div>

        {/* Z2 — Tabs L3 */}
        <div className="shrink-0 px-6">
          <TabNavigation>
            {TABS.map((t) => (
              <TabNavigationLink
                key={t.key}
                active={tab === t.key}
                onClick={() => setTab(t.key)}
                asChild
              >
                <button type="button">{t.label}</button>
              </TabNavigationLink>
            ))}
          </TabNavigation>
        </div>

        {/* Z3 — Toolbar de filtros (flat, anatomia operacoes4) */}
        <div
          className={cx(
            "shrink-0 border-b border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
            scrolled && "scroll-shadow",
          )}
        >
          <div className="flex h-[52px] items-center gap-2 px-6">
            <SegmentSwitch
              ariaLabel="Método de apuração"
              options={METODOS.map((m) => ({ value: m.value, label: m.label }))}
              value={metodo}
              onChange={(v) => setMetodo(v)}
            />

            <div className="h-6 w-px shrink-0 bg-gray-200 dark:bg-gray-800" />

            <FilterChip
              label="Período"
              value={PERIODO_LABEL[periodo]}
              active={periodo !== "6m"}
              icon={RiCalendarLine}
            >
              <div className="py-1">
                {PERIODOS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setPeriodo(opt.value)}
                    className={cx(
                      "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                      periodo === opt.value
                        ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                        : "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800",
                    )}
                  >
                    <span className="flex-1 text-left">{opt.label}</span>
                    {periodo === opt.value && (
                      <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />
                    )}
                  </button>
                ))}
              </div>
            </FilterChip>

            <FilterChip
              label="UA"
              value={fundoSelecionado?.nome ?? "Todas"}
              active={!!fundoUuid}
            >
              <div className="max-h-72 overflow-y-auto py-1">
                {[{ id: "", nome: "Todas as UAs" }, ...uaOptions].map((ua) => (
                  <button
                    key={ua.id || "todas"}
                    type="button"
                    onClick={() => setFundoUuid(ua.id)}
                    className={cx(
                      "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                      fundoUuid === ua.id
                        ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                        : "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800",
                    )}
                  >
                    <span className="flex-1 text-left">{ua.nome}</span>
                    {fundoUuid === ua.id && (
                      <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />
                    )}
                  </button>
                ))}
              </div>
            </FilterChip>

            <Button
              variant="ghost"
              onClick={() => {
                setPeriodo("6m")
                setFundoUuid("")
                setMetodo("caixa")
              }}
              disabled={!hasFiltrosAtivos}
              className="ml-1"
            >
              <RiRefreshLine className="size-3.5 shrink-0" aria-hidden="true" />
              Resetar
            </Button>

            <span className="ml-auto shrink-0 text-[11px] text-gray-500 dark:text-gray-400">
              {isFetching ? "Atualizando…" : "Atualizado"}
            </span>
          </div>
        </div>

        {/* InsightStrip */}
        {insightStripItems.length > 0 && (
          <div className="shrink-0 px-6 pt-3">
            <InsightStrip insights={insightStripItems} />
          </div>
        )}

        {/* Conteudo (scroll interno) */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-4">
          <div className="flex flex-col gap-4">
            {tab === "visao" && (
              <VisaoGeral
                resumoQ={resumoQ}
                detalheQ={detalheQ}
                metodo={metodo}
                presetLabel={PERIODO_LABEL[periodo]}
                onDrill={(l) => setSelected(`${l.familia}|${l.stream}`)}
              />
            )}
            {tab === "familia" && (
              <DetalheTable
                linhas={detalheQ.data?.linhas ?? []}
                total={detalheQ.data?.total ?? 0}
                loading={detalheQ.isLoading}
                onDrill={(l) => setSelected(`${l.familia}|${l.stream}`)}
              />
            )}
            {tab === "cedente" && (
              <CedentesTable
                linhas={cedentesQ.data?.linhas ?? []}
                total={cedentesQ.data?.total ?? 0}
                loading={cedentesQ.isLoading}
              />
            )}
            {tab === "conferencias" && <Conferencias q={conferenciasQ} />}
          </div>
        </div>

        <ProvenanceFooter sources={provenance} />
      </div>

      <AIPanel
        open={ai.open}
        onClose={() => ai.setOpen(false)}
        context={aiContext}
        insights={insights}
        sendMessage={send}
      />

      <DrillDownSheet
        open={!!selected}
        onClose={() => setSelected(null)}
        size="xl"
        title={`${FAMILIA_LABEL[selFamilia] ?? selFamilia} · ${STREAM_LABEL[selStream] ?? selStream}`}
      >
        <DrillDownSheet.Body>
          <TitulosDrill
            linhas={titulosQ.data?.linhas ?? []}
            total={titulosQ.data?.total ?? 0}
            qtd={titulosQ.data?.qtd ?? 0}
            loading={titulosQ.isLoading}
          />
        </DrillDownSheet.Body>
      </DrillDownSheet>
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Visao geral
// ───────────────────────────────────────────────────────────────────────────

function VisaoGeral({
  resumoQ,
  detalheQ,
  metodo,
  presetLabel,
  onDrill,
}: {
  resumoQ: ReturnType<typeof useReceitasResumo>
  detalheQ: ReturnType<typeof useReceitasDetalhe>
  metodo: ReceitasMetodo
  presetLabel: string
  onDrill: (l: ReceitaDetalheLinha) => void
}) {
  const r = resumoQ.data

  const heroOption: EChartsOption = React.useMemo(() => {
    const serie = r?.serieMensal ?? []
    const familias = Array.from(
      new Set(serie.flatMap((p) => Object.keys(p.porFamilia))),
    ).sort((a, b) => (a === "operacao" ? -1 : b === "operacao" ? 1 : a.localeCompare(b)))
    return {
      grid: { left: 36, right: 8, top: 28, bottom: 4, containLabel: false },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v) => fmtBRL(Number(v ?? 0)),
      },
      legend: {
        top: 0,
        textStyle: { fontSize: 11, color: "#6B7280" },
        itemWidth: 10,
        itemHeight: 10,
        data: familias.map((f) => FAMILIA_LABEL[f] ?? f),
      },
      xAxis: {
        type: "category",
        data: serie.map((p) => fmtCompetencia(p.competencia)),
        axisLabel: { fontSize: 10, color: "#6B7280" },
        axisTick: { show: false },
        axisLine: { lineStyle: { color: "#E5E7EB" } },
      },
      yAxis: {
        type: "value",
        axisLabel: {
          fontSize: 10,
          color: "#6B7280",
          formatter: (v: number) => fmtCompacto(v),
        },
        splitLine: { lineStyle: { color: "#E5E7EB", type: "dashed" } },
      },
      series: familias.map((f) => ({
        name: FAMILIA_LABEL[f] ?? f,
        type: "bar",
        stack: "total",
        barMaxWidth: 36,
        itemStyle: { color: FAMILIA_COR[f] ?? "#9CA3AF" },
        emphasis: { focus: "series" },
        data: serie.map((p) => p.porFamilia[f] ?? 0),
      })),
    }
  }, [r])

  return (
    <>
      <KpiStrip>
        <KpiCard label="Receita total" value={r ? fmtBRL0(r.kpis.total) : "—"} sub={METODO_DESC[metodo]} />
        <KpiCard label="Deságio" value={r ? fmtBRL0(r.kpis.desagio) : "—"} sub="bloco operação" />
        <KpiCard label="Mora (juros + multa)" value={r ? fmtBRL0(r.kpis.mora) : "—"} sub="todas as famílias" />
        <KpiCard label="Tarifas" value={r ? fmtBRL0(r.kpis.tarifas) : "—"} sub="operação + serviço" />
        <KpiCard label="Recompra (encargos)" value={r ? fmtBRL0(r.kpis.recompraEncargos) : "—"} sub="juros + multa + deságio" />
      </KpiStrip>

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <EChartsCard
          className="xl:col-span-2"
          title="EVOLUÇÃO MENSAL"
          headerKpi={{
            value: r ? `R$ ${fmtCompacto(r.kpis.total)}` : "—",
            deltaSub: "no período",
          }}
          caption={`Por família · ${presetLabel}`}
          option={heroOption}
          height={300}
          loading={resumoQ.isLoading}
        />
        <ComposicaoNaturezaCard
          composicao={r?.composicaoNatureza ?? []}
          total={r?.kpis.total ?? 0}
          loading={resumoQ.isLoading}
        />
      </section>

      {r && <PonteCard ponte={r.ponte} metodoAtivo={metodo} />}

      <DetalheTable
        linhas={detalheQ.data?.linhas ?? []}
        total={detalheQ.data?.total ?? 0}
        loading={detalheQ.isLoading}
        onDrill={onDrill}
      />
    </>
  )
}

function ComposicaoNaturezaCard({
  composicao,
  total,
  loading,
}: {
  composicao: { natureza: string; valor: number }[]
  total: number
  loading: boolean
}) {
  return (
    <Card className={cardTokens.body}>
      <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
        Composição por natureza
      </p>
      <p className="mt-1 text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-50">
        {total > 0 ? `R$ ${fmtCompacto(total)}` : "—"}
      </p>
      <p className="text-[11px] text-gray-500 dark:text-gray-400">
        participação de cada natureza no total
      </p>
      <div className="mt-4 space-y-3">
        {loading && <p className="text-xs text-gray-500">Carregando…</p>}
        {!loading && composicao.map((c) => {
          const pct = total > 0 ? (c.valor / total) * 100 : 0
          return (
            <div key={c.natureza}>
              <div className="flex items-baseline justify-between gap-2">
                <span className={tableTokens.cellText}>
                  {NATUREZA_LABEL[c.natureza] ?? c.natureza}
                </span>
                <span className={tableTokens.cellNumber}>
                  {fmtBRL0(c.valor)}
                  <span className="ml-1.5 text-gray-400">
                    {pct.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%
                  </span>
                </span>
              </div>
              <div className="mt-1 h-1.5 w-full rounded-full bg-gray-100 dark:bg-gray-800">
                <div
                  className="h-1.5 rounded-full bg-blue-500"
                  style={{ width: `${Math.max(pct, 0.5)}%` }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

function PonteCard({
  ponte,
  metodoAtivo,
}: {
  ponte: NonNullable<ReturnType<typeof useReceitasResumo>["data"]>["ponte"]
  metodoAtivo: ReceitasMetodo
}) {
  const itens: { metodo: ReceitasMetodo; valor: number }[] = [
    { metodo: "caixa",       valor: ponte.caixa },
    { metodo: "competencia", valor: ponte.competencia },
    { metodo: "acruo",       valor: ponte.acruo },
  ]
  return (
    <Card className={cardTokens.body}>
      <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
        Ponte entre os métodos
      </p>
      <p className="mt-0.5 text-[11px] text-gray-500 dark:text-gray-400">
        Mesmo período e filtros — os três totais e as diferenças explicadas.
        Mora, prorrogação, recompra e tarifas de serviço são idênticas nos três.
      </p>
      <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3">
        {itens.map((i) => (
          <div
            key={i.metodo}
            className={cx(
              "rounded border p-3",
              i.metodo === metodoAtivo
                ? "border-blue-500 bg-blue-50/50 dark:bg-blue-950/20"
                : "border-gray-200 dark:border-gray-800",
            )}
          >
            <p className="text-[10px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
              {METODOS.find((m) => m.value === i.metodo)?.label}
            </p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-50">
              {fmtBRL0(i.valor)}
            </p>
            <p className="mt-0.5 text-[11px] text-gray-500 dark:text-gray-400">
              {METODO_DESC[i.metodo]}
            </p>
          </div>
        ))}
      </div>
      <div className="mt-3 space-y-1 border-t border-gray-100 pt-3 dark:border-gray-800">
        <p className="text-xs text-gray-600 dark:text-gray-300">
          <span className="font-medium">
            Competência − Caixa = {fmtBRL(ponte.deltaCompetenciaCaixa)}
          </span>
          {" "}· deságio de títulos operados no período e ainda não liquidados
        </p>
        <p className="text-xs text-gray-600 dark:text-gray-300">
          <span className="font-medium">
            Competência − Acruo = {fmtBRL(ponte.deltaCompetenciaAcruo)}
          </span>
          {" "}· saldo a apropriar — curva que corre fora do período
        </p>
      </div>
    </Card>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Tabelas
// ───────────────────────────────────────────────────────────────────────────

const colDetalhe = createColumnHelper<ReceitaDetalheLinha>()

function DetalheTable({
  linhas,
  total,
  loading,
  onDrill,
}: {
  linhas: ReceitaDetalheLinha[]
  total: number
  loading: boolean
  onDrill: (l: ReceitaDetalheLinha) => void
}) {
  const columns = React.useMemo(
    () => [
      colDetalhe.accessor("familia", {
        header: "Família",
        cell: (c) => (
          <span className={tableTokens.cellText}>
            {FAMILIA_LABEL[c.getValue()] ?? c.getValue()}
          </span>
        ),
      }),
      colDetalhe.accessor("stream", {
        header: "Stream",
        cell: (c) => (
          <span className={tableTokens.cellSecondary}>
            {STREAM_LABEL[c.getValue()] ?? c.getValue()}
          </span>
        ),
      }),
      colDetalhe.accessor("natureza", {
        header: "Natureza",
        cell: (c) => (
          <span className={tableTokens.cellSecondary}>
            {NATUREZA_LABEL[c.getValue()] ?? c.getValue()}
          </span>
        ),
      }),
      colDetalhe.accessor("qtd", {
        header: "Qtd",
        cell: (c) => (
          <span className={tableTokens.cellNumberSecondary}>
            {c.getValue().toLocaleString("pt-BR")}
          </span>
        ),
        meta: { align: "right" },
      }),
      colDetalhe.accessor("valor", {
        header: "Valor",
        cell: (c) => (
          <span className={tableTokens.cellNumber}>{fmtBRL(c.getValue())}</span>
        ),
        meta: { align: "right" },
      }),
    ] as ColumnDef<ReceitaDetalheLinha, unknown>[],
    [],
  )

  return (
    <Card className="p-0">
      <div className="flex items-baseline justify-between px-4 pb-2 pt-4">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
            Receitas por família e stream
          </p>
          <p className="mt-0.5 text-[11px] text-gray-500 dark:text-gray-400">
            clique numa linha para abrir os títulos/lançamentos
          </p>
        </div>
        <span className={tableTokens.cellNumber}>
          {loading ? "…" : fmtBRL(total)}
        </span>
      </div>
      <DataTable
        data={linhas}
        columns={columns}
        density="compact"
        onRowClick={onDrill}
        renderFooter={(rows) => (
          <div className="flex justify-between px-4 py-2">
            <span className={tableTokens.cellSecondary}>
              {rows.length} linhas (todas exibidas)
            </span>
            <span className={tableTokens.cellNumber}>
              {fmtBRL(rows.reduce((s, r) => s + r.valor, 0))}
            </span>
          </div>
        )}
      />
    </Card>
  )
}

const colCed = createColumnHelper<ReceitaCedenteLinha>()

function CedentesTable({
  linhas,
  total,
  loading,
}: {
  linhas: ReceitaCedenteLinha[]
  total: number
  loading: boolean
}) {
  const columns = React.useMemo(
    () => [
      colCed.accessor("cedenteNome", {
        header: "Cedente",
        cell: (c) => <span className={tableTokens.cellText}>{c.getValue()}</span>,
      }),
      colCed.accessor("desagio", {
        header: "Deságio",
        cell: (c) => <span className={tableTokens.cellNumber}>{fmtBRL(c.getValue())}</span>,
        meta: { align: "right" },
      }),
      colCed.accessor("mora", {
        header: "Mora",
        cell: (c) => <span className={tableTokens.cellNumber}>{fmtBRL(c.getValue())}</span>,
        meta: { align: "right" },
      }),
      colCed.accessor("tarifas", {
        header: "Tarifas",
        cell: (c) => <span className={tableTokens.cellNumber}>{fmtBRL(c.getValue())}</span>,
        meta: { align: "right" },
      }),
      colCed.accessor("demais", {
        header: "Demais",
        cell: (c) => <span className={tableTokens.cellNumberSecondary}>{fmtBRL(c.getValue())}</span>,
        meta: { align: "right" },
      }),
      colCed.accessor("total", {
        header: "Total",
        cell: (c) => <span className={tableTokens.cellStrong}>{fmtBRL(c.getValue())}</span>,
        meta: { align: "right" },
      }),
    ] as ColumnDef<ReceitaCedenteLinha, unknown>[],
    [],
  )
  return (
    <Card className="p-0">
      <div className="flex items-baseline justify-between px-4 pb-2 pt-4">
        <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
          Receita por cedente
        </p>
        <span className={tableTokens.cellNumber}>{loading ? "…" : fmtBRL(total)}</span>
      </div>
      <DataTable
        data={linhas}
        columns={columns}
        density="compact"
        renderFooter={(rows) => (
          <div className="flex justify-between px-4 py-2">
            <span className={tableTokens.cellSecondary}>
              {rows.length} cedentes (todos exibidos)
            </span>
            <span className={tableTokens.cellNumber}>
              {fmtBRL(rows.reduce((s, r) => s + r.total, 0))}
            </span>
          </div>
        )}
      />
    </Card>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Conferencias — desconto de mora concedido
// ───────────────────────────────────────────────────────────────────────────

const colConf = createColumnHelper<DescontoMoraCedente>()

function Conferencias({
  q,
}: {
  q: ReturnType<typeof useReceitasConferencias>
}) {
  const d = q.data
  const columns = React.useMemo(
    () => [
      colConf.accessor("cedenteNome", {
        header: "Cedente",
        cell: (c) => <span className={tableTokens.cellText}>{c.getValue()}</span>,
      }),
      colConf.accessor("regua", {
        header: "Régua contratual",
        cell: (c) => <span className={tableTokens.cellNumberSecondary}>{fmtBRL(c.getValue())}</span>,
        meta: { align: "right" },
      }),
      colConf.accessor("cobrado", {
        header: "Cobrado",
        cell: (c) => <span className={tableTokens.cellNumber}>{fmtBRL(c.getValue())}</span>,
        meta: { align: "right" },
      }),
      colConf.accessor("desconto", {
        header: "Desconto concedido",
        cell: (c) => (
          <span
            className={cx(
              tableTokens.cellNumber,
              c.getValue() > 0 && "text-red-600 dark:text-red-400",
            )}
          >
            {fmtBRL(c.getValue())}
          </span>
        ),
        meta: { align: "right" },
      }),
      colConf.accessor("perdoesTotais", {
        header: "Perdões totais",
        cell: (c) => (
          <span className={tableTokens.cellNumberSecondary}>
            {c.getValue() > 0 ? c.getValue().toLocaleString("pt-BR") : "—"}
          </span>
        ),
        meta: { align: "right" },
      }),
      colConf.accessor("qtd", {
        header: "Títulos",
        cell: (c) => (
          <span className={tableTokens.cellNumberSecondary}>
            {c.getValue().toLocaleString("pt-BR")}
          </span>
        ),
        meta: { align: "right" },
      }),
    ] as ColumnDef<DescontoMoraCedente, unknown>[],
    [],
  )

  return (
    <>
      <KpiStrip>
        <KpiCard label="Régua contratual" value={d ? fmtBRL0(d.totalRegua) : "—"} sub="mora devida pelo contrato" />
        <KpiCard label="Cobrado" value={d ? fmtBRL0(d.totalCobrado) : "—"} sub="efetivamente lançado" />
        <KpiCard label="Desconto concedido" value={d ? fmtBRL0(d.totalDesconto) : "—"} sub="régua − cobrado" />
        <KpiCard label="Perdões totais" value={d ? d.totalPerdoes.toLocaleString("pt-BR") : "—"} sub="títulos com mora 100% perdoada" />
      </KpiStrip>
      <Card className="p-0">
        <div className="px-4 pb-2 pt-4">
          <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
            Desconto de mora por cedente
          </p>
          <p className="mt-0.5 text-[11px] text-gray-500 dark:text-gray-400">
            recompras e encargos negociados com régua contratual registrada —
            desconto negativo = cobrado acima da régua
          </p>
        </div>
        <DataTable
          data={d?.descontoMora ?? []}
          columns={columns}
          density="compact"
          renderFooter={(rows) => (
            <div className="flex justify-between px-4 py-2">
              <span className={tableTokens.cellSecondary}>
                {rows.length} cedentes (todos exibidos)
              </span>
              <span className={tableTokens.cellNumber}>
                {fmtBRL(rows.reduce((s, r) => s + r.desconto, 0))}
              </span>
            </div>
          )}
        />
      </Card>
    </>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Drill de titulos (DrillDownSheet)
// ───────────────────────────────────────────────────────────────────────────

const colTit = createColumnHelper<ReceitaTituloLinha>()

function TitulosDrill({
  linhas,
  total,
  qtd,
  loading,
}: {
  linhas: ReceitaTituloLinha[]
  total: number
  qtd: number
  loading: boolean
}) {
  const columns = React.useMemo(
    () => [
      colTit.accessor("data", {
        header: "Data",
        cell: (c) => {
          const [y, m, dd] = c.getValue().split("-")
          return <span className={tableTokens.cellTextMono}>{`${dd}/${m}/${y.slice(2)}`}</span>
        },
      }),
      colTit.accessor("documento", {
        header: "Documento",
        cell: (c) => <span className={tableTokens.cellTextMono}>{c.getValue() ?? "—"}</span>,
      }),
      colTit.accessor("cedenteNome", {
        header: "Cedente",
        cell: (c) => <span className={tableTokens.cellSecondary}>{c.getValue() ?? "—"}</span>,
      }),
      colTit.accessor("natureza", {
        header: "Natureza",
        cell: (c) => (
          <span className={tableTokens.cellSecondary}>
            {NATUREZA_LABEL[c.getValue()] ?? c.getValue()}
          </span>
        ),
      }),
      colTit.accessor("valor", {
        header: "Valor",
        cell: (c) => <span className={tableTokens.cellNumber}>{fmtBRL(c.getValue())}</span>,
        meta: { align: "right" },
      }),
      colTit.accessor("valorReferenciaRegua", {
        header: "Régua",
        cell: (c) => {
          const v = c.getValue()
          return (
            <span className={tableTokens.cellNumberSecondary}>
              {v === null ? "—" : fmtBRL(v)}
            </span>
          )
        },
        meta: { align: "right" },
      }),
    ] as ColumnDef<ReceitaTituloLinha, unknown>[],
    [],
  )

  if (loading) {
    return <p className="px-4 py-6 text-sm text-gray-500">Carregando títulos…</p>
  }
  return (
    <DataTable
      data={linhas}
      columns={columns}
      density="ultra"
      virtualize
      renderFooter={() => (
        <div className="flex justify-between px-4 py-2">
          <span className={tableTokens.cellSecondary}>
            {qtd.toLocaleString("pt-BR")} linhas (todas — soma fecha o total)
          </span>
          <span className={tableTokens.cellNumber}>{fmtBRL(total)}</span>
        </div>
      )}
    />
  )
}
