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
import {
  KpiHeadline,
  type KpiHeadlineDiagnostic,
} from "@/design-system/components/KpiHeadline"
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
  const dq = balancete?.data_quality
  const nodes = balancete?.nodes ?? []
  const classeBreakdown =
    selectedNode?.codigo && balancete
      ? balancete.classe_breakdown_por_cosif[selectedNode.codigo]
      : undefined

  // ─── Diagnostico do KpiHeadline ─────────────────────────────────────────
  // Ordem dos chips:
  //   0. (prioritario) Snapshot parcial — quando data_quality.comparable=false,
  //      esse chip aparece PRIMEIRO em vermelho e o numero primary vira cinza.
  //      Comparacao distorcida e o problema mais grave: sem dado consistente,
  //      os outros diagnosticos perdem sentido.
  //   1. Reconciliacao: |residuo| / |PL Sub D-1| <= 0,1pp = ok
  //   2. Cobertura COSIF: 0 rows pendentes = ok
  //   3. Anomalias adicionais: placeholder ate termos detector dedicado
  const headlineDiagnostics = React.useMemo<KpiHeadlineDiagnostic[]>(() => {
    if (!recon || !cob) return []
    const out: KpiHeadlineDiagnostic[] = []

    // 0. Snapshot parcial — prioritario
    if (dq && !dq.comparable) {
      out.push({
        label: dq.reason ?? "Comparacao nao confiavel (snapshot parcial)",
        tone:  "error",
      })
    }

    // 1. Reconciliacao
    const residuoPp =
      recon.pl_cota_sub_d1 !== 0
        ? Math.abs(recon.residuo) / Math.abs(recon.pl_cota_sub_d1)
        : 0
    if (residuoPp <= 0.001) {
      out.push({ label: "Reconciliada", tone: "ok" })
    } else if (residuoPp <= 0.01) {
      out.push({
        label: `Residuo ${fmtBRLCompact.format(Math.abs(recon.residuo))}`,
        tone:  "warning",
      })
    } else {
      out.push({
        label: `Residuo ${fmtBRLCompact.format(Math.abs(recon.residuo))} acima da tolerancia`,
        tone:  "error",
      })
    }

    // 2. Cobertura COSIF
    const pendentesCount = cob.rows_por_source.pendente ?? 0
    if (pendentesCount === 0) {
      out.push({ label: "Cobertura 100%", tone: "ok" })
    } else {
      out.push({
        label: `${pendentesCount} ${pendentesCount === 1 ? "papel sem COSIF" : "papeis sem COSIF"}`,
        tone:  "warning",
      })
    }

    // 3. Anomalias dedicadas — placeholder ate Fase 1.5 (detector heuristico)
    out.push({ label: "0 anomalias", tone: "ok" })

    return out
  }, [recon, cob, dq])

  const headlinePrimary = React.useMemo(() => {
    if (!recon) return { value: "—" }
    const pct = recon.delta_pct_sobre_d1
    const sinalPct = pct >= 0 ? "+" : ""
    const sinalReal = recon.delta_pl_cota_sub_real >= 0 ? "+" : ""
    // Quando snapshot e parcial, forca tone=neutral (cinza) para evitar que o
    // usuario interprete um numero distorcido como tendencia real.
    const tone: "positive" | "negative" | "neutral" | undefined =
      dq && !dq.comparable ? "neutral" : undefined
    return {
      value: `${sinalPct}${pct.toFixed(2).replace(".", ",")}%`,
      sub:   `${sinalReal}${fmtBRLCompact.format(recon.delta_pl_cota_sub_real)} vs D-1`,
      tone,
    }
  }, [recon, dq])

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
      {/* 1. KpiHeadline — Z1 canonica para paginas analiticas com pergunta
          dominante. Substitui a strip de 4 KpiCards (tile syndrome). */}
      <KpiHeadline
        statement="Variação do PL"
        primary={headlinePrimary}
        diagnostics={headlineDiagnostics}
        loading={loading && !balancete}
      />

      {/* 2. Balancete patrimonial diario hierarquico — tabela COSIF como
          referencia primaria de leitura (controller le saldos antes do
          waterfall, que e a sintese do movimento) */}
      <BalanceteDiarioTable
        nodes={nodes}
        data={balancete?.data_d_zero}
        dataAnterior={balancete?.data_d_minus_1}
        emptyMessage={loading ? "Carregando..." : undefined}
        onSelectNode={setSelectedNode}
        comparable={dq?.comparable ?? true}
        unreliableReason={dq?.reason}
      />

      {/* 3. Hero waterfall — reconciliacao da Cota Sub (sintese visual do
          movimento, complementa a tabela acima) */}
      <ReconciliacaoWaterfallCard
        reconciliacao={recon}
        loading={loading}
        error={errorMessage ?? null}
        onRetry={onRetry}
        comparable={dq?.comparable ?? true}
        unreliableReason={dq?.reason}
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
