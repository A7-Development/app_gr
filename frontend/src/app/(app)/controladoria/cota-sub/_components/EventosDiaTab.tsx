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
  FluxoCaixaExplanation,
  MovimentoCarteiraExplanation,
  MtmExplanation,
  OutrosExplanation,
  PddExplanation,
  RemuneracaoSrMezExplanation,
} from "@/lib/api-client"
import { useExplicacaoVariacao } from "@/lib/hooks/controladoria"

import { BalanceteDiarioTable } from "./BalanceteDiarioTable"
import {
  BridgeCard,
  type BridgeDriver,
} from "./BridgeCard"
import { CosifDrillSheet } from "./CosifDrillSheet"
import {
  buildDriverFromAjustesContabeis,
  buildDriverFromFluxoCaixa,
  buildDriverFromMovimentoCarteira,
  buildDriverFromMtm,
  buildDriverFromOutros,
  buildDriverFromPdd,
  buildDriverFromRemuneracaoSrMez,
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
  const fluxoCaixa = explicacao.data?.explanations.find(
    (e): e is FluxoCaixaExplanation => e.categoria === "fluxo_caixa",
  )
  const movimentoCarteira = explicacao.data?.explanations.find(
    (e): e is MovimentoCarteiraExplanation => e.categoria === "movimento_carteira",
  )
  const mtm = explicacao.data?.explanations.find(
    (e): e is MtmExplanation => e.categoria === "mtm",
  )
  const remuneracao = explicacao.data?.explanations.find(
    (e): e is RemuneracaoSrMezExplanation => e.categoria === "remuneracao_sr_mez",
  )
  const outros = explicacao.data?.explanations.find(
    (e): e is OutrosExplanation => e.categoria === "outros",
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
  // Status 2026-05-17: TODOS os 6 drivers entregues.
  //  - PDD (bucket proprio, rose)
  //  - Ajustes contabeis (diferimento + apropriacao, violet)
  //  - Fluxo de caixa do cotista (aporte/resgate Sub/Mez/Sr, emerald)
  //  - Movimento de carteira (liquidacao/aquisicao, blue) - INFORMACIONAL delta=0
  //  - Marcacao a mercado (renda fixa, amber) - Sub absorve direto
  //  - Remuneracao Sr/Mez (custo de subordinacao, rose) - Sub paga
  //
  // Fallback: quando o explainer ENTREGUE retorna undefined (sem evento no
  // dia), usar `empty: true` (nao `placeholder: true`) — sinaliza categoria
  // implementada mas dia trivial, render "Sem movimentacao no dia".
  const driverInputs = React.useMemo<DriverInput[]>(() => {
    const list: DriverInput[] = []
    list.push(
      pdd
        ? buildDriverFromPdd(pdd)
        : { id: "pdd", delta: 0, empty: true },
    )

    const ajustes = buildDriverFromAjustesContabeis({ diferimento, apropriacao })
    list.push(
      ajustes ?? { id: "ajustes_contabeis", delta: 0, empty: true },
    )

    list.push(
      fluxoCaixa
        ? buildDriverFromFluxoCaixa(fluxoCaixa)
        : { id: "fluxo_caixa", delta: 0, empty: true },
    )

    list.push(
      movimentoCarteira
        ? buildDriverFromMovimentoCarteira(movimentoCarteira)
        : { id: "movimento_carteira", delta: 0, empty: true },
    )

    list.push(
      mtm
        ? buildDriverFromMtm(mtm)
        : { id: "marcacao_mercado", delta: 0, empty: true },
    )

    list.push(
      remuneracao
        ? buildDriverFromRemuneracaoSrMez(remuneracao)
        : { id: "remuneracao_sr_mez", delta: 0, empty: true },
    )

    // Bucket "Nao explicado" (id="outros") — refactor 2026-05-17:
    // agora reflete APENAS folhas COSIF sem mapping em
    // `cosif_to_bucket.py`. Em regime estavel deve ser zero.
    // (O residuo MEC vs Contabil agora vai pro painel proprio de conciliacao,
    // nao mais pra este bucket.)
    if (outros) {
      list.push(buildDriverFromOutros(outros))
    }
    return list
  }, [
    pdd, diferimento, apropriacao, fluxoCaixa, movimentoCarteira, mtm, remuneracao, outros,
  ])

  // BridgeDrivers — converte DriverInput pro shape do waterfall.
  // "Outros (nao classificado)" aparece quando indeterminado_brl > limiar.
  // Labels do eixo X sao cognatos 1:1 dos titulos dos cards do DriversCard
  // (single source of truth — ver shortLabelFromCategoryId).
  const bridgeDrivers = React.useMemo<BridgeDriver[]>(() => {
    const fromInput = (input: DriverInput): BridgeDriver => {
      const sl = shortLabelFromCategoryId(input.id)
      return {
        id:           input.id,
        label:        labelFromCategoryId(input.id),
        shortLabel:   sl.line1,
        shortLabel2:  sl.line2,
        delta:        input.delta,
        placeholder:  input.placeholder,
      }
    }
    // Ordem fixa no waterfall: PDD, Ajustes, Fluxo, Carteira, MtM,
    // Remuneracao Sr/Mez, Outros (no fim, sempre que presente).
    const ordered = [
      driverInputs.find((d) => d.id === "pdd"),
      driverInputs.find((d) => d.id === "ajustes_contabeis"),
      driverInputs.find((d) => d.id === "fluxo_caixa"),
      driverInputs.find((d) => d.id === "movimento_carteira"),
      driverInputs.find((d) => d.id === "marcacao_mercado"),
      driverInputs.find((d) => d.id === "remuneracao_sr_mez"),
      driverInputs.find((d) => d.id === "outros"),
    ].filter((x): x is DriverInput => x !== undefined)
    return ordered.map(fromInput)
  }, [driverInputs])

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

      {/* 1. Status headline compacto (Z1) — 3 deltas.
            ATENCAO a nomenclatura do backend (balancete_diario.py:484-485):
              - `delta_pl_cota_sub_real`     = MEC direto (verdade do administrador)
              - `delta_pl_cota_sub_esperado` = derivado contabil (ΔTotal − Sr − Mez)
            "Real" no schema = MEC apurado; "Esperado" = inferencia contabil.
            UI mostra:
              - Variacao apurada (MEC) ← delta_pl_cota_sub_real
              - Variacao calculada (contabil) ← delta_pl_cota_sub_esperado
              - Nao-explicado ← residuo = real − esperado. */}
      <StatusHeadlineCompact
        dataD0={balancete?.data_d_zero}
        plSubD0={recon?.pl_cota_sub_d0}
        deltaApuradoMec={recon?.delta_pl_cota_sub_real}
        deltaApuradoPct={recon?.delta_pct_sobre_d1}
        deltaCalculadoReal={recon?.delta_pl_cota_sub_esperado}
        deltaCalculadoPct={
          recon && recon.pl_cota_sub_d1 !== 0
            ? (recon.delta_pl_cota_sub_esperado / recon.pl_cota_sub_d1) * 100
            : undefined
        }
        residuo={recon?.residuo}
        baseResiduo={recon?.pl_cota_sub_d1}
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

      {/* 3. Conteudo do sub-tab.
          Layout split 50/50: BridgeCard + DriversCard com mesma largura.
          O `minmax(0,1fr)` em AMBAS impede que o conteudo intrinseco
          (evidencias PDD/Ajustes expandidas) infle qualquer coluna alem
          da proporcao — sem isso, a direita engordava ao expandir e
          empurrava a esquerda (resize visual confuso). */}
      {subTab === "resumo" ? (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
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
          <div className="min-w-0">
            <DriversCard
              drivers={driverInputs}
              base={recon?.pl_cota_sub_d1}
              onInvestigate={() => setSubTab("detalhe")}
            />
          </div>
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

// Labels do eixo X do waterfall — single source of truth pra textos que
// aparecem na pagina cota-sub. Cognato 1:1 com os titulos exibidos no
// DriversCard (rail direito). Quando o nome tem 2 palavras e nao cabe em
// 1 linha do eixo X, quebra em 2 linhas (line1 + line2) via tspan no SVG.
//
// Regra: o que o usuario le no card a direita = o que o usuario le no
// eixo X do waterfall (uma label NUNCA difere da outra).
function labelFromCategoryId(id: BridgeDriver["id"]): string {
  switch (id) {
    case "pdd":                return "PDD"
    case "ajustes_contabeis":  return "Ajustes contábeis"
    case "fluxo_caixa":        return "Aporte e resgate"
    case "movimento_carteira": return "Movimento de carteira"
    case "marcacao_mercado":   return "Renda Fixa"
    case "remuneracao_sr_mez": return "Remuneração Sr/Mez"
    case "outros":             return "Não explicado"
  }
}

type ShortAxisLabel = { line1: string; line2?: string }
function shortLabelFromCategoryId(id: BridgeDriver["id"]): ShortAxisLabel {
  switch (id) {
    case "pdd":                return { line1: "PDD" }
    case "ajustes_contabeis":  return { line1: "Ajustes",        line2: "contábeis" }
    case "fluxo_caixa":        return { line1: "Aporte",         line2: "e resgate" }
    case "movimento_carteira": return { line1: "Movimento",      line2: "de carteira" }
    case "marcacao_mercado":   return { line1: "Renda",          line2: "Fixa" }
    case "remuneracao_sr_mez": return { line1: "Remuneração",    line2: "Sr/Mez" }
    case "outros":             return { line1: "Não",            line2: "explicado" }
  }
}

function formatBR(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  if (!m) return iso
  return `${m[3]}/${m[2]}/${m[1]}`
}
