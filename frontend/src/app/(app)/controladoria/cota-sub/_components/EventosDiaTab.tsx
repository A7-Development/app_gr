"use client"

/**
 * EventosDiaTab — composicao da Aba "Eventos do dia" da pagina cota-sub.
 *
 * Layout vertical (top -> bottom):
 *   1. KpiStrip 4 KPIs (PL Sub D0, ΔPL R$, %ΔvsD-1, Cobertura, Residuo)
 *   2. ReconciliacaoWaterfallCard — hero (Z2)
 *   3. BalanceteDiarioTable — arvore COSIF hierarquica (Z3)
 *   4. ResiduoAlertCard — alerta de cobertura/residuo (Z4)
 *
 * Consome BalanceteResponse do endpoint /controladoria/cota-sub/balancete-diario.
 * Classificacao COSIF agnostica multi-tenant (CLAUDE.md §10) — ver
 * backend/docs/atribuicao-cota-sub-cosif.md.
 *
 * Defensivo: quando `balancete` chega vazio ou em erro, renderiza EmptyState
 * em vez de KPIs/charts/tabela com numeros falsos. CLAUDE.md §14:
 * explicabilidade > sofisticacao em mercado regulado.
 */

import * as React from "react"
import { RiCalendarLine } from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { KpiCard, KpiStrip } from "@/design-system/components/KpiStrip"
import { EmptyState } from "@/design-system/components/EmptyState"
import { ErrorState } from "@/design-system/components/ErrorState"

import type { BalanceteResponse, CosifNode } from "@/lib/api-client"

import { BalanceteDiarioTable } from "./BalanceteDiarioTable"
import { CosifDrillSheet } from "./CosifDrillSheet"
import { ReconciliacaoWaterfallCard } from "./ReconciliacaoWaterfallCard"
import { ResiduoAlertCard } from "./ResiduoAlertCard"

// ─── Formatadores ────────────────────────────────────────────────────────────

const fmtBRLCompact = new Intl.NumberFormat("pt-BR", {
  style: "currency", currency: "BRL",
  notation: "compact", maximumFractionDigits: 2,
})

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency", currency: "BRL",
  minimumFractionDigits: 2, maximumFractionDigits: 2,
})

const fmtPct = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2, maximumFractionDigits: 2,
})

// ─── Props ───────────────────────────────────────────────────────────────────

export type EventosDiaTabProps = {
  balancete?:    BalanceteResponse
  loading?:      boolean
  errorMessage?: string
  onRetry?:      () => void
  /** Fundo selecionado — necessario para o drill de rows silver. */
  fundoId?:      string | null
}

// ─── Componente ──────────────────────────────────────────────────────────────

export function EventosDiaTab({
  balancete,
  loading       = false,
  errorMessage,
  onRetry,
  fundoId,
}: EventosDiaTabProps) {
  const [selectedNode, setSelectedNode] = React.useState<CosifNode | null>(null)

  const recon = balancete?.reconciliacao
  const cob = balancete?.cobertura
  const nodes = balancete?.nodes ?? []
  const classeBreakdown =
    selectedNode?.codigo && balancete
      ? balancete.classe_breakdown_por_cosif[selectedNode.codigo]
      : undefined

  // Cobertura % classificada (override + rule)
  const coberturaPct = React.useMemo(() => {
    if (!cob || cob.total_rows === 0) return null
    const pend = cob.rows_por_source.pendente ?? 0
    return (1 - pend / cob.total_rows) * 100
  }, [cob])

  // Erro: prioriza ErrorState (CLAUDE.md §14 — explicar a falha).
  if (errorMessage && !loading) {
    return (
      <ErrorState
        title="Falha ao carregar o balancete"
        description={errorMessage}
        action={onRetry ? <Button onClick={onRetry}>Tentar novamente</Button> : undefined}
        className="mt-4"
      />
    )
  }

  // Vazio: caso patologico — Calendar normalmente bloqueia. Mantemos
  // EmptyState defensivo.
  if (!loading && !balancete) {
    return (
      <EmptyState
        icon={RiCalendarLine}
        title="Sem dados para esta data"
        description="A QiTech nao publicou snapshot deste fundo no dia selecionado (fim de semana, feriado ou ETL pendente). Selecione outra data no Calendar."
        className="mt-4"
      />
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {/* 1. KpiStrip — 4 KPIs do dia */}
      <KpiStrip cols={4}>
        <KpiCard
          label="PL Cota Sub"
          value={recon ? fmtBRLCompact.format(recon.pl_cota_sub_d0) : "—"}
          sub={recon ? `D-1: ${fmtBRLCompact.format(recon.pl_cota_sub_d1)}` : undefined}
          source="QiTech"
        />
        <KpiCard
          label="Δ PL Cota Sub"
          value={recon ? fmtBRLCompact.format(recon.delta_pl_cota_sub_real) : "—"}
          delta={
            recon && recon.pl_cota_sub_d1 !== 0
              ? { value: recon.delta_pct_sobre_d1, suffix: "%" }
              : undefined
          }
          deltaSub="vs D-1"
          source="QiTech"
        />
        <KpiCard
          label="Cobertura COSIF"
          value={coberturaPct != null ? `${fmtPct.format(coberturaPct)}%` : "—"}
          sub={cob ? `${cob.total_rows} rows classificadas` : undefined}
          source="A7 · classifier"
        />
        <KpiCard
          label="Residuo"
          value={recon ? fmtBRL.format(recon.residuo) : "—"}
          sub={
            recon && recon.pl_cota_sub_d1 !== 0
              ? `${fmtPct.format(Math.abs(recon.residuo) / Math.abs(recon.pl_cota_sub_d1) * 100)} pp do PL Sub`
              : undefined
          }
          source="reconciliacao"
        />
      </KpiStrip>

      {/* 2. Hero waterfall — reconciliacao da Cota Sub (Z2) */}
      <ReconciliacaoWaterfallCard
        reconciliacao={recon}
        loading={loading}
        error={errorMessage ?? null}
        onRetry={onRetry}
      />

      {/* 3. Balancete patrimonial diario hierarquico (Z3) */}
      <BalanceteDiarioTable
        nodes={nodes}
        data={balancete?.data_d_zero}
        dataAnterior={balancete?.data_d_minus_1}
        emptyMessage={loading ? "Carregando..." : undefined}
        onSelectNode={setSelectedNode}
      />

      {/* 4. Residuo + cobertura (Z4) */}
      <ResiduoAlertCard
        reconciliacao={recon}
        cobertura={cob}
      />

      {/* Drill-down — abre ao clicar conta analitica no Z3 */}
      <CosifDrillSheet
        node={selectedNode}
        classeBreakdown={classeBreakdown}
        fundoId={fundoId ?? null}
        dataPosicao={balancete?.data_d_zero ?? null}
        onClose={() => setSelectedNode(null)}
      />
    </div>
  )
}
