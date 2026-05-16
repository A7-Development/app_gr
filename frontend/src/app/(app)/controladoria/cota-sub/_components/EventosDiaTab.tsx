"use client"

/**
 * EventosDiaTab — composicao da aba "Eventos do dia" da pagina cota-sub.
 *
 * Redesenho 2026-05-14 a partir do handoff `analise-cota` (Claude Design).
 * Substitui o shell antigo (`KpiHeadline + grid 2-col`) pelo split layout:
 *
 *   [Banner sticky pendentes]                              <- defesa C1, preservado
 *   [StatusHeadlineCompact]                                <- Z1 compacto (PL, ΔReal, Δ%, chips)
 *   [SubTabBar: Resumo narrativo | Detalhe contábil]       <- segment
 *   if Resumo:
 *     grid 1.42fr/1fr:
 *       left:  [BridgeCard]      <- waterfall por categoria
 *              [ReconStatusCard] <- strip de reconciliacao + stats
 *       right: [DriversCard]     <- 4 categorias com expand+evidencias
 *   if Detalhe:
 *     [BalanceteDiarioTable]     <- arvore COSIF hierarquica (preservada)
 *
 * Defesas preservadas integralmente: banner sticky de pendentes (incidente
 * 2026-05-12), ErrorState/EmptyState defensivos, data_quality.comparable
 * forca neutral, CosifDrillSheet para drill em folha COSIF (so na aba
 * "Detalhe contábil"). Aderente a CLAUDE.md §14 explicabilidade > inferencia.
 */

import * as React from "react"
import { RiAlertLine, RiArrowDownLine, RiCalendarLine } from "@remixicon/react"

import { cx } from "@/lib/utils"
import { Button } from "@/components/tremor/Button"
import { EmptyState } from "@/design-system/components/EmptyState"
import { ErrorState } from "@/design-system/components/ErrorState"

import type {
  ApropriacaoExplanation,
  BalanceteResponse,
  CosifNode,
  DiferimentoExplanation,
  PddExplanation,
} from "@/lib/api-client"
import { useExplicacaoVariacao } from "@/lib/hooks/controladoria"

