// src/app/(app)/controladoria/pagamento-diario/page.tsx
//
// Pagamento Diario — pagina canonica do BI Framework (DashboardBiPadrao
// minimalista). Foco unico: mostrar o que saiu do caixa no dia, lendo
// `pagamentos` do endpoint variacoes-dia (silver only, CLAUDE.md §13.2.1).
//
// Estrutura DashboardBiPadrao (5 zonas + AIPanel lateral):
//   Z1 PageHeader (titulo + DashboardHeaderActions canonico)
//   Z2 TabNavigation L3 (single tab "Diario" por enquanto — pode crescer
//      para "Por origem", "Por fornecedor", etc., sem refactor)
//   Z3 FilterBar sticky (Dia + Fundo)
//   Z4 PagamentosDiaPanel
//   Z5 ProvenanceFooter
//   Lateral: AIPanel violet drawer
//
// Sem KpiStrip, sem charts, sem tabela de movimentacoes — divergencia
// intencional do DashboardBiPadrao completo. MOTIVO: a pagina tem foco
// unico (lista de pagamentos), KPIs/charts entrariam como ruido.

"use client"

import * as React from "react"
import { RiCalendarLine, RiCheckLine, RiHandCoinLine } from "@remixicon/react"

import { format, isSameDay } from "date-fns"
import { ptBR } from "date-fns/locale"

import { cx } from "@/lib/utils"
import { Calendar } from "@/components/tremor/Calendar"
import {
  TabNavigation,
  TabNavigationLink,
} from "@/components/tremor/TabNavigation"

import { PageHeader } from "@/design-system/components/PageHeader"
import { DashboardHeaderActions } from "@/design-system/components/DashboardHeaderActions"
import { ProvenanceFooter, type ProvenanceSource } from "@/design-system/components/ProvenanceFooter"
import {
  FilterBar,
  FilterChip,
  SavedViewsDropdown,
} from "@/design-system/components/FilterBar"
import { EmptyState } from "@/design-system/components/EmptyState"
import {
  AIPanel,
  useAIPanel,
  type AIInsight,
} from "@/design-system/components/AIPanel"
import { PagamentosDiaPanel } from "@/components/controladoria/PagamentosDiaPanel"

import { useUAs } from "@/lib/hooks/cadastros"
import { useVariacoesDia } from "@/lib/hooks/controladoria"

// ───────────────────────────────────────────────────────────────────────────
// L3 Tabs — single por enquanto (CLAUDE.md §11.6: max 3 niveis)
// ───────────────────────────────────────────────────────────────────────────

const TABS = [
  { key: "diario", label: "Diario" },
] as const

type TabKey = (typeof TABS)[number]["key"]

// ───────────────────────────────────────────────────────────────────────────
// Mocks de proveniencia + insights (substituir por dados reais)
// ───────────────────────────────────────────────────────────────────────────

const MOCK_PROVENANCE: ProvenanceSource[] = [
  { label: "Bitfin · Caixa", updated: "Hoje 08:30" },
  { label: "QiTech · CPR",   updated: "Hoje 08:00" },
]

const MOCK_INSIGHTS: AIInsight[] = []

// ───────────────────────────────────────────────────────────────────────────
// Pagina
// ───────────────────────────────────────────────────────────────────────────

