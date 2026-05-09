// src/app/(app)/bi/operacoes2/page.tsx
//
// BI · Operacoes — pagina derivada do pattern canonico `DashboardBiPadrao`
// (`design-system/patterns/DashboardBiPadrao.tsx`) com divergencias
// documentadas abaixo.
//
// Chrome preservado: title row, toolbar 52px com tabs+filtros, InsightStrip,
// ProvenanceFooter, AIPanel, DrillDownSheet.
//
// AJUSTES vs `DashboardBiPadrao`:
//   1. Dados dos KPIs: 5 indicadores reais de Operacoes (VOP, Taxa, Prazo,
//      Produto Top, Receita) via `biOperacoes2.kpiStrip(filters)`.
//   2. Apresentacao da area util: charts ECharts em <AbaVolumeRitmo /> (Aba 1).
//   3. Filtros reais: Periodo (preset) + Produto (multi) + UA (multi) via
//      `useBiFilters` (substituem o mock fundo/tipo).
//   4. ProvenanceFooter: do `components/bi/` (carrega `Provenance` real do
//      backend) em vez do mock do DS — mesma anatomia visual.
//   5. KpiStrip page-level removido em 2026-05-09 — diagnostico em
//      `docs/bi-patterns-presentacao-dados.md` §1.2: 4 dos 5 tiles
//      duplicavam KPIs decompostos pelos cards das abas. Numeros migram para
//      o `headerKpi` de cada chart-card das abas (refactor em sequencia).
//      Query `kpiStripQuery` continua viva — alimenta o LLM via `kpisBlock`
//      e o ProvenanceFooter via `provenance`.

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
import {
  TabNavigation,
  TabNavigationLink,
} from "@/components/tremor/TabNavigation"

import { PageHeader } from "@/design-system/components/PageHeader"
import { DashboardHeaderActions } from "@/design-system/components/DashboardHeaderActions"
import {
  FilterChip,
  MoreFiltersButton,
} from "@/design-system/components/FilterBar"
import { Checkbox } from "@/components/tremor/Checkbox"
import { InsightStrip } from "@/design-system/components/InsightStrip"
import { DrillDownSheet } from "@/design-system/components/DrillDownSheet"
import {
  AIPanel,
  useAIPanel,
  type AIInsight,
} from "@/design-system/components/AIPanel"
import { AIQuotaIndicator } from "@/design-system/components/AIQuotaIndicator"

import { ProvenanceFooter } from "@/components/bi/ProvenanceFooter"
import { useScrollShadow } from "@/lib/hooks/use-scroll-shadow"
import { useAIChat, useAIInsights, useAIQuota } from "@/lib/hooks/ai"
import { useBiFilters, type PresetKey } from "@/lib/hooks/useBiFilters"
import { biMetadata, biOperacoes2 } from "@/lib/api-client"

import { AbaMesCorrente } from "./_components/AbaMesCorrente"
import { AbaProdutosPricing } from "./_components/AbaProdutosPricing"
import { AbaVolumeRitmo } from "./_components/AbaVolumeRitmo"

// ───────────────────────────────────────────────────────────────────────────
// Tabs L3 (CLAUDE.md §11.6)
// ───────────────────────────────────────────────────────────────────────────
//
// Aba "Mes corrente" e a primeira (default) — responde "como esta indo o
// mes" via variance decomposition em 6 KPIs (VOP, Receita, Taxa-PVM,
// Prazo-PVM, Mix-Dumbbell, Concentracao-HHI). Decisao 2026-05-08.

const TABS = [
  { key: "mes-corrente", label: "Mês corrente" },
  { key: "volume-ritmo", label: "Volume & Ritmo" },
  { key: "produtos-pricing", label: "Produtos & Pricing" },
  { key: "receita", label: "Receita" },
  { key: "cedentes-concentracao", label: "Cedentes & Concentração" },
] as const

type TabKey = (typeof TABS)[number]["key"]

// ───────────────────────────────────────────────────────────────────────────
// Periodo presets para o FilterChip "Periodo"
// ───────────────────────────────────────────────────────────────────────────

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

// ───────────────────────────────────────────────────────────────────────────
// Formatadores
// ───────────────────────────────────────────────────────────────────────────

const fmtBRLCompact = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 2,
})
const fmtPct2 = (v: number) => `${v.toFixed(2).replace(".", ",")}%`
const fmtDays = (v: number) => `${v.toFixed(1).replace(".", ",")} d`
const fmtSharePct = (v: number) => `${v.toFixed(1).replace(".", ",")}%`

// ───────────────────────────────────────────────────────────────────────────
// Pagina
// ───────────────────────────────────────────────────────────────────────────

