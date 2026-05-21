// src/app/(app)/bi/operacoes4/page.tsx
//
// BI · Mes Corrente · operações (controladoria) — pagina /bi/operacoes4.
//
// Reorienta /bi/operacoes3 pra responder perguntas que chegam da equipe
// de controladoria sobre o mes em curso. Diferenca chave vs operacoes3:
//
//   - L1 KpiStrip: 4 cards (sem Potencial — vai pra L2 direita)
//   - L3 NOVO:     Composicao da receita + Yield efetivo por DU
//                  (regime CAIXA, 4 buckets, via /bi/operacoes4/lens-receitas)
//
// Reusa o resto de operacoes3 sem refator: HeroVopMes, TabelaCedentesMtd,
// DecomposicaoAvancada, AIPanel. Convive em paralelo — sidebar agrupa as
// 3 variantes ("Mes corrente · antigo / novo / operacoes") sob parent
// "Operações" (CLAUDE.md §11.6).
//
// Quando estabilizar, /bi/operacoes3 e /bi/operacoes4 convergem; ate la,
// este arquivo e a iteracao "controladoria-aware" e operacoes3 fica como
// referencia.

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import {
  RiCalendarEventLine,
  RiCalendarLine,
  RiCheckLine,
  RiRefreshLine,
} from "@remixicon/react"
import { toast } from "sonner"

import { cx } from "@/lib/utils"
import { Button } from "@/components/tremor/Button"
import { Card } from "@/components/tremor/Card"
import { Checkbox } from "@/components/tremor/Checkbox"

import { PageHeader } from "@/design-system/components/PageHeader"
import { DashboardHeaderActions } from "@/design-system/components/DashboardHeaderActions"
import {
  FilterChip,
  MoreFiltersButton,
} from "@/design-system/components/FilterBar"
import { InsightStrip } from "@/design-system/components/InsightStrip"
import { KpiCard, KpiStrip } from "@/design-system/components"
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
import { useBiFilters, type PresetKey } from "@/lib/hooks/useBiFilters"
import { biMetadata, biOperacoes2 } from "@/lib/api-client"
import type {
  Operacoes2CedenteMtdItem,
  Operacoes2Dimension,
  Operacoes4LensReceitasData,
  Operacoes4ReceitaTipo,
} from "@/lib/api-client"

// Reuso direto de componentes de operacoes3 — co-evoluem com aquela pagina
// enquanto operacoes4 e a iteracao "controladoria-aware". Quando uma das
// duas paginas mudar de forma incompativel, promovemos os shared a
// `src/app/(app)/bi/_components/` ou ao design-system.
import { TabelaCedentesMtd } from "../operacoes3/_components/TabelaCedentesMtd"

import { L3CardsRow } from "./_components/L3CardsRow"
import { MixDeProdutosCard } from "./_components/MixDeProdutosCard"
import { VopDiarioCard } from "./_components/VopDiarioCard"

import { DrillDownSheet } from "@/design-system/components/DrillDownSheet"

import { DrillOperacoesDoDia } from "../operacoes3/_components/DrillOperacoesDoDia"
import { DrillMovimentoContent, DrillReceitaTipoContent } from "./_components/DrillSheets"
import { MovementStack } from "./_components/MovementStack"

const PRESET_OPTIONS: ReadonlyArray<{ key: PresetKey; label: string }> = [
  { key: "ytd", label: "Ano até hoje" },
  { key: "3m", label: "Últimos 3 meses" },
  { key: "6m", label: "Últimos 6 meses" },
  { key: "12m", label: "Últimos 12 meses" },
  { key: "24m", label: "Últimos 24 meses" },
  { key: "36m", label: "Últimos 36 meses" },
  { key: "all", label: "Todo histórico" },
]
const PRESET_LABEL_MAP: Record<PresetKey, string> = Object.fromEntries(
  PRESET_OPTIONS.map((o) => [o.key, o.label]),
) as Record<PresetKey, string>

