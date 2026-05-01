// src/app/(app)/credito/agentes/page.tsx
//
// Catalogo de Specialist Agents disponiveis (read-only no MVP).
// Edicao de prompts vem via /admin/ia/prompts (system maintainer).
//
// Pattern canonico: `ListagemCrudCards` (variante read-only — sem `+ Novo`,
// sem DropdownMenu, sem DrillDownSheet, sem Dialog destrutivo). Mantem a
// anatomia da PageHeader (title + info + subtitle), Card[FilterSearch +
// SegmentSwitch + counter] e grid 1/2/3 de AgentCard.
//
// Read-only justificado: agentes sao definidos em codigo
// (`backend/app/shared/agents/catalog.py`), nao por tenant. Customizacao
// por tenant esta na roadmap (banner "Em breve" no rodape).

"use client"

import * as React from "react"
import { RiRobot2Line, RiSparklingLine } from "@remixicon/react"

import { Card } from "@/components/tremor/Card"
import { Button } from "@/components/tremor/Button"
import {
  FilterSearch,
  PageHeader,
  SegmentSwitch,
} from "@/design-system/components"
import { cardTokens } from "@/design-system/tokens/card"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

// ───────────────────────────────────────────────────────────────────────────
// Catalogo — espelhado de backend/app/shared/agents/catalog.py
// `kind`: agrupa agentes pra SegmentSwitch (Analise vs Extracao).
// ───────────────────────────────────────────────────────────────────────────

type AgentKind = "analise" | "extracao"

type AgentEntry = {
  name: string
  label: string
  description: string
  section: string
  kind: AgentKind
}

const AGENTS: AgentEntry[] = [
  { name: "social_contract_analyst",   label: "Analise de contrato social",  description: "Firmas e poderes, alteracoes do QSA, objeto social, restricoes estatutarias.",                section: "Contrato social", kind: "analise"  },
  { name: "financial_analyst",         label: "Analise financeira",          description: "DRE, Balanco, faturamento — indicadores, tendencias, sazonalidade.",                            section: "Financeiro",      kind: "analise"  },
  { name: "indebtedness_analyst",      label: "Analise de endividamento",    description: "SCR Bacen + dividas declaradas, concentracao bancaria, capacidade de pagamento.",                section: "Endividamento",   kind: "analise"  },
  { name: "legal_analyst",             label: "Analise juridica",            description: "Processos judiciais e protestos, classificacao de risco juridico.",                              section: "Juridico",        kind: "analise"  },
  { name: "partner_analyst",           label: "Analise de socios",           description: "Patrimonio, processos pessoais, ligacoes (parentescos, empresas em comum).",                     section: "Socios",          kind: "analise"  },
  { name: "commercial_visit_analyst",  label: "Analise de visita comercial", description: "Relatorio de visita, consistencia com declaracoes da empresa.",                                  section: "Visita",          kind: "analise"  },
  { name: "cross_reference_analyst",   label: "Cross-reference",             description: "Cruza dados de TODAS as analises buscando inconsistencias entre fontes.",                        section: "Cross-Ref",       kind: "analise"  },
  { name: "opinion_writer",            label: "Redator de parecer",          description: "Gera parecer consolidado: executive summary + recomendacao final.",                              section: "Parecer",         kind: "analise"  },
  { name: "document_extractor",        label: "Extrator de documentos",      description: "Multimodal — extrai dados estruturados de PDFs e imagens.",                                      section: "Documentos",      kind: "extracao" },
  { name: "pleito_extractor",          label: "Extrator do pleito",          description: "Extrai produto/volume/taxa/prazo de email ou texto informal.",                                   section: "Pleito",          kind: "extracao" },
]

type Segment = "todos" | "analise" | "extracao"

