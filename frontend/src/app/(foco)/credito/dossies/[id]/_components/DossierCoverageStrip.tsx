// DossierCoverageStrip — raio-X do dossiê (2026-06-12, pedido do Ricardo):
// "bater o olho e saber o que foi visto". Um card por fonte/análise,
// derivado do que JÁ existe no dossiê (docs, node runs, red flags, parecer).
//
// Regra §14.6 aplicada à cobertura: o que NÃO rodou aparece explícito
// ("não consultado", cinza) — ausência informada, nunca omitida. Renderiza
// em DOIS lugares com a mesma fonte: topo do Dossiê de leitura (D4) e a
// estação Parecer (acima da decisão — "vou assinar tendo visto o quê?").

"use client"

import * as React from "react"

import { cx } from "@/lib/utils"
import type { CreditDocumentRead } from "@/lib/credito-client"

type Status = "ok" | "warn" | "bad" | "off"

export type CoverageItem = {
  id: string
  label: string
  detail: string
  status: Status
}

const DOT: Record<Status, string> = {
  ok: "bg-emerald-500",
  warn: "bg-amber-500",
  bad: "bg-red-500",
  off: "bg-gray-300 dark:bg-gray-700",
}

const TEXT: Record<Status, string> = {
  ok: "text-gray-900 dark:text-gray-100",
  warn: "text-amber-900 dark:text-amber-200",
  bad: "text-red-900 dark:text-red-200",
  off: "text-gray-400 dark:text-gray-500",
}

// Shapes mínimos do que a página já tem (evita acoplar no tipo gigante).
type StepLite = {
  nodeType?: string | null
  state?: string | null
  config?: Record<string, unknown> | null
  output?: Record<string, unknown> | null
}

type RedFlagLite = { severity?: string | null }

type OpinionLite = { recommendation?: string | null } | null

const RECO_LABEL: Record<string, { label: string; status: Status }> = {
  approve: { label: "aprovação", status: "ok" },
  conditional: { label: "aprovação condicional", status: "warn" },
  deny: { label: "negativa", status: "bad" },
}

const REVENUE_DOC_TYPES = new Set([
  "revenue_report",
  "dre",
  "balance_sheet",
  "faturamento",
])