export default function PagamentoDiarioPage() {
  // Dia: pagina analisa um unico dia por vez. Default = hoje.
  const today = React.useMemo(() => new Date(), [])
  const [day, setDay] = React.useState<Date>(today)

  // Fundo: opcoes vem de Cadastros · UAs do tipo FIDC.
  const fundosQuery  = useUAs({ tipo: "fidc", ativa: true })
  const fundoOptions = React.useMemo(
    () => ["Todos", ...(fundosQuery.data?.map((ua) => ua.nome) ?? [])],
    [fundosQuery.data],
  )
  const [fundo, setFundo] = React.useState<string>("Todos")

  const [activeTab, setActiveTab] = React.useState<TabKey>("diario")

  // Atalho Cmd/Ctrl + 1 (regra L3 do CLAUDE.md §11.6) — uma tab so por enquanto.
  React.useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "1") {
        e.preventDefault()
        setActiveTab(TABS[0].key)
      }
    }
    window.addEventListener("keydown", handleKey)
    return () => window.removeEventListener("keydown", handleKey)
  }, [])

  const ai = useAIPanel()

  // Lookup do UUID da UA selecionada (endpoint exige fundo_id).
  const fundoId = React.useMemo(() => {
    if (fundo === "Todos") return null
    return fundosQuery.data?.find((ua) => ua.nome === fundo)?.id ?? null
  }, [fundo, fundosQuery.data])

  const dayIso         = React.useMemo(() => format(day, "yyyy-MM-dd"), [day])
  const variacoesQuery = useVariacoesDia(fundoId, dayIso)
  const fundoSelecionado = fundoId !== null

  // Saved views — params atuais + handler
  const currentViewParams = React.useMemo<Record<string, string>>(() => ({
    day:   format(day, "yyyy-MM-dd"),
    fundo,
  }), [day, fundo])

  const handleApplyView = React.useCallback((view: { params: Record<string, string> }) => {
    const p = view.params
    if (p.fundo) setFundo(p.fundo)
    if (p.day) {
      const d = new Date(p.day)
      if (!isNaN(d.getTime())) setDay(d)
    }
  }, [])

  // Contexto da IA (mocks por enquanto — handler real conecta no LLM gateway).
  const aiContext = React.useMemo(() => ({
    page:    "controladoria/pagamento-diario",
    period:  format(day, "yyyy-MM-dd"),
    fundo,
  }), [day, fundo])

  function handleShare() {
    void navigator.clipboard?.writeText(window.location.href)
  }

  function handleExport() {
    // TODO: exportar pagamentos do dia em CSV.
  }

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden bg-gray-50 dark:bg-gray-950">
      {/* Coluna principal */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">

        {/* Z1 — PageHeader */}
        <div className="shrink-0 px-6 pt-5 pb-3">
          <PageHeader
            title="Pagamento Diario"
            info="Saidas de caixa do dia (pagamentos efetivados) cruzadas com provisoes previas do CPR. Le `pagamentos` de variacoes-dia (silver canonico)."
            actions={
              <DashboardHeaderActions
                ai={{ open: ai.open, onToggle: ai.toggle }}
                onShare={handleShare}
                onExport={handleExport}
              />
            }
          />
        </div>

        {/* Z2 — TabNavigation L3 */}
        <div className="shrink-0 px-6">
          <TabNavigation>
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
        </div>

        {/* Z3 — FilterBar sticky */}
        <div className="shrink-0 px-6">
          <FilterBar
            extraActions={
              <SavedViewsDropdown
                currentParams={currentViewParams}
                onApplyView={handleApplyView}
              />
            }
          >
            <FilterChip
              label="Dia"
              value={isSameDay(day, today) ? "Hoje" : format(day, "dd/MM/yyyy")}
              active={!isSameDay(day, today)}
              icon={RiCalendarLine}
            >
              <Calendar
                mode="single"
                selected={day}
                onSelect={(d) => d && setDay(d)}
                locale={ptBR}
                disabled={{ after: today }}
                initialFocus
              />
            </FilterChip>

            <FilterChip
              label="Fundo"
              value={fundo}
              active={fundo !== "Todos"}
            >
              <div className="py-1">
                {fundosQuery.isLoading && (
                  <div className="px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400">
                    Carregando UAs...
                  </div>
                )}
                {fundosQuery.isError && (
                  <div className="px-3 py-1.5 text-xs text-red-600 dark:text-red-400">
                    Falha ao carregar UAs
                  </div>
                )}
                {!fundosQuery.isLoading && !fundosQuery.isError && fundoOptions.length === 1 && (
                  <div className="px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400">
                    Nenhuma UA do tipo FIDC cadastrada
                  </div>
                )}
                {fundoOptions.map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => setFundo(opt)}
                    className={cx(
                      "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                      fundo === opt
                        ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                        : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
                    )}
                  >
                    <span className="flex-1 text-left">{opt}</span>
                    {fundo === opt && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
                  </button>
                ))}
              </div>
            </FilterChip>
          </FilterBar>
        </div>

        {/* Z4 — Conteudo */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {!fundoSelecionado ? (
            <EmptyState
              icon={RiHandCoinLine}
              title="Selecione um fundo para comecar"
              description='Escolha o fundo no filtro "Fundo" acima para carregar os pagamentos efetivados no dia.'
              className="mt-4"
            />
          ) : (
            <PagamentosDiaPanel
              variacoes={variacoesQuery.data}
              loading={variacoesQuery.isLoading}
              error={variacoesQuery.error as Error | null}
            />
          )}
        </div>

        {/* Z5 — ProvenanceFooter (mock) */}
        <ProvenanceFooter sources={MOCK_PROVENANCE} />
      </div>

      {/* AI Panel */}
      <AIPanel
        open={ai.open}
        onClose={() => ai.setOpen(false)}
        context={aiContext}
        insights={MOCK_INSIGHTS}
      />
    </div>
  )
}
