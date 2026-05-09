"use client"

/**
 * EventosDiaTab — composicao da Aba "Eventos do dia" da pagina cota-sub.
 *
 * Layout vertical (top → bottom):
 *   1. KpiStrip 5 KPIs (PL Sub D0, ΔPL, %Δ vs CDI, ΔAtivo, ΔPassivo)
 *   2. WaterfallEventosCard — chart hero da decomposicao
 *   3. InsightStrip 38px — insights heuristicos (nao-LLM no PR1)
 *   4. BalanceTable evoluida (showContribuicao + sortByDelta)
 *
 * Recebe o payload do `/balanco`, agrega via agregarBuckets, gera insights
 * heuristicos e propaga para os componentes filhos. Sem fetch direto — pure
 * composition de dados ja prontos.
 *
 * Defensivo: quando `rows` chega vazio (data sem snapshot QiTech — caso
 * patologico que ja deveria ser bloqueado pelo Calendar), renderiza
 * EmptyState explicativo em vez de KPIs/charts/tabela com numeros falsos.
 * CLAUDE.md §14: explicabilidade > sofisticacao em mercado regulado.
 */

import * as React from "react"
import { RiCalendarLine } from "@remixicon/react"

import { KpiCard, KpiStrip } from "@/design-system/components/KpiStrip"
import { InsightStrip } from "@/design-system/components/InsightStrip"
import { EmptyState } from "@/design-system/components/EmptyState"

import type { BalanceRow } from "@/lib/api-client"

import { agregarBuckets, decomposicaoLinhas } from "../_lib/agregacao-buckets"
import { gerarInsights } from "../_lib/insights-heuristica"
import { BalanceTable } from "./BalanceTable"
import { WaterfallEventosCard } from "./WaterfallEventosCard"

// ─── Formatadores ────────────────────────────────────────────────────────────

const fmtBRLCompact = new Intl.NumberFormat("pt-BR", {
  style:                 "currency",
  currency:              "BRL",
  notation:              "compact",
  maximumFractionDigits: 2,
})

// ─── Props ───────────────────────────────────────────────────────────────────

export type EventosDiaTabProps = {
  rows:               BalanceRow[]
  data?:              string
  dataAnterior?:      string
  loading?:           boolean
  errorMessage?:      string
  emptyMessage?:      string
}

// ─── Componente ──────────────────────────────────────────────────────────────