export default function Operacoes4Page() {
  const dataMinimaQuery = useQuery({
    queryKey: ["bi", "metadata", "data-minima"],
    queryFn: () => biMetadata.dataMinima(),
    staleTime: 6 * 60 * 60 * 1000,
  })
  const dataMinima = dataMinimaQuery.data?.data_minima ?? undefined

  const { filtersWithFocus, preset, setFilter, resetFilters } =
    useBiFilters(dataMinima)

  const uasQuery = useQuery({
    queryKey: ["bi", "metadata", "uas"],
    queryFn: () => biMetadata.uas(),
    staleTime: 60 * 60 * 1000,
  })
  const produtosQuery = useQuery({
    queryKey: ["bi", "metadata", "produtos"],
    queryFn: () => biMetadata.produtos(),
    staleTime: 60 * 60 * 1000,
  })
  const uaOptions = React.useMemo(
    () =>
      (uasQuery.data ?? []).map((u) => ({
        value: String(u.id),
        label: u.nome,
      })),
    [uasQuery.data],
  )
  const produtoOptions = React.useMemo(
    () =>
      (produtosQuery.data ?? []).map((p) => ({
        value: p.sigla,
        label: `${p.nome} (${p.sigla})`,
      })),
    [produtosQuery.data],
  )

  // Em PR1 dimension fica fixa em "produto". PR2 reintroduz SegmentSwitch
  // Produto|UA dentro do DrillDrivers drawer (em vez de no hero L2).
  const dimension: Operacoes2Dimension = "produto"

  // Bundle v3 — alimenta L1 (termometro -> 4 KPIs), L2 (VOP + Mix),
  // L3 card 4 (composicao via lensReceitas separada).
  const q = useQuery({
    queryKey: ["bi", "operacoes4", "aba3", filtersWithFocus, dimension],
    queryFn: () => biOperacoes2.abaMesCorrenteV3(filtersWithFocus, dimension),
  })
  const bundle = q.data?.data

  // AI hooks (mesmo padrao de operacoes3).
  const quotaQ = useAIQuota()
  const [conversationId, setConversationId] = React.useState<string | null>(null)
  const insightsQ = useAIInsights({
    page: "/bi/operacoes4",
    period: preset ?? "12m",
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
      page: "BI · Mês corrente · operações",
      period: preset ?? "custom",
      filters: [
        produtosFilterLabel(filtersWithFocus.produtoSigla),
        uasFilterLabel(filtersWithFocus.uaId, uaOptions),
      ]
        .filter(Boolean)
        .join(", ") || "Nenhum",
    }),
    [preset, filtersWithFocus.produtoSigla, filtersWithFocus.uaId, uaOptions],
  )

  const insightStripItems = React.useMemo(
    () => insights.map((ins, idx) => ({ id: String(idx), text: ins.text })),
    [insights],
  )

  const [scrollRef, scrolled] = useScrollShadow<HTMLDivElement>()
  const handleShare = React.useCallback(() => toast.info("Compartilhar — em breve"), [])
  const handleExport = React.useCallback(() => toast.info("Exportar — em breve"), [])

  // ─── Drill state (PR4) ──────────────────────────────────────────────────
  // Modelado como discriminated union — apenas 1 drill aberto por vez.
  type DrillState =
    | { kind: "dia"; dataISO: string }
    | { kind: "receita"; bucketIdx: number; total_mtd: number; total_parity: number }
    | {
        kind: "movimento"
        categoria: "novos" | "sumidos" | "movers"
        items: Operacoes2CedenteMtdItem[]
      }
    | null
  const [drill, setDrill] = React.useState<DrillState>(null)

  // Recupera o bundle de lens-receitas via cache do React Query para os
  // drills da composicao (mesma queryKey que ReceitasSection usa).
  const lensReceitasQ = useQuery<{ data: Operacoes4LensReceitasData }>({
    queryKey: ["bi", "operacoes4", "lens-receitas", filtersWithFocus],
    enabled: false, // ReceitasSection ja faz o fetch — aqui so leio do cache
  })

  const handleBucketClick = React.useCallback(
    (tipo: Operacoes4ReceitaTipo) => {
      const data = lensReceitasQ.data?.data
      if (!data) return
      const bucketIdx = data.composicao.findIndex((c) => c.tipo === tipo)
      if (bucketIdx < 0) return
      setDrill({
        kind: "receita",
        bucketIdx,
        total_mtd:
          typeof data.total_mtd === "string"
            ? Number(data.total_mtd)
            : data.total_mtd,
        total_parity:
          typeof data.total_parity === "string"
            ? Number(data.total_parity)
            : data.total_parity,
      })
    },
    [lensReceitasQ.data],
  )

  const drillTitle =
    drill?.kind === "dia"
      ? "Operações do dia"
      : drill?.kind === "receita"
        ? "Receita por tipo"
        : drill?.kind === "movimento"
          ? "Cedentes"
          : "Detalhe"

  return (
    <div className="flex h-[calc(100vh-3rem)] overflow-hidden">
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Title row */}
        <div className="shrink-0 bg-white px-6 pt-3.5 pb-3 dark:bg-gray-950">
          <PageHeader
            title="BI · Mês corrente · operações"
            info='Lente alternativa do mes corrente reorientada para perguntas da controladoria. Regime caixa (wh_operacao) — 4 buckets de receita, yield efetivo por DU. Multa, mora, cobranca e aditivo nao aparecem aqui (sao pos-cessao).'
            subtitle={pageHeaderSubtitle(bundle)}
            actions={
              <div className="flex items-center gap-2">
                {bundle?.termometro?.vop?.mes_label && (
                  <MesReferenciaPill mesLabel={bundle.termometro.vop.mes_label} />
                )}
                <AIQuotaIndicator
                  quota={quotaQ.data}
                  loading={quotaQ.isLoading}
                />
                <DashboardHeaderActions
                  ai={{ open: ai.open, onToggle: ai.toggle }}
                  onShare={handleShare}
                  onExport={handleExport}
                />
              </div>
            }
          />
        </div>

        {/* Toolbar de filtros */}
        <div
          className={cx(
            "shrink-0 border-b border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
            scrolled && "scroll-shadow",
          )}
        >
          <div className="flex h-[52px] items-center gap-2 px-6">
            <FilterChip
              label="Período"
              value={preset ? PRESET_LABEL_MAP[preset] : "Personalizado"}
              active={preset !== null && preset !== "12m"}
              icon={RiCalendarLine}
            >
              <div className="py-1">
                {PRESET_OPTIONS.map((opt) => (
                  <button
                    key={opt.key}
                    type="button"
                    onClick={() => setFilter({ preset: opt.key })}
                    className={cx(
                      "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                      preset === opt.key
                        ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                        : "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800",
                    )}
                  >
                    <span className="flex-1 text-left">{opt.label}</span>
                    {preset === opt.key && (
                      <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />
                    )}
                  </button>
                ))}
              </div>
            </FilterChip>

            <FilterChip
              label="Produto"
              value={multiLabel(filtersWithFocus.produtoSigla, produtoOptions)}
              active={(filtersWithFocus.produtoSigla?.length ?? 0) > 0}
            >
              <MultiCheckList
                options={produtoOptions}
                selected={filtersWithFocus.produtoSigla ?? []}
                onChange={(next) =>
                  setFilter({ produtoSigla: next.length > 0 ? next : undefined })
                }
              />
            </FilterChip>

            <FilterChip
              label="UA"
              value={multiLabel(
                (filtersWithFocus.uaId ?? []).map(String),
                uaOptions,
              )}
              active={(filtersWithFocus.uaId?.length ?? 0) > 0}
            >
              <MultiCheckList
                options={uaOptions}
                selected={(filtersWithFocus.uaId ?? []).map(String)}
                onChange={(next) =>
                  setFilter({
                    uaId:
                      next.length > 0
                        ? next.map((x) => Number(x)).filter(Number.isFinite)
                        : undefined,
                  })
                }
              />
            </FilterChip>

            <MoreFiltersButton />

            <Button
              variant="ghost"
              onClick={resetFilters}
              disabled={!hasFiltrosAtivos(preset, filtersWithFocus)}
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

        {/* InsightStrip */}
        <div className="shrink-0 px-6 pt-3">
          <InsightStrip insights={insightStripItems} />
        </div>

        {/* Conteudo */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-4">
          <div className="flex flex-col gap-4">
            {q.isLoading && <PaginaSkeleton />}
            {q.isError && (
              <Card className={cx(cardTokens.body, "py-12 text-center")}>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Não foi possível carregar a Visão Mês Corrente.
                </p>
                <Button
                  variant="ghost"
                  className="mt-2"
                  onClick={() => q.refetch()}
                >
                  Tentar novamente
                </Button>
              </Card>
            )}
            {bundle && (
              <>
                {/* L1 — 4 KPIs compact (canonico, ver handoff 2026-05-21) */}
                <KpiStrip cols={4}>
                  <KpiCard
                    variant="compact"
                    label="VOP"
                    value={formatKpiValor(bundle.termometro.vop)}
                    sub={bundle.termometro.vop.mes_label}
                    delta={kpiDelta(bundle.termometro.vop.delta_vop_du_pct)}
                    deltaSub="VOP-DU"
                  />
                  <KpiCard
                    variant="compact"
                    label="Receita"
                    value={formatKpiValor(bundle.termometro.receita)}
                    sub={bundle.termometro.receita.mes_label}
                    delta={kpiDelta(bundle.termometro.receita.delta_vop_du_pct)}
                    deltaSub="VOP-DU"
                  />
                  <KpiCard
                    variant="compact"
                    label="Taxa média"
                    value={formatKpiValor(bundle.termometro.taxa)}
                    sub={bundle.termometro.taxa.mes_label}
                    delta={kpiDelta(bundle.termometro.taxa.delta_vop_du_pct)}
                    deltaSub="VOP-DU"
                  />
                  <KpiCard
                    variant="compact"
                    label="Prazo médio"
                    value={formatKpiValor(bundle.termometro.prazo)}
                    sub={bundle.termometro.prazo.mes_label}
                    delta={kpiDelta(bundle.termometro.prazo.delta_vop_du_pct)}
                    deltaSub="VOP-DU"
                  />
                </KpiStrip>
                {bundle.termometro.vop.valor === 0 && (
                  <p className="text-[11px] italic text-gray-500 dark:text-gray-400">
                    Aguardando primeiros DUs do mês — KPIs ainda zerados.
                  </p>
                )}

                {/* L2 — 50/50: VOP Diário (esq) + Mix de produtos (dir) */}
                <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                  <VopDiarioCard
                    vopDiario={bundle.vop_diario}
                    vopDiarioPorUa={bundle.vop_diario_por_ua}
                    vopMtdPorUa={bundle.vop_mtd_por_ua}
                    vop={bundle.vop}
                    duDecorridos={bundle.du_decorridos}
                    duTotais={bundle.du_totais_mes}
                    onPointClick={(dataISO) =>
                      setDrill({ kind: "dia", dataISO })
                    }
                  />
                  <MixDeProdutosCard mix={bundle.mix} />
                </section>

                {/* L3 — 4 cards 25% (Hist Taxas · Bar Taxa/produto · Hist Prazo · Composição) */}
                <L3CardsRow
                  filters={filtersWithFocus}
                  onBucketTaxasClick={(bucketIdx) =>
                    // PR1 stub — bucket drill drawer entra em PR2.
                    // Reusa estrutura de receita pra abrir DrillDownSheet generico.
                    handleBucketClick(
                      ["desagio", "tarifa_cessao", "tarifas_operacionais", "outras"][
                        Math.min(bucketIdx, 3)
                      ] as never,
                    )
                  }
                />

                {/* L4 — Cedentes 75/25 (sem mudancas vs producao) */}
                <section className="grid grid-cols-1 gap-4 xl:grid-cols-4">
                  <div className="xl:col-span-3">
                    <TabelaCedentesMtd />
                  </div>
                  <div>
                    <MovementStack
                      filters={filtersWithFocus}
                      onCardClick={(categoria, items) =>
                        setDrill({ kind: "movimento", categoria, items })
                      }
                    />
                  </div>
                </section>

                {/* Footer com metadata de comparacao */}
                <p className="text-[11px] text-gray-500 dark:text-gray-500">
                  {bundle.comparacao_label_pt}
                </p>
              </>
            )}
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

      {/* DrillDownSheet unico — conteudo dinamico por kind. */}
      <DrillDownSheet
        open={drill !== null}
        onClose={() => setDrill(null)}
        size="lg"
        title={drillTitle}
      >
        {drill?.kind === "dia" && (
          <DrillOperacoesDoDia dataISO={drill.dataISO} />
        )}
        {drill?.kind === "receita" &&
          lensReceitasQ.data?.data?.composicao[drill.bucketIdx] && (
            <DrillReceitaTipoContent
              bucket={lensReceitasQ.data.data.composicao[drill.bucketIdx]}
              total_mtd={drill.total_mtd}
              total_parity={drill.total_parity}
            />
          )}
        {drill?.kind === "movimento" && (
          <DrillMovimentoContent
            categoria={drill.categoria}
            items={drill.items}
          />
        )}
      </DrillDownSheet>
    </div>
  )
}