export function buildCoverage({
  steps,
  docs,
  redFlags,
  opinion,
  hasCadastral,
}: {
  steps: StepLite[]
  docs: CreditDocumentRead[]
  redFlags: RedFlagLite[]
  opinion: OpinionLite
  hasCadastral: boolean
}): CoverageItem[] {
  const items: CoverageItem[] = []
  const byType = (t: string) => steps.filter((s) => s.nodeType === t)
  const agentName = (s: StepLite) =>
    String(
      (s.config as { agent?: string } | undefined)?.agent ??
        (s.output as { agent?: string } | undefined)?.agent ??
        "",
    )

  // 1 · Identificação
  const inputs = byType("human_input")
  if (inputs.length > 0) {
    const done = inputs.some((s) => s.state === "completed")
    items.push({
      id: "identificacao",
      label: "Identificação",
      detail: done ? "dados confirmados pelo analista" : "aguardando o analista",
      status: done ? "ok" : "warn",
    })
  }

  // 2 · Contrato social
  const scDoc = docs.find((d) => d.doc_type.toLowerCase() === "social_contract")
  const fetchSteps = byType("official_document_fetch")
  if (scDoc) {
    const validated = scDoc.extraction_status === "validated"
    const viaJunta = scDoc.original_filename?.startsWith("JUCESP_")
    items.push({
      id: "contrato_social",
      label: "Contrato social",
      detail: validated
        ? `${viaJunta ? "JUCESP · " : ""}homologado pelo analista`
        : "extraído — aguarda homologação",
      status: validated ? "ok" : "warn",
    })
  } else if (fetchSteps.length > 0) {
    const f = fetchSteps[0]
    const found = (f.output as { found?: boolean } | undefined)?.found
    items.push({
      id: "contrato_social",
      label: "Contrato social",
      detail:
        f.state === "completed" && found === false
          ? "não localizado na fonte oficial"
          : f.state === "running"
            ? "buscando na JUCESP…"
            : "não coletado",
      status: f.state === "completed" && found === false ? "warn" : "off",
    })
  }

  // 3 · Cadastral (Cartão CNPJ)
  const cadSteps = byType("cadastral_enrichment")
  items.push({
    id: "cadastral",
    label: "Cartão CNPJ / Cadastral",
    detail: hasCadastral
      ? "consultado e gravado"
      : cadSteps.length > 0
        ? "previsto no fluxo — ainda não rodou"
        : "não consultado",
    status: hasCadastral ? "ok" : cadSteps.length > 0 ? "warn" : "off",
  })

  // 4 · Faturamento
  const revDocs = docs.filter((d) =>
    REVENUE_DOC_TYPES.has(d.doc_type.toLowerCase()),
  )
  const revAnalyzed = steps.some(
    (s) => s.state === "completed" && agentName(s) === "revenue_analyst",
  )
  if (revDocs.length > 0 || revAnalyzed) {
    items.push({
      id: "faturamento",
      label: "Faturamento",
      detail: revAnalyzed
        ? `analisado (${revDocs.length} doc${revDocs.length === 1 ? "" : "s"})`
        : `${revDocs.length} doc(s) sem análise`,
      status: revAnalyzed ? "ok" : "warn",
    })
  }

  // 5 · Bureau de crédito
  const bureaus = byType("bureau_query")
  if (bureaus.length > 0) {
    const done = bureaus.filter((s) => s.state === "completed").length
    items.push({
      id: "bureau",
      label: "Bureau de crédito",
      detail: done > 0 ? `${done} consulta(s)` : "previsto — ainda não rodou",
      status: done > 0 ? "ok" : "warn",
    })
  }

  // 6 · Análises IA (especialistas, sem o parecerista)
  const agents = byType("specialist_agent").filter(
    (s) => agentName(s) !== "opinion_writer",
  )
  if (agents.length > 0) {
    const done = agents.filter((s) => s.state === "completed").length
    items.push({
      id: "analises",
      label: "Análises IA",
      detail: `${done}/${agents.length} concluída(s)`,
      status: done === agents.length ? "ok" : "warn",
    })
  }

  // 7 · Red flags
  const critical = redFlags.filter((f) => f.severity === "critical").length
  items.push({
    id: "redflags",
    label: "Red flags",
    detail:
      redFlags.length === 0
        ? "nenhum apontamento"
        : `${redFlags.length} apontamento(s)${critical ? ` · ${critical} crítico(s)` : ""}`,
    status: critical > 0 ? "bad" : redFlags.length > 0 ? "warn" : "ok",
  })

  // 8 · Parecer
  const reco = opinion?.recommendation
    ? RECO_LABEL[opinion.recommendation]
    : null
  items.push({
    id: "parecer",
    label: "Parecer",
    detail: reco ? `recomendação: ${reco.label}` : "pendente",
    status: reco ? reco.status : "off",
  })

  return items
}

export function DossierCoverageStrip({ items }: { items: CoverageItem[] }) {
  if (items.length === 0) return null
  return (
    <section className="rounded border border-gray-200 bg-white px-4 py-3 shadow-xs dark:border-gray-800 dark:bg-gray-950">
      <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-gray-500 dark:text-gray-400">
        O que foi analisado
      </p>
      <div className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3 lg:grid-cols-4">
        {items.map((it) => (
          <div key={it.id} className="flex items-start gap-2">
            <span
              className={cx("mt-1 size-2 shrink-0 rounded-full", DOT[it.status])}
              aria-hidden
            />
            <div className="min-w-0">
              <p className={cx("text-xs font-semibold leading-tight", TEXT[it.status])}>
                {it.label}
              </p>
              <p className="text-[11px] leading-tight text-gray-500 dark:text-gray-400">
                {it.detail}
              </p>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
