// src/app/(app)/controladoria/dre/page.tsx
//
// Controladoria · DRE — Demonstrativo do Resultado do Exercicio.
//
// Shell derivado do DashboardBiPadrao (CLAUDE.md §7) e do shell consolidado
// de cota-sub / bi/operacoes2:
//   - Z1: PageHeader (titulo + info + DashboardHeaderActions)
//   - Z2: Toolbar unificada (filtros + saved views — sem L3 tabs por enquanto)
//   - Z3: KpiHeadline (statement + primary + diagnostics)
//   - Z4: DrePivotTable (tabela hierarquica grupo>subgrupo>descricao x competencia)
//   - Z5: ProvenanceFooter (mock — substituir por status real dos adapters)
//   - Lateral: AIPanel violeta in-layout + FornecedoresDrillSheet
//
// Backend:
//   GET /controladoria/dre/competencias-disponiveis
//   GET /controladoria/dre/pivot
//   GET /controladoria/dre/drill/fornecedores
//
// Pipeline upstream: Bitfin UNLTD_<X> -> bronze wh_bitfin_raw_dre -> classifier
// (wh_dre_classification_rule) -> silver wh_dre_mensal (CLAUDE.md §13.2.1).

"use client"

import * as React from "react"
import {
  RiCalendarLine,
  RiCheckLine,
  RiFundsLine,
} from "@remixicon/react"

import { format } from "date-fns"
import { ptBR } from "date-fns/locale"

import { cx } from "@/lib/utils"
import { Calendar } from "@/components/tremor/Calendar"

import { PageHeader } from "@/design-system/components/PageHeader"
import { DashboardHeaderActions } from "@/design-system/components/DashboardHeaderActions"
import {
  ProvenanceFooter,
  type ProvenanceSource,
} from "@/design-system/components/ProvenanceFooter"
import { KpiHeadline, type KpiHeadlineDiagnostic } from "@/design-system/components/KpiHeadline"
import {
  FilterChip,
} from "@/design-system/components/FilterBar"
import { EmptyState } from "@/design-system/components/EmptyState"
import {
  AIPanel,
  useAIPanel,
} from "@/design-system/components/AIPanel"
import { TabNavigation, TabNavigationLink } from "@/components/tremor/TabNavigation"
import { useUAs } from "@/lib/hooks/cadastros"
import { useDrePivot, useDreBreakdown } from "@/lib/hooks/controladoria"
import { useScrollShadow } from "@/lib/hooks/use-scroll-shadow"

import { DrePivotTable } from "./_components/DrePivotTable"
import { DreBreakdownTable } from "./_components/DreBreakdownTable"
import type { DrePivotFilters, DreBreakdownFilters, DreDimensao } from "@/lib/api-client"

// ───────────────────────────────────────────────────────────────────────────
// Helpers / formatters
// ───────────────────────────────────────────────────────────────────────────

const fmtBRLCompact = new Intl.NumberFormat("pt-BR", {
  notation: "compact",
  style: "currency",
  currency: "BRL",
  minimumFractionDigits: 0,
  maximumFractionDigits: 1,
})

const fmtPct = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})

function firstOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1)
}

function addMonths(d: Date, months: number): Date {
  return new Date(d.getFullYear(), d.getMonth() + months, 1)
}

function isoFirstOfMonth(d: Date): string {
  return format(firstOfMonth(d), "yyyy-MM-dd")
}

function labelMonth(d: Date): string {
  return format(d, "MMM/yyyy", { locale: ptBR })
}

// Fonte: filtra a coluna `fonte` do silver wh_dre_mensal. Os valores DEVEM
// casar com os canonicos gravados pelo ETL (_TIPO_TO_FONTE em etl.py); antes
// mandavamos os nomes de tipo_origem (dre_legacy/pagamento_opcao/...) que
// nunca casavam -> filtro retornava vazio em silencio. Default "Todas" agrega
// todos (servico ignora o filtro quando vazio).
const FONTE_OPTIONS = [
  { value: "",                label: "Todas" },
  { value: "DRE_OPERACIONAL", label: "Operacional" },
  { value: "CONTAS_A_PAGAR",  label: "Contas a pagar" },
  { value: "COMISSAO",        label: "Comissao" },
] as const