// ─── PageHeader pill + subtitle helpers ────────────────────────────────────

function MesReferenciaPill({ mesLabel }: { mesLabel: string }) {
  // Converte "mai/26" → "Maio/2026" pra exibição na pill canônica.
  const displayLabel = formatMesReferenciaLabel(mesLabel)
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border border-blue-200 bg-blue-50 px-2.5 py-0.5 dark:border-blue-500/30 dark:bg-blue-500/10"
      title="Mês de referência dos KPIs"
    >
      <RiCalendarEventLine
        className="size-3 text-blue-600 dark:text-blue-400"
        aria-hidden
      />
      <span className="text-[10px] font-medium uppercase tracking-wider text-blue-600/80 dark:text-blue-400/80">
        Mês de referência
      </span>
      <span className="text-[12px] font-semibold tabular-nums text-blue-700 dark:text-blue-300">
        {displayLabel}
      </span>
    </span>
  )
}

const _MESES_LONGO_PT = [
  "Janeiro",
  "Fevereiro",
  "Março",
  "Abril",
  "Maio",
  "Junho",
  "Julho",
  "Agosto",
  "Setembro",
  "Outubro",
  "Novembro",
  "Dezembro",
]
function formatMesReferenciaLabel(mesLabel: string): string {
  // Aceita "mai/26", "mai/2026", "MAR/26" — converte para "Maio/2026".
  const match = mesLabel.match(/^([a-z]{3,})\.?\/(\d{2,4})$/i)
  if (!match) return mesLabel
  const mes3 = match[1].toLowerCase()
  const anoStr = match[2]
  const idx = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"].indexOf(mes3)
  if (idx < 0) return mesLabel
  const ano = anoStr.length === 2 ? `20${anoStr}` : anoStr
  return `${_MESES_LONGO_PT[idx]}/${ano}`
}

