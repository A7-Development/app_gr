// src/app/(app)/bi/operacoes3/page.tsx
//
// BI · Mes Corrente (novo) — pagina reorientada pro socio-diretor.
//
// Responde "como ta o mes? onde estou ganhando, onde estou perdendo?" em
// uma piscadela. Vive em paralelo com /bi/operacoes2 ate ser promovida.
//
// Estrutura final (PR1):
//   L1 Termometro: 5 KpiCards canonicos (VOP/Receita/Taxa/Prazo com 2 deltas,
//      Potencial absoluto).
//   L2 Hero VOP do mes: VOP Diario (col-span-2 ~66%) + VOP Waterfall
//      (col-span-1 ~33%). Click em barra do diario abre DrillDownSheet
//      com operacoes do dia.
//   L5 Decomposicao avancada: collapsible (default fechada) com Receita,
//      Taxa, Prazo, Mix, Concentracao.
//
// PRs seguintes:
//   L3 Movimentos (Cedentes / Produtos / Taxas / Prazos) — PR2
//   L4 Sinais discretos (dia fora da curva, recompras, concentracao) — PR3

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import {
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
import type { Operacoes2Dimension } from "@/lib/api-client"

import { DecomposicaoAvancada } from "./_components/DecomposicaoAvancada"
import { HeroVopMes } from "./_components/HeroVopMes"
import { TabelaCedentesMtd } from "./_components/TabelaCedentesMtd"
import { TermometroStrip } from "./_components/TermometroStrip"

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

export default function Operacoes3Page() {
  // ─── Filtros reais via useBiFilters ─────────────────────────────────────
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

  // Dimension do VOP Waterfall (Produto | UA) — controlado pelo SegmentSwitch
  // dentro do HeroVopMes. Refetch automatico via queryKey.
  const [dimension, setDimension] = React.useState<Operacoes2Dimension>("produto")

  // ─── Bundle v3 ──────────────────────────────────────────────────────────
  const q = useQuery({
    queryKey: ["bi", "operacoes3", "aba3", filtersWithFocus, dimension],
    queryFn: () => biOperacoes2.abaMesCorrenteV3(filtersWithFocus, dimension),
  })
  const bundle = q.data?.data

  // ─── AI hooks ───────────────────────────────────────────────────────────
  const quotaQ = useAIQuota()
  const [conversationId, setConversationId] = React.useState<string | null>(null)
  const insightsQ = useAIInsights({
    page: "/bi/operacoes3",
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
      page: "BI · Mês corrente (novo)",
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

  return (
    <div className="flex h-[calc(100vh-3rem)] overflow-hidden">
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Title row */}
        <div className="shrink-0 bg-white px-6 pt-3.5 pb-3 dark:bg-gray-950">
          <PageHeader
            title="BI · Mês corrente"
            info='Visao do socio-diretor: "como ta o mes? onde tô ganhando, onde tô perdendo?". Termometro de 5 KPIs com dupla comparacao (VOP-DU paridade DU + MOM normalizado), hero VOP diario + waterfall, e decomposicao avancada colapsavel.'
            subtitle="BI · Mês corrente (novo)"
            actions={
              <div className="flex items-center gap-2">
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
                {/* L1 — Termometro */}
                <TermometroStrip data={bundle.termometro} />

                {/* L2 — Hero VOP do mes */}
                <HeroVopMes
                  vopDiario={bundle.vop_diario}
                  vopDiarioPorUa={bundle.vop_diario_por_ua}
                  vopMtdPorUa={bundle.vop_mtd_por_ua}
                  vop={bundle.vop}
                  dimension={dimension}
                  onDimensionChange={setDimension}
                />

                {/* L3 — Tabela narrativa de cedentes MTD */}
                <TabelaCedentesMtd />

                {/* L5 — Decomposicao avancada (collapsible, fechada default) */}
                <DecomposicaoAvancada
                  receita={bundle.receita}
                  receitaProjecao={bundle.receita_projecao}
                  taxa={bundle.taxa}
                  prazo={bundle.prazo}
                  mix={bundle.mix}
                  concentracao={bundle.concentracao}
                />

                {/* Footer com metadata de comparacao */}
                <p className="text-[11px] text-gray-500 dark:text-gray-500">
                  {bundle.comparacao_label_pt}
                </p>
              </>
            )}
          </div>
        </div>

        {/* ProvenanceFooter */}
        <ProvenanceFooter provenance={q.data?.provenance} />
      </div>

      {/* AI Panel */}
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

// ─── Skeleton ──────────────────────────────────────────────────────────────

function PaginaSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <div className="h-24 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900" />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <div className="h-72 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900 xl:col-span-2" />
        <div className="h-72 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900" />
      </div>
      <div className="h-12 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900" />
    </div>
  )
}

// ─── Helpers reaproveitados de operacoes2/page.tsx ────────────────────────

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