export function EventosDiaTab({
  rows,
  data,
  dataAnterior,
  loading       = false,
  errorMessage,
  emptyMessage,
}: EventosDiaTabProps) {
  const agregacao = React.useMemo(
    () => (rows.length > 0 ? agregarBuckets(rows) : undefined),
    [rows],
  )

  // Decomposicao granular (linha-a-linha) — alimenta o waterfall com 3 grupos
  // (Ativo | Passivo | Δ). Mantida em paralelo a `agregacao` (que serve KPIs +
  // insights heuristicos com vocabulario tematico mais legivel).
  const decomposicao = React.useMemo(
    () => (rows.length > 0 ? decomposicaoLinhas(rows) : undefined),
    [rows],
  )

  const insights = React.useMemo(
    () => (agregacao ? gerarInsights(agregacao) : []),
    [agregacao],
  )

  // Delta percentual sobre PL Sub D-1 — exibido como sub do KPI principal
  const deltaPctTexto = React.useMemo(() => {
    if (!agregacao || agregacao.cota_sub_d1 === 0) return undefined
    const pct = (agregacao.delta_cota_sub / Math.abs(agregacao.cota_sub_d1)) * 100
    return `${pct >= 0 ? "+" : ""}${pct.toFixed(2).replace(".", ",")}%`
  }, [agregacao])

  // Defensivo: rows vazio = data sem snapshot QiTech para esta UA. Calendar
  // ja bloqueia esse caso, mas se o usuario chegar via deep-link ou houver
  // race condition apos troca de fundo, renderiza EmptyState em vez de
  // numeros falsos.
  if (!loading && rows.length === 0) {
    return (
      <EmptyState
        icon={RiCalendarLine}
        title="Sem dados para esta data"
        description="A QiTech nao publicou snapshot deste fundo no dia selecionado (provavelmente fim de semana, feriado ou pendencia de ETL). Selecione outra data no Calendar."
        className="mt-4"
      />
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {/* 1. KpiStrip — 5 KPIs do dia */}
      <KpiStrip cols={5}>
        <KpiCard
          label="PL Cota Sub"
          value={agregacao ? fmtBRLCompact.format(agregacao.cota_sub_d0) : "—"}
          sub={dataAnterior ? `D-1: ${agregacao ? fmtBRLCompact.format(agregacao.cota_sub_d1) : "—"}` : undefined}
          source="QiTech"
        />
        <KpiCard
          label="Δ PL Cota Sub"
          value={agregacao ? fmtBRLCompact.format(agregacao.delta_cota_sub) : "—"}
          sub={deltaPctTexto ?? "—"}
          delta={
            agregacao && agregacao.cota_sub_d1 !== 0
              ? {
                  value: (agregacao.delta_cota_sub / Math.abs(agregacao.cota_sub_d1)) * 100,
                  suffix: "%",
                }
              : undefined
          }
          deltaSub="dia"
          source="QiTech"
        />
        <KpiCard
          label="Δ Ativo"
          value={agregacao ? fmtBRLCompact.format(agregacao.delta_ativo) : "—"}
          sub="contribuicao positiva"
          source="QiTech"
        />
        <KpiCard
          label="Δ Passivo + Equity"
          value={agregacao ? fmtBRLCompact.format(agregacao.delta_passivo) : "—"}
          sub="contribuicao negativa"
          source="QiTech"
        />
        <KpiCard
          label="Bucket dominante"
          value={dominanteLabel(agregacao)}
          sub={dominanteSubtexto(agregacao)}
          source="QiTech"
        />
      </KpiStrip>

      {/* 2. Hero waterfall — decomposicao da Cota Sub.
          Card ocupa 50% da largura em viewports >= lg (espaco a direita reservado
          para apoios complementares no PR2: tabela compacta de buckets, mini
          chart de evolucao do PL Sub, etc). */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <WaterfallEventosCard
          decomposicao={decomposicao}
          loading={loading}
          error={errorMessage ?? null}
        />
      </div>

      {/* 3. InsightStrip — heuristica (nao-LLM no PR1) */}
      {insights.length > 0 && (
        <InsightStrip
          insights={insights}
          storageKey="strata:cota-sub:eventos-dia:insight-strip:dismissed"
        />
      )}

      {/* 4. BalanceTable evoluida — foco no Δ + contribuicao na Cota Sub,
          ordenavel por magnitude do Δ. Mantem hierarquia (section/subtotal/
          total) intocada — sort vale apenas para line/sub. */}
      <BalanceTable
        rows={rows}
        data={data}
        dataAnterior={dataAnterior}
        emptyMessage={emptyMessage}
        showContribuicao
        sortByDelta
        title="Eventos por linha do balancete"
      />
    </div>
  )
}

// ─── Helpers do KpiCard "Bucket dominante" ───────────────────────────────────

function dominanteLabel(
  agg: ReturnType<typeof agregarBuckets> | undefined,
): string {
  if (!agg) return "—"
  const ranking = [...agg.buckets]
    .filter((b) => b.contribuicao_cota_sub !== 0)
    .sort(
      (a, b) =>
        Math.abs(b.contribuicao_cota_sub) - Math.abs(a.contribuicao_cota_sub),
    )
  return ranking[0]?.label ?? "—"
}

function dominanteSubtexto(
  agg: ReturnType<typeof agregarBuckets> | undefined,
): string {
  if (!agg) return "—"
  const ranking = [...agg.buckets]
    .filter((b) => b.contribuicao_cota_sub !== 0)
    .sort(
      (a, b) =>
        Math.abs(b.contribuicao_cota_sub) - Math.abs(a.contribuicao_cota_sub),
    )
  const top = ranking[0]
  if (!top) return "—"
  const sinal = top.contribuicao_cota_sub >= 0 ? "+" : ""
  return `${sinal}${fmtBRLCompact.format(top.contribuicao_cota_sub)}`
}