function pageHeaderSubtitle(
  bundle: { du_decorridos: number; du_totais_mes: number } | undefined,
): string {
  if (!bundle) return ""
  const dec = bundle.du_decorridos
  const tot = bundle.du_totais_mes
  const falta = Math.max(0, tot - dec)
  return `${dec} DU${dec === 1 ? "" : "s"} decorridos de ${tot} · faltam ${falta} DU${falta === 1 ? "" : "s"}`
}

// ─── KPI helpers (L1) ──────────────────────────────────────────────────────

const _fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 2,
})

function formatKpiValor(
  cell: { valor: number; unidade: string },
): string {
  switch (cell.unidade) {
    case "BRL":
      return _fmtBRL.format(cell.valor)
    case "%":
      return `${cell.valor.toFixed(1).replace(".", ",")}%`
    case "dias":
      return `${cell.valor.toFixed(1).replace(".", ",")} d`
    default:
      return String(cell.valor)
  }
}

function kpiDelta(
  pct: number | null | undefined,
): { value: number; suffix: string } | undefined {
  return pct == null ? undefined : { value: pct, suffix: "%" }
}

// ─── Skeleton ──────────────────────────────────────────────────────────────

function PaginaSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <div className="h-24 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900" />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <div className="h-72 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900 xl:col-span-2" />
        <div className="h-72 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900" />
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="h-72 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900" />
        <div className="h-72 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900" />
      </div>
    </div>
  )
}