import { BalanceteDiarioTable } from "./BalanceteDiarioTable"
import {
  BridgeCard,
  type BridgeDriver,
} from "./BridgeCard"
import { CosifDrillSheet } from "./CosifDrillSheet"
import {
  buildDriverFromEventosContabeis,
  DriversCard,
  type DriverInput,
} from "./DriversCard"
import { ReconStatusCard } from "./ReconStatusCard"
import {
  StatusHeadlineCompact,
  type StatusHeadlineChip,
} from "./StatusHeadlineCompact"
import { SubTabBar, type SubTabKey } from "./SubTabBar"

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
  const [subTab, setSubTab] = React.useState<SubTabKey>("resumo")
  const [unit, setUnit] = React.useState<"R$" | "pp">("pp")

  const recon = balancete?.reconciliacao
  const cob   = balancete?.cobertura
  const dq    = balancete?.data_quality
  const nodes = balancete?.nodes ?? []

  // Explicacao da variacao (apenas PDD entregue hoje — 2026-05-13).
  const explicacao = useExplicacaoVariacao(
    balancete?.fundo_id ?? null,
    balancete?.data_d_zero ?? null,
    { dataAnterior: balancete?.data_d_minus_1 ?? null },
  )

  const pdd = explicacao.data?.explanations.find(
    (e): e is PddExplanation => e.categoria === "pdd",
  )
  const diferimento = explicacao.data?.explanations.find(
    (e): e is DiferimentoExplanation => e.categoria === "diferimento",
  )
  const apropriacao = explicacao.data?.explanations.find(
    (e): e is ApropriacaoExplanation => e.categoria === "apropriacao",
  )

  // Pendentes — usado em multiplos lugares (banner sticky, chips, tone).
  const pendentesCount = cob?.rows_por_source.pendente ?? 0
  const pendentesValor = cob?.valor_por_source.pendente ?? 0
  const hasPendentes   = pendentesCount > 0

  // Quando ha pendente OU dataquality incompativel, numero primary vira
  // cinza — explicabilidade > sofisticacao (CLAUDE.md §14).
  const forceNeutral = hasPendentes || (dq != null && !dq.comparable)

  // Total de contas folha (nivel >= 3) para badge do sub-tab "Detalhe contabil".
  const contasFolha = React.useMemo(
    () => nodes.filter((n) => n.codigo != null && n.nivel >= 3).length,
    [nodes],
  )

  // ─── Chips do header ────────────────────────────────────────────────────
  // Ordem: snapshot parcial (prioritario) -> reconciliacao -> cobertura.
  const headerChips = React.useMemo<StatusHeadlineChip[]>(() => {
    const out: StatusHeadlineChip[] = []
    if (!recon || !cob) return out

    if (dq && !dq.comparable) {
      out.push({
        label: dq.reason ?? "Snapshot parcial — comparação não confiável",
        tone:  "error",
      })
    }

    const residuoPp =
      recon.pl_cota_sub_d1 !== 0
        ? Math.abs(recon.residuo) / Math.abs(recon.pl_cota_sub_d1)
        : 0
    if (residuoPp <= 0.001) {
      out.push({
        label: `Reconciliado · resíduo ${fmtBRLCompact.format(Math.abs(recon.residuo))}`,
        tone:  "ok",
      })
    } else if (residuoPp <= 0.01) {
      out.push({
        label: `Resíduo ${fmtBRLCompact.format(Math.abs(recon.residuo))}`,
        tone:  "warn",
      })
    } else {
      out.push({
        label: `Resíduo ${fmtBRLCompact.format(Math.abs(recon.residuo))} acima da tolerância`,
        tone:  "error",
      })
    }

    if (pendentesCount === 0) {
      out.push({ label: "Cobertura COSIF 100%", tone: "ok" })
    } else {
      out.push({
        label: `${pendentesCount} ${pendentesCount === 1 ? "papel sem COSIF" : "papéis sem COSIF"}`,
        tone:  "error",
      })
    }

    return out
  }, [recon, cob, dq, pendentesCount])

  // ─── Drivers para o BridgeCard + DriversCard ────────────────────────────
  // Hoje "eventos_contabeis" agrega PDD + Diferimento + Apropriacao.
  // Demais buckets (fluxo_caixa, movimento_carteira, marcacao_mercado)
  // ainda sao placeholders ate seus explainers entrarem.
  const driverInputs = React.useMemo<DriverInput[]>(() => {
    const list: DriverInput[] = []
    const eventosContabeis = buildDriverFromEventosContabeis({
      pdd,
      diferimento,
      apropriacao,
    })
    list.push(
      eventosContabeis ?? { id: "eventos_contabeis", delta: 0, placeholder: true },
    )
    list.push({ id: "fluxo_caixa",        delta: 0, placeholder: true })
    list.push({ id: "movimento_carteira", delta: 0, placeholder: true })
    list.push({ id: "marcacao_mercado",   delta: 0, placeholder: true })
    return list
  }, [pdd, diferimento, apropriacao])

  // BridgeDrivers — converte DriverInput pro shape do waterfall.
  // "Outros (nao classificado)" aparece quando indeterminado_brl > limiar.
  const bridgeDrivers = React.useMemo<BridgeDriver[]>(() => {
    const fromInput = (input: DriverInput): BridgeDriver => ({
      id:          input.id,
      label:       labelFromCategoryId(input.id),
      shortLabel:  shortLabelFromCategoryId(input.id),
      delta:       input.delta,
      placeholder: input.placeholder,
    })
    // Mesma ordem do handoff: eventos, fluxo, carteira, mtm
    const ordered = [
      driverInputs.find((d) => d.id === "eventos_contabeis"),
      driverInputs.find((d) => d.id === "fluxo_caixa"),
      driverInputs.find((d) => d.id === "movimento_carteira"),
      driverInputs.find((d) => d.id === "marcacao_mercado"),
    ].filter((x): x is DriverInput => x !== undefined)
    const out = ordered.map(fromInput)

    // Adiciona "Outros (nao classificado)" quando indeterminado_brl
    // representa mais que 1k em modulo (mostra o gap honestamente).
    const indeterminado = explicacao.data?.indeterminado_brl ?? 0
    const threshold = 1_000
    if (Math.abs(indeterminado) > threshold) {
      out.push({
        id:          "outros",
        label:       "Outros (não classificado)",
        shortLabel:  "Outros",
        delta:       indeterminado,
      })
    }
    return out
  }, [driverInputs, explicacao.data?.indeterminado_brl])

  // Ref para scroll do CTA "Ver pendentes" no banner
  const residuoCardRef = React.useRef<HTMLDivElement>(null)
  const scrollToResiduo = React.useCallback(() => {
    // Quando o user clica em "Ver pendentes" e estamos na sub-tab "Resumo",
    // a tabela COSIF nao esta montada -- pula pro sub-tab "Detalhe".
    setSubTab("detalhe")
    requestAnimationFrame(() => {
      residuoCardRef.current?.scrollIntoView({
        behavior: "smooth",
        block:    "start",
      })
    })
  }, [])

  // ─── Estados patologicos ────────────────────────────────────────────────

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

  // ─── Render principal ──────────────────────────────────────────────────

  return (
    <div className="flex flex-col gap-3">
      {/* 0. Banner sticky de pendentes — defesa C1 do incidente 2026-05-12.
          Aparece SO quando ha pendentes. CTA "Ver pendentes" alterna pro
          sub-tab "Detalhe" e da scroll. */}
      {hasPendentes && (
        <div className="sticky top-0 z-10 -mx-6 flex flex-wrap items-center gap-3 border-b border-red-200 bg-red-50 px-6 py-2.5 text-[13px] dark:border-red-900/40 dark:bg-red-950/40">
          <RiAlertLine
            className="size-4 shrink-0 text-red-600 dark:text-red-400"
            aria-hidden="true"
          />
          <span className="font-medium text-red-800 dark:text-red-200">
            {pendentesCount} {pendentesCount === 1 ? "papel" : "papéis"} sem classificação COSIF
          </span>
          <span className="text-red-700 dark:text-red-300">
            ({fmtBRLCompact.format(Math.abs(pendentesValor))} fora da árvore) — análise pode estar incompleta
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

      {/* 1. Status headline compacto (Z1) */}
      <StatusHeadlineCompact
        dataD0={balancete?.data_d_zero}
        plSubD0={recon?.pl_cota_sub_d0}
        deltaReal={recon?.delta_pl_cota_sub_real}
        deltaPct={recon?.delta_pct_sobre_d1}
        forceNeutral={forceNeutral}
        chips={headerChips}
        loading={loading && !balancete}
      />

      {/* 2. Sub-tab bar */}
      <SubTabBar
        value={subTab}
        onChange={setSubTab}
        contasCount={contasFolha}
        trailing={
          balancete?.data_d_zero
            ? `Snapshot · ${formatBR(balancete.data_d_zero)}`
            : undefined
        }
      />

      {/* 3. Conteudo do sub-tab */}
      {subTab === "resumo" ? (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1.42fr_1fr]">
          <div className="flex min-w-0 flex-col gap-3">
            <BridgeCard
              startTotal={recon?.pl_cota_sub_d1 ?? 0}
              endTotal={recon?.pl_cota_sub_d0 ?? 0}
              drivers={bridgeDrivers}
              dataD1={balancete?.data_d_minus_1 ?? ""}
              dataD0={balancete?.data_d_zero ?? ""}
              unit={unit}
              onUnitChange={setUnit}
              height={360}
            />
            <ReconStatusCard
              reconciliacao={recon}
              nodes={nodes}
            />
          </div>
          <DriversCard
            drivers={driverInputs}
            base={recon?.pl_cota_sub_d1}
          />
        </div>
      ) : (
        <div ref={residuoCardRef} className="scroll-mt-4">
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
        </div>
      )}

      {/* Drill-down — sheet de explicacao acessivel via Detalhe contabil. */}
      <CosifDrillSheet
        node={selectedNode}
        onClose={() => setSelectedNode(null)}
      />
    </div>
  )
}

// ─── helpers locais ─────────────────────────────────────────────────────────

function labelFromCategoryId(id: BridgeDriver["id"]): string {
  switch (id) {
    case "fluxo_caixa":        return "Fluxo de cotista"
    case "movimento_carteira": return "Carteira"
    case "eventos_contabeis":  return "Eventos"
    case "marcacao_mercado":   return "MtM"
    case "outros":             return "Outros"
  }
}
function shortLabelFromCategoryId(id: BridgeDriver["id"]): string {
  switch (id) {
    case "fluxo_caixa":        return "Fluxo"
    case "movimento_carteira": return "Carteira"
    case "eventos_contabeis":  return "Eventos"
    case "marcacao_mercado":   return "MtM"
    case "outros":             return "Outros"
  }
}

function formatBR(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  if (!m) return iso
  return `${m[3]}/${m[2]}/${m[1]}`
}