export default function Operacoes2Page() {
  // ─── Estado local: tab + AI conversa + drill-down + busca ────────────────
  const [activeTab, setActiveTab] = React.useState<TabKey>("mes-corrente")
  const [conversationId, setConversationId] = React.useState<string | null>(null)
  const [selected, setSelected] = React.useState<unknown>(null)

  // ─── Filtros reais via useBiFilters ──────────────────────────────────────
  const dataMinimaQuery = useQuery({
    queryKey: ["bi", "metadata", "data-minima"],
    queryFn: () => biMetadata.dataMinima(),
    staleTime: 6 * 60 * 60 * 1000,
  })
  const dataMinima = dataMinimaQuery.data?.data_minima ?? undefined

  const { filtersWithFocus, preset, setFilter, resetFilters } =
    useBiFilters(dataMinima)

  // Metadata para Pills (Produto + UA)
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

  // ─── Query do KPI Strip ─────────────────────────────────────────────────
  const kpiStripQuery = useQuery({
    queryKey: ["bi", "operacoes2", "kpi-strip", filtersWithFocus],
    queryFn: () => biOperacoes2.kpiStrip(filtersWithFocus),
  })
  const kpiStrip = kpiStripQuery.data?.data

  // ─── AI hooks ─────────────────────────────────────────────────────────────
  // kpisBlock — bloco textual com Periodo + Mes Corrente para o LLM gerar
  // insights "agora vs periodo" (Opcao 4 paradigma 2026-05-03 §B).
  const kpisBlock = React.useMemo(() => {
    if (!kpiStrip) return undefined
    const lines: string[] = []
    lines.push(`Periodo (filtro: ${preset ?? "custom"}) vs ${kpiStrip.vop.mes_corrente_label}`)
    lines.push(
      `VOP — periodo: ${fmtBRLCompact.format(kpiStrip.vop.valor)} · mes: ${fmtBRLCompact.format(kpiStrip.vop.mes_corrente_valor)}`,
    )
    lines.push(
      `Taxa media — periodo: ${fmtPct2(kpiStrip.taxa_media.valor)} · mes: ${fmtPct2(kpiStrip.taxa_media.mes_corrente_valor)}`,
    )
    lines.push(
      `Prazo medio — periodo: ${fmtDays(kpiStrip.prazo_medio.valor)} · mes: ${fmtDays(kpiStrip.prazo_medio.mes_corrente_valor)}`,
    )
    lines.push(
      `Produto top — periodo: ${kpiStrip.produto_top.nome ?? kpiStrip.produto_top.sigla} (${fmtSharePct(kpiStrip.produto_top.share_pct)}) · mes: ${kpiStrip.produto_top.mes_corrente_nome ?? kpiStrip.produto_top.mes_corrente_sigla} (${fmtSharePct(kpiStrip.produto_top.mes_corrente_share_pct)})`,
    )
    lines.push(
      `Receita contratada — periodo: ${fmtBRLCompact.format(kpiStrip.receita_contratada.valor)} · mes: ${fmtBRLCompact.format(kpiStrip.receita_contratada.mes_corrente_valor)}`,
    )
    return lines.join("\n")
  }, [kpiStrip, preset])

  const quotaQ = useAIQuota()
  const insightsQ = useAIInsights({
    page: "/bi/operacoes2",
    period: preset ?? "12m",
    kpisBlock,
  })
  const { send } = useAIChat({
    conversationId,
    onConversationCreated: setConversationId,
  })
  const insights: AIInsight[] = React.useMemo(
    () => (insightsQ.data?.insights ?? []).map((i) => ({ text: i.text })),
    [insightsQ.data],
  )

  // ─── AI Panel + atalhos ──────────────────────────────────────────────────
  const ai = useAIPanel()

  // Atalhos Cmd/Ctrl + 1..5 para tabs (CLAUDE.md §11.6)
  React.useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && ["1", "2", "3", "4", "5"].includes(e.key)) {
        const idx = Number(e.key) - 1
        if (TABS[idx]) {
          e.preventDefault()
          setActiveTab(TABS[idx].key)
        }
      }
    }
    window.addEventListener("keydown", handleKey)
    return () => window.removeEventListener("keydown", handleKey)
  }, [])

  const aiContext = React.useMemo(
    () => ({
      page: "BI · Operacoes",
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

  const handleShare = React.useCallback(() => {
    toast.info("Compartilhar — em breve")
  }, [])
  const handleExport = React.useCallback(() => {
    toast.info("Exportar — em breve")
  }, [])

  const insightStripItems = React.useMemo(
    () => insights.map((ins, idx) => ({ id: String(idx), text: ins.text })),
    [insights],
  )

  // Sombra canonica na toolbar quando o conteudo (Z4) esta scrollado.
  const [scrollRef, scrolled] = useScrollShadow<HTMLDivElement>()

  return (
    <div className="flex h-[calc(100vh-3rem)] overflow-hidden">
      {/* Coluna principal */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Title row (70px) — banda branca unificada com a toolbar abaixo. */}
        <div className="shrink-0 bg-white px-6 pt-3.5 pb-3 dark:bg-gray-950">
          <PageHeader
            title="BI · Operações"
            info="Operacoes efetivadas: VOP, taxa, prazo, mix de produtos e receita contratada — com lentes em volume/ritmo, pricing, receita e cedentes."
            subtitle="Visao consolidada das operacoes efetivadas no periodo."
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

        {/* Toolbar unificada (52px) — tabs L3 + filtros + sync status. */}
        <div
          className={cx(
            "shrink-0 border-b border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
            scrolled && "scroll-shadow",
          )}
        >
          <div className="flex h-[52px] items-center gap-2 px-6">
            <TabNavigation className="border-0">
              {TABS.map((t, i) => (
                <TabNavigationLink
                  key={t.key}
                  href="#"
                  active={activeTab === t.key}
                  onClick={(e) => {
                    e.preventDefault()
                    setActiveTab(t.key)
                  }}
                  title={`Cmd/Ctrl + ${i + 1}`}
                >
                  {t.label}
                </TabNavigationLink>
              ))}
            </TabNavigation>

            <div
              aria-hidden="true"
              className="mx-1 h-5 w-px bg-gray-200 dark:bg-gray-800"
            />

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

            {/* Resetar filtros — habilitado quando ha qualquer filtro ativo. */}
            <Button
              variant="ghost"
              onClick={resetFilters}
              disabled={!hasFiltrosAtivos(preset, filtersWithFocus)}
              className="ml-1"
            >
              <RiRefreshLine
                className="size-3.5 shrink-0"
                aria-hidden="true"
              />
              Resetar
            </Button>

            <span className="ml-auto shrink-0 text-[11px] text-gray-500 dark:text-gray-400">
              {kpiStripQuery.isFetching ? "Atualizando…" : "Atualizado"}
            </span>
          </div>
        </div>

        {/* InsightStrip (38px) — primeiro insight inline + popover "+N analises" */}
        <div className="shrink-0 px-6 pt-3">
          <InsightStrip insights={insightStripItems} />
        </div>

        {/* Conteudo da aba — scroll container observado por useScrollShadow. */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-4">
          <div className="flex flex-col gap-4">
            {/* MOTIVO: KpiStrip page-level removido em 2026-05-09 — diagnostico
                em docs/bi-patterns-presentacao-dados.md §1.2: 4 dos 5 tiles
                duplicavam KPIs decompostos pelos cards das abas (VOP/Taxa/Prazo/
                Receita). Numeros migraram para o headerKpi de cada chart-card.
                Query `kpiStripQuery` continua viva — alimenta o LLM via
                `kpisBlock`. ProvenanceFooter idem (consome `provenance` da
                mesma query). */}

            {/* Tab content — area util da pagina */}
            {activeTab === "mes-corrente" && <AbaMesCorrente />}
            {activeTab === "volume-ritmo" && <AbaVolumeRitmo />}
            {activeTab === "produtos-pricing" && <AbaProdutosPricing />}
            {activeTab === "receita" && <PlaceholderTab label="Receita" />}
            {activeTab === "cedentes-concentracao" && (
              <PlaceholderTab label="Cedentes & Concentração" />
            )}
          </div>
        </div>

        {/* Z5 — ProvenanceFooter real (vem do backend via biOperacoes2.kpiStrip) */}
        <ProvenanceFooter provenance={kpiStripQuery.data?.provenance} />
      </div>

      {/* AI Panel — drawer in-layout */}
      <AIPanel
        open={ai.open}
        onClose={() => ai.setOpen(false)}
        context={aiContext}
        insights={insights}
        sendMessage={send}
      />

      {/* Drill-down sheet — placeholder ate Aba 4 ter rows clicaveis */}
      <DrillDownSheet
        open={selected !== null}
        onClose={() => setSelected(null)}
        title="Detalhe"
      >
        <div className="p-6 text-xs text-gray-500 dark:text-gray-400">
          Drill-down sera ativado nas Abas 2/3/4 conforme implementadas.
        </div>
      </DrillDownSheet>
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Helpers
// ───────────────────────────────────────────────────────────────────────────

function PlaceholderTab({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16">
      <div
        aria-hidden="true"
        className="size-10 rounded-full bg-gray-100 dark:bg-gray-800"
      />
      <p className="text-sm font-medium text-gray-600 dark:text-gray-400">
        Aba “{label}”
      </p>
      <p className="text-xs text-gray-400 dark:text-gray-600">
        Em breve. Aba 1 (Volume & Ritmo) entregue na primeira passada.
      </p>
    </div>
  )
}

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

// ─── Multi-select via FilterChip + checkboxes ────────────────────────────
//
// FilterChip canonico e single-select (label + valor + chevron). Para multi,
// composimos a lista de opcoes com Checkbox do Tremor dentro do popover —
// preserva visual canonico no trigger e funcionalidade multi no popover.

type MultiOption = { value: string; label: string }

/** Label exibido no FilterChip quando ha selecao multi-valor. */
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

/** Indica se ha qualquer filtro nao-default ativo (habilita botao Resetar). */
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