export default function AgentesPage() {
  const [search, setSearch] = React.useState("")
  const [segment, setSegment] = React.useState<Segment>("todos")

  const counts = React.useMemo(
    () => ({
      todos: AGENTS.length,
      analise: AGENTS.filter((a) => a.kind === "analise").length,
      extracao: AGENTS.filter((a) => a.kind === "extracao").length,
    }),
    [],
  )

  const segmentFiltered = React.useMemo(() => {
    if (segment === "analise") return AGENTS.filter((a) => a.kind === "analise")
    if (segment === "extracao") return AGENTS.filter((a) => a.kind === "extracao")
    return AGENTS
  }, [segment])

  const visible = React.useMemo(() => {
    const term = search.trim().toLowerCase()
    if (!term) return segmentFiltered
    return segmentFiltered.filter(
      (a) =>
        a.label.toLowerCase().includes(term) ||
        a.description.toLowerCase().includes(term) ||
        a.name.toLowerCase().includes(term) ||
        a.section.toLowerCase().includes(term),
    )
  }, [segmentFiltered, search])

  const noResults = visible.length === 0

  return (
    <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
      <PageHeader
        title="Agentes especialistas"
        info="Catalogo de agentes IA disponiveis para uso nos workflows. Cada um tem prompt versionado + tools tenant-scoped + output schema validado."
        subtitle="Credito · Configuracao"
      />

      {/* Faixa de filtros — mesma anatomia do ListagemCrudCards */}
      <Card className="flex flex-wrap items-center gap-2 p-3">
        <FilterSearch
          value={search}
          onChange={(e) => setSearch(e.currentTarget.value)}
          onClear={() => setSearch("")}
          placeholder="Buscar por nome, descricao ou secao..."
        />
        <SegmentSwitch
          options={[
            { value: "todos",    label: "Todos",    count: counts.todos },
            { value: "analise",  label: "Analise",  count: counts.analise },
            { value: "extracao", label: "Extracao", count: counts.extracao },
          ]}
          value={segment}
          onChange={setSegment}
        />
        <span
          className="ml-auto text-[11px] tabular-nums text-gray-500 dark:text-gray-400"
          aria-live="polite"
        >
          {visible.length === counts.todos
            ? `${visible.length} ${visible.length === 1 ? "agente" : "agentes"}`
            : `${visible.length} de ${counts.todos}`}
        </span>
      </Card>

      {noResults ? (
        <div className="flex flex-col items-center justify-center gap-2 rounded border border-dashed border-gray-200 bg-white py-12 text-center dark:border-gray-800 dark:bg-gray-950">
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Nenhum agente para esses filtros
          </p>
          <Button
            variant="ghost"
            onClick={() => {
              setSearch("")
              setSegment("todos")
            }}
          >
            Limpar filtros
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {visible.map((agent) => (
            <AgentCard key={agent.name} agent={agent} />
          ))}
        </div>
      )}

      {/* Banner "em breve" — feature na roadmap (Onda 3) */}
      <div className="flex items-start gap-3 rounded-md border border-amber-200 bg-amber-50 p-4 text-xs text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
        <RiSparklingLine className="mt-0.5 size-4 shrink-0" aria-hidden />
        <div>
          <p className="font-medium">Customizacao por tenant — em breve</p>
          <p className="mt-1">
            Cada tenant podera customizar os system prompts dos agentes (override
            por workflow), criar agentes proprios e compartilhar templates no
            marketplace.
          </p>
        </div>
      </div>
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// AgentCard — anatomia segue o pattern ListagemCrudCards.
// Variante read-only: sem onClick, sem DropdownMenu de acoes.
// Cor indigo (icone) e IDENTIDADE de modulo/credito, nao status.
// Modo Iteracao de Design ativo — apos a janela, promover a token nomeado.
// ───────────────────────────────────────────────────────────────────────────

function AgentCard({ agent }: { agent: AgentEntry }) {
  return (
    <Card>
      <div className={cx(cardTokens.body, "space-y-3")}>
        {/* Linha 1: avatar + badge de secao (read-only — sem dropdown) */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-md bg-indigo-50 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-400">
            <RiRobot2Line className="size-5" aria-hidden />
          </div>
          <div className="flex flex-1 flex-wrap items-center justify-end gap-2">
            <span
              className={cx(
                tableTokens.badge,
                "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300",
              )}
            >
              {agent.section}
            </span>
          </div>
        </div>

        {/* Linha 2: titulo + descricao */}
        <div>
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 line-clamp-1">
            {agent.label}
          </h3>
          <p className={cx(tableTokens.cellSecondary, "mt-1 line-clamp-2")}>
            {agent.description}
          </p>
        </div>

        {/* Linha 3: metadados — agent.name como identifier tecnico */}
        <div className={cx(tableTokens.cellSecondary, "flex items-center gap-2")}>
          <code className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-[11px] text-gray-700 dark:bg-gray-900 dark:text-gray-300">
            {agent.name}
          </code>
        </div>
      </div>
    </Card>
  )
}
