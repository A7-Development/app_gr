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
import { RiAlertLine, RiArrowDownLine, RiCalendarLine } from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import {
  KpiHeadline,
  type KpiHeadlineDiagnostic,
} from "@/design-system/components/KpiHeadline"
import { EmptyState } from "@/design-system/components/EmptyState"
import { ErrorState } from "@/design-system/components/ErrorState"

import type { BalanceteResponse, CosifNode } from "@/lib/api-client"

import { AnaliseVariacaoCard } from "./AnaliseVariacaoCard"
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
}

// ─── Componente ──────────────────────────────────────────────────────────────

export function EventosDiaTab({
  balancete,
  loading       = false,
  errorMessage,
  onRetry,
}: EventosDiaTabProps) {
  const [selectedNode, setSelectedNode] = React.useState<CosifNode | null>(null)

  const recon = balancete?.reconciliacao
  const cob = balancete?.cobertura
  const dq = balancete?.data_quality
  const nodes = balancete?.nodes ?? []

  // Pendentes — usado em multiplos lugares (banner sticky, KpiHeadline,
  // tone forcado). Conta + valor cumulativo |valor_por_source.pendente|.
  const pendentesCount = cob?.rows_por_source.pendente ?? 0
  const pendentesValor = cob?.valor_por_source.pendente ?? 0
  const hasPendentes = pendentesCount > 0

  // Quando ha pendente OU dataquality incompativel, numero primary vira
  // cinza — explicabilidade > sofisticacao (CLAUDE.md §14). Usuario nao
  // deve interpretar variacao como tendencia real se ha lancamentos
  // fora da arvore ou se o snapshot D-1 e parcial.
  const cotaTonelaForcaNeutral = hasPendentes || (dq != null && !dq.comparable)

  // Ref para scroll do CTA "Ver pendentes" no banner
  const residuoCardRef = React.useRef<HTMLDivElement>(null)
  const scrollToResiduo = React.useCallback(() => {
    residuoCardRef.current?.scrollIntoView({
      behavior: "smooth",
      block:    "start",
    })
  }, [])

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

    // 2. Cobertura COSIF — QUALQUER pendente vira tone='error' (nao warning).
    // Caso real 2026-05-12: 4 rows pendentes com R$ -19k passaram despercebidos
    // com chip amber pequeno enquanto outros chips estavam em verde. Defesa:
    // pendente >0 = chip prioritario em vermelho, alem do banner sticky no topo.
    if (pendentesCount === 0) {
      out.push({ label: "Cobertura 100%", tone: "ok" })
    } else {
      out.push({
        label: `${pendentesCount} ${pendentesCount === 1 ? "papel sem COSIF" : "papeis sem COSIF"}`,
        tone:  "error",
      })
    }

    // 3. Anomalias dedicadas — placeholder ate Fase 1.5 (detector heuristico)
    out.push({ label: "0 anomalias", tone: "ok" })

    return out
  }, [recon, cob, dq, pendentesCount])

  const headlinePrimary = React.useMemo(() => {
    if (!recon) return { value: "—" }
    const pct = recon.delta_pct_sobre_d1
    const sinalPct = pct >= 0 ? "+" : ""
    const sinalReal = recon.delta_pl_cota_sub_real >= 0 ? "+" : ""
    // Numero primary fica cinza quando ha pendente OU snapshot parcial —
    // usuario nao deve interpretar como tendencia real se ha lancamentos
    // fora da arvore ou se D-1 e incompleto.
    const tone: "positive" | "negative" | "neutral" | undefined =
      cotaTonelaForcaNeutral ? "neutral" : undefined
    return {
      value: `${sinalPct}${pct.toFixed(2).replace(".", ",")}%`,
      sub:   `${sinalReal}${fmtBRLCompact.format(recon.delta_pl_cota_sub_real)} vs D-1`,
      tone,
    }
  }, [recon, cotaTonelaForcaNeutral])

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
      {/* 0. Banner sticky de pendentes — defesa C1 (CLAUDE.md §14
          explicabilidade > inferencia). Aparece SO quando ha pendentes,
          some quando todos identificadores estao classificados. */}
      {hasPendentes && (
        <div className="sticky top-0 z-10 -mx-6 flex flex-wrap items-center gap-3 border-b border-red-200 bg-red-50 px-6 py-2.5 text-[13px] dark:border-red-900/40 dark:bg-red-950/40">
          <RiAlertLine
            className="size-4 shrink-0 text-red-600 dark:text-red-400"
            aria-hidden="true"
          />
          <span className="font-medium text-red-800 dark:text-red-200">
            {pendentesCount} {pendentesCount === 1 ? "papel" : "papeis"} sem classificacao COSIF
          </span>
          <span className="text-red-700 dark:text-red-300">
            ({fmtBRLCompact.format(Math.abs(pendentesValor))} fora da arvore) — analise pode estar incompleta
          </span>
          <button
            type="button"
            onClick={scrollToResiduo}
            className="ml-auto inline-flex items-center gap-1 rounded-sm border border-red-300 bg-white px-2 py-0.5 text-[12px] font-medium text-red-700 transition-colors hover:bg-red-100 dark:border-red-800 dark:bg-red-950/60 dark:text-red-200 dark:hover:bg-red-900/40"
          >
            Ver pendentes
            <RiArrowDownLine className="size-3.5" aria-hidden="true" />
          </button>
        </div>
      )}

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
        classeBreakdownPorCosif={balancete?.classe_breakdown_por_cosif}
        rowsPorCosif={balancete?.rows_por_cosif}
        resultado={recon ? {
          label:     "RESULTADO DO DIA — COTA SUBORDINADA",
          d_minus_1: recon.pl_cota_sub_d1,
          d_zero:    recon.pl_cota_sub_d0,
          delta:     recon.delta_pl_cota_sub_real,
          delta_pct: recon.delta_pct_sobre_d1,
        } : undefined}
        data={balancete?.data_d_zero}
        dataAnterior={balancete?.data_d_minus_1}
        emptyMessage={loading ? "Carregando..." : undefined}
        onSelectNode={setSelectedNode}
        comparable={dq?.comparable ?? true}
        unreliableReason={dq?.reason}
      />

      {/* 3. Grid 2-col — esquerda: waterfall da reconciliacao; direita:
          shell de analise da variacao (explainers heuristicos virao). */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ReconciliacaoWaterfallCard
          reconciliacao={recon}
          nodes={nodes}
          loading={loading}
          error={errorMessage ?? null}
          onRetry={onRetry}
          comparable={dq?.comparable ?? true}
          unreliableReason={dq?.reason}
        />
        <AnaliseVariacaoCard balancete={balancete} />
      </div>

      {/* 4. Residuo + cobertura (Z4) — alvo do botao 'Ver pendentes'
          no banner sticky acima. */}
      <div ref={residuoCardRef} className="scroll-mt-4">
        <ResiduoAlertCard
          reconciliacao={recon}
          cobertura={cob}
        />
      </div>

      {/* Drill-down — sheet de EXPLICACAO (papeis ja estao na propria tabela). */}
      <CosifDrillSheet
        node={selectedNode}
        onClose={() => setSelectedNode(null)}
      />
    </div>
  )
}