const MOCK_PROVENANCE: ProvenanceSource[] = [
  { label: "Bitfin (DRE)", updated: "ha 18 min", sla: "60 min", stale: false },
  { label: "Classifier",    updated: "v2.0.0",    sla: "—",       stale: false },
]

// Abas L3: Demonstracao (pivot, periodo) + breakdowns da receita (1 mes).
const TABS = [
  { key: "demonstracao", label: "Demonstração", dim: null },
  { key: "natureza",     label: "Por Natureza", dim: "natureza" },
  { key: "cedente",      label: "Por Cedente",  dim: "cedente" },
  { key: "produto",      label: "Por Produto",  dim: "produto" },
] as const
type TabKey = (typeof TABS)[number]["key"]

// ───────────────────────────────────────────────────────────────────────────
// Page
// ───────────────────────────────────────────────────────────────────────────

export default function DrePage() {
  const today = React.useMemo(() => new Date(), [])

  // Periodo default: ultimos 6 meses (mes atual incluso)
  const [competenciaAte, setCompetenciaAte] = React.useState<Date>(firstOfMonth(today))
  const [competenciaDe,  setCompetenciaDe]  = React.useState<Date>(addMonths(firstOfMonth(today), -5))

  // Fundo: UAs do gr_db (qualquer tipo — DRE nao restringe a FIDC). Conversao
  // UUID -> int via campo `bitfin_ua_id` (UA pode nao ter mapping ainda).
  const fundosQuery = useUAs({ ativa: true })
  const [fundoUuid, setFundoUuid] = React.useState<string>("")  // "" = Todos
  const fundoSelecionado = fundosQuery.data?.find((ua) => ua.id === fundoUuid)
  const fundoBitfinId = fundoSelecionado?.bitfin_ua_id ?? null

  const [fonte, setFonte] = React.useState<string>("")  // "" = Todas

  const [activeTab, setActiveTab] = React.useState<TabKey>("demonstracao")

  const ai = useAIPanel()

  // Filtro do pivot principal
  const pivotFilters: DrePivotFilters = React.useMemo(
    () => ({
      competenciaDe:  isoFirstOfMonth(competenciaDe),
      competenciaAte: isoFirstOfMonth(competenciaAte),
      fundoId:        fundoBitfinId ?? undefined,
      fonte:          fonte || undefined,
    }),
    [competenciaDe, competenciaAte, fundoBitfinId, fonte],
  )

  const pivotQuery = useDrePivot(pivotFilters)
  const pivot = pivotQuery.data

  // Breakdown da receita (1 mes = competencia "Fim"). So quando a aba e de breakdown.
  const breakdownFilters = React.useMemo<DreBreakdownFilters | null>(() => {
    const dim = TABS.find((t) => t.key === activeTab)?.dim
    if (!dim) return null
    return {
      competencia: isoFirstOfMonth(competenciaAte),
      dim: dim as DreDimensao,
      fundoId: fundoBitfinId ?? undefined,
    }
  }, [activeTab, competenciaAte, fundoBitfinId])

  const breakdownQuery = useDreBreakdown(breakdownFilters)

  // ────────────────────────────────────────────────────────────────────────
  // KpiHeadline — derivado dos totais agregados do pivot
  // ────────────────────────────────────────────────────────────────────────
  const headlinePrimary = React.useMemo(() => {
    if (!pivot) return { value: "—" }
    const r = pivot.totais.resultado
    const sinal = r >= 0 ? "+" : ""
    return {
      value: `${sinal}${fmtBRLCompact.format(r)}`,
      sub:   `no periodo de ${labelMonth(competenciaDe)} a ${labelMonth(competenciaAte)}`,
      tone:  r >= 0 ? "positive" as const : "negative" as const,
    }
  }, [pivot, competenciaDe, competenciaAte])

  const headlineDiagnostics = React.useMemo<KpiHeadlineDiagnostic[]>(() => {
    if (!pivot) return []
    const out: KpiHeadlineDiagnostic[] = []

    // Receita total — sempre informativo (top informativo da DRE)
    out.push({
      label: `Receita ${fmtBRLCompact.format(pivot.totais.receita)}`,
      tone:  "ok",
    })

    // PDD (constituicao) — chip warning quando consome mais de 50% da receita
    const pdd = pivot.grupos.find((g) => g.grupoDre === "PROVISAO_PDD")
    if (pdd && pdd.totais.custo > 0 && pivot.totais.receita > 0) {
      const pct = (pdd.totais.custo / pivot.totais.receita) * 100
      out.push({
        label: `PDD ${fmtBRLCompact.format(pdd.totais.custo)} (${fmtPct.format(pct)}% da receita)`,
        tone:  pct > 50 ? "warning" : "info",
      })
    }

    // Despesa Administrativa — info chip
    const adm = pivot.grupos.find((g) => g.grupoDre === "DESPESA_ADMINISTRATIVA")
    if (adm && adm.totais.custo > 0) {
      out.push({
        label: `Despesa adm ${fmtBRLCompact.format(adm.totais.custo)}`,
        tone:  "info",
      })
    }

    // Margem operacional (resultado / receita_bruta)
    if (pivot.totais.receita > 0) {
      const margem = (pivot.totais.resultado / pivot.totais.receita) * 100
      out.push({
        label: `Margem ${fmtPct.format(margem)}%`,
        tone:  margem >= 10 ? "ok" : margem >= 0 ? "info" : "warning",
      })
    }

    return out
  }, [pivot])

  // ────────────────────────────────────────────────────────────────────────
  // Header actions
  // ────────────────────────────────────────────────────────────────────────
  const handleShare = React.useCallback(() => {
    void navigator.clipboard?.writeText(window.location.href)
  }, [])

  const handleExport = React.useCallback(() => {
    // Stub — wire to real export endpoint (CSV/XLSX).
    // eslint-disable-next-line no-console
    console.log("export DRE", pivotFilters)
  }, [pivotFilters])

  const aiContext = React.useMemo(
    () => ({
      page: "Controladoria · DRE",
      period: `${labelMonth(competenciaDe)} → ${labelMonth(competenciaAte)}`,
      filters: [
        fundoSelecionado && `Fundo: ${fundoSelecionado.nome}`,
        fonte && `Fonte: ${fonte}`,
      ].filter(Boolean).join(", ") || "Nenhum",
    }),
    [competenciaDe, competenciaAte, fundoSelecionado, fonte],
  )

  const [scrollRef, scrolled] = useScrollShadow<HTMLDivElement>()

  // Mensagem quando UA selecionada nao tem bitfin_ua_id (silver e por int)
  const fundoSemBitfin = fundoUuid !== "" && fundoBitfinId === null

  return (
    <div className="flex h-[calc(100vh-3rem)] overflow-hidden">
      {/* Coluna principal */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Z1 — Title row */}
        <div className="shrink-0 bg-white px-6 pt-3.5 pb-3 dark:bg-gray-950">
          <PageHeader
            title="DRE"
            info="Demonstrativo do Resultado do Exercicio. Le silver wh_dre_mensal populada pelo ETL Bitfin v2.0.0 (bronze + classifier override-por-tenant). Hierarquia grupo > subgrupo > descricao pivotada por competencia."
            subtitle="Controladoria · Resultado"
            actions={
              <DashboardHeaderActions
                ai={{ open: ai.open, onToggle: ai.toggle }}
                onShare={handleShare}
                onExport={handleExport}
              />
            }
          />
        </div>

        {/* Z2 — Toolbar */}
        <div
          className={cx(
            "shrink-0 border-b border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
            scrolled && "scroll-shadow",
          )}
        >
          <div className="flex h-[52px] items-center gap-2 px-6">
            <FilterChip
              label="Inicio"
              value={labelMonth(competenciaDe)}
              active={true}
              icon={RiCalendarLine}
            >
              <Calendar
                mode="single"
                selected={competenciaDe}
                onSelect={(d) => d && setCompetenciaDe(firstOfMonth(d))}
                locale={ptBR}
                disabled={(date) => date > today || date > competenciaAte}
                initialFocus
              />
            </FilterChip>

            <FilterChip
              label="Fim"
              value={labelMonth(competenciaAte)}
              active={true}
              icon={RiCalendarLine}
            >
              <Calendar
                mode="single"
                selected={competenciaAte}
                onSelect={(d) => d && setCompetenciaAte(firstOfMonth(d))}
                locale={ptBR}
                disabled={(date) => date > today || date < competenciaDe}
                initialFocus
              />
            </FilterChip>

            <FilterChip
              label="Fundo"
              value={fundoSelecionado?.nome ?? "Todos"}
              active={fundoUuid !== ""}
            >
              <div className="py-1">
                <button
                  type="button"
                  onClick={() => setFundoUuid("")}
                  className={cx(
                    "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                    fundoUuid === ""
                      ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                      : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
                  )}
                >
                  <span className="flex-1 text-left">Todos</span>
                  {fundoUuid === "" && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
                </button>
                {fundosQuery.isLoading && (
                  <div className="px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400">
                    Carregando UAs...
                  </div>
                )}
                {fundosQuery.data?.map((ua) => (
                  <button
                    key={ua.id}
                    type="button"
                    onClick={() => setFundoUuid(ua.id)}
                    disabled={ua.bitfin_ua_id === null}
                    className={cx(
                      "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                      "disabled:opacity-50 disabled:cursor-not-allowed",
                      fundoUuid === ua.id
                        ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                        : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
                    )}
                    title={
                      ua.bitfin_ua_id === null
                        ? "UA sem mapping Bitfin — DRE indisponivel"
                        : undefined
                    }
                  >
                    <span className="flex-1 text-left">{ua.nome}</span>
                    {fundoUuid === ua.id && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
                  </button>
                ))}
              </div>
            </FilterChip>

            <FilterChip
              label="Fonte"
              value={FONTE_OPTIONS.find((o) => o.value === fonte)?.label ?? "Todas"}
              active={fonte !== ""}
            >
              <div className="py-1">
                {FONTE_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setFonte(opt.value)}
                    className={cx(
                      "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                      fonte === opt.value
                        ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                        : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
                    )}
                  >
                    <span className="flex-1 text-left">{opt.label}</span>
                    {fonte === opt.value && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
                  </button>
                ))}
              </div>
            </FilterChip>

            <div className="ml-auto flex items-center gap-2">
              <span className="shrink-0 text-[11px] text-gray-500 dark:text-gray-400">
                {pivotQuery.isFetching ? "Atualizando…" : "Atualizado"}
              </span>
            </div>
          </div>
        </div>

        {/* Z2.5 — Abas L3 (Demonstracao + breakdowns da receita) */}
        <div className="shrink-0 border-b border-gray-200 bg-white px-6 dark:border-gray-800 dark:bg-gray-950">
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

        {/* Z3/Z4 — conteudo da aba ativa */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-4">
          {fundoSemBitfin ? (
            <EmptyState
              icon={RiFundsLine}
              title="UA sem mapping com Bitfin"
              description="O fundo selecionado nao tem bitfin_ua_id. Cadastre o mapping em Cadastros · UAs para habilitar a DRE."
              className="mt-4"
            />
          ) : activeTab === "demonstracao" ? (
            <div className="flex flex-col gap-4">
              <KpiHeadline
                statement="Resultado do periodo"
                primary={headlinePrimary}
                diagnostics={headlineDiagnostics}
                loading={pivotQuery.isLoading && !pivot}
              />

              <DrePivotTable
                pivot={pivot}
                loading={pivotQuery.isLoading}
              />
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              <KpiHeadline
                statement={`Receita de ${labelMonth(competenciaAte)}`}
                primary={{
                  value: fmtBRLCompact.format(breakdownQuery.data?.totalReceita ?? 0),
                  sub: `por ${TABS.find((t) => t.key === activeTab)?.label.toLowerCase()}`,
                  tone: "positive" as const,
                }}
                diagnostics={[]}
                loading={breakdownQuery.isLoading && !breakdownQuery.data}
              />

              <DreBreakdownTable
                data={breakdownQuery.data}
                loading={breakdownQuery.isLoading}
              />
            </div>
          )}
        </div>

        {/* Z5 — ProvenanceFooter (mock — substituir por status real) */}
        <ProvenanceFooter sources={MOCK_PROVENANCE} />
      </div>

      {/* AIPanel — drawer in-layout (sem sendMessage ainda — placeholder) */}
      <AIPanel
        open={ai.open}
        onClose={() => ai.setOpen(false)}
        context={aiContext}
      />
    </div>
  )
}