// ─── Helpers (clones diretos de operacoes3 ate promovermos a shared) ──────

function produtosFilterLabel(produtos: string[] | undefined): string | false {
  if (!produtos || produtos.length === 0) return false
  if (produtos.length <= 2) return `Produto: ${produtos.join(", ")}`
  return `Produto: ${produtos.length} selecionados`
}

function uasFilterLabel(
  uaIds: number[] | undefined,
  options: { value: string; label: string }[],
): string | false {
  if (!uaIds || uaIds.length === 0) return false
  if (uaIds.length <= 2) {
    const labels = uaIds.map((id) => {
      const opt = options.find((o) => o.value === String(id))
      return opt?.label ?? `UA ${id}`
    })
    return `UA: ${labels.join(", ")}`
  }
  return `UA: ${uaIds.length} selecionadas`
}

type MultiOption = { value: string; label: string }

function multiLabel(
  selected: string[] | undefined,
  options: MultiOption[],
  placeholder = "Todos",
): string {
  if (!selected || selected.length === 0) return placeholder
  if (selected.length === 1) {
    const opt = options.find((o) => o.value === selected[0])
    return opt?.label ?? selected[0]
  }
  if (options.length > 0 && selected.length === options.length) return "Todos"
  return `${selected.length} selecionados`
}

function hasFiltrosAtivos(
  preset: PresetKey | null,
  filtros: { produtoSigla?: string[]; uaId?: number[] },
): boolean {
  if (preset !== null && preset !== "12m") return true
  if (filtros.produtoSigla && filtros.produtoSigla.length > 0) return true
  if (filtros.uaId && filtros.uaId.length > 0) return true
  return false
}

function MultiCheckList({
  options,
  selected,
  onChange,
}: {
  options: MultiOption[]
  selected: string[]
  onChange: (next: string[]) => void
}) {
  const set = React.useMemo(() => new Set(selected), [selected])
  const toggle = React.useCallback(
    (value: string, checked: boolean) => {
      const next = new Set(set)
      if (checked) next.add(value)
      else next.delete(value)
      onChange(Array.from(next))
    },
    [set, onChange],
  )
  return (
    <div className="max-h-72 overflow-y-auto py-1">
      {options.length === 0 && (
        <p className="px-3 py-2 text-xs text-gray-400 dark:text-gray-600">
          Nenhuma opção disponível.
        </p>
      )}
      {options.map((opt) => {
        const isChecked = set.has(opt.value)
        return (
          <label
            key={opt.value}
            className="flex cursor-pointer items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            <Checkbox
              checked={isChecked}
              onCheckedChange={(c) => toggle(opt.value, c === true)}
            />
            <span className="flex-1 text-gray-700 dark:text-gray-300">
              {opt.label}
            </span>
          </label>
        )
      })}
    </div>
  )
}
