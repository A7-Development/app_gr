// DossierReadingView — o dossiê de leitura (handoff frame D4): a PROJEÇÃO
// compilada do fluxo. Documento centrado (max 860px) sobre gray-50:
// capa (eyebrow + nome 24/700 + régua 2px) → resumo da decisão → banda de
// indicadores com sups de lastro → §seções (na ordem das estações) →
// parecer com assinatura declarada → lastro (grid 2 col, 100% rastreável).
//
// O que o diretor lê AQUI é o que o analista fechou nas estações — paridade
// total tela ↔ PDF (Exportar = projeção do mesmo documento).

"use client"

import * as React from "react"
import {
  RiCheckboxCircleFill,
  RiCloseCircleLine,
  RiErrorWarningLine,
  RiFileDownloadLine,
  RiHistoryLine,
} from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import {
  ProvenanceSup,
  SectionRenderer,
  StrataIcon,
} from "@/design-system/components"
import type { StationDescriptor } from "@/design-system/types/section"
import type { WizardMultiStepStep } from "@/design-system/patterns/WizardMultiStep"
import { provenanceTokens, type ProvenanceOrigin } from "@/design-system/tokens/provenance"
import type {
  CreditDocumentRead,
  DossierRead,
  RedFlagItem,
  RevenueAnalysis,
} from "@/lib/credito-client"
import { cx } from "@/lib/utils"

import {
  DossierCoverageStrip,
  type CoverageItem,
} from "./DossierCoverageStrip"
import { CadastralCard } from "./CadastralCard"

type OpinionOutput = {
  executive_summary?: string
  recommendation?: "approve" | "conditional" | "deny"
  strengths?: string[]
  concerns?: string[]
  conditions?: string[] | null
}

export type LastroEntry = {
  origin: ProvenanceOrigin
  index: number
  description: string
  stationId?: string
}

export function DossierReadingView({
  coverage,
  dossier,
  docs,
  redFlags,
  revenueOutput,
  opinionOutput,
  hasCadastral,
  agentSteps,
  adjustments,
  progressPct,
  trailCount,
  onOpenTrail,
  onGoToStation,
  descriptorStations,
  workflowName,
  workflowVersion,
  analystName,
}: {
  coverage?: CoverageItem[]
  /** Quando presente (flag ?descriptor=1), o §miolo vem do /descriptor (read-mode). */
  descriptorStations?: StationDescriptor[]
  dossier: DossierRead
  docs: CreditDocumentRead[]
  redFlags: RedFlagItem[]
  revenueOutput: RevenueAnalysis | null
  opinionOutput: OpinionOutput | null
  hasCadastral: boolean
  /** Agentes que concluíram (para o lastro IA). */
  agentSteps: WizardMultiStepStep[]
  /** Ajustes do analista (docs editados etc.) para o lastro A. */
  adjustments: string[]
  progressPct: number
  trailCount: number
  onOpenTrail: () => void
  onGoToStation?: (id: string) => void
  /** Cabeçalho de auditoria (handoff workflow, snapshot 07): workflow de
   *  origem + versão + analista responsável. A conclusão vem de finalized_at. */
  workflowName?: string | null
  workflowVersion?: number | null
  analystName?: string | null
}) {
  const titleLabel =
    dossier.target_name ??
    (dossier.target_cnpj ? `CNPJ ${dossier.target_cnpj}` : "Análise sem identidade")

  // ── Série mensal do documento homologado (D1) ────────────────────────────
  const primaryDoc = docs.find((d) => {
    const f = ((d.ai_extraction as Record<string, unknown> | null)?.extracted_fields ??
      null) as Record<string, unknown> | null
    return Array.isArray(f?.monthly) && (f!.monthly as unknown[]).length > 0
  })
  const monthly: Array<{ month: string; value: number }> = React.useMemo(() => {
    const f = ((primaryDoc?.ai_extraction as Record<string, unknown> | null)
      ?.extracted_fields ?? null) as { monthly?: unknown } | null
    if (!f || !Array.isArray(f.monthly)) return []
    return (f.monthly as Array<Record<string, unknown>>).map((r) => ({
      month: String(r.month ?? ""),
      value: Number(r.value ?? 0),
    }))
  }, [primaryDoc])

  const sum = monthly.reduce((a, r) => a + r.value, 0)
  const avg = monthly.length ? sum / monthly.length : 0

  // ── Lastro (numeração estável: D docs, F fontes, IA agentes, A ajustes) ──
  const lastro: LastroEntry[] = React.useMemo(() => {
    const entries: LastroEntry[] = []
    docs.forEach((d, i) =>
      entries.push({
        origin: "documento",
        index: i + 1,
        description: `${d.original_filename}${d.extraction_status === "validated" ? " · homologado" : ""}`,
      }),
    )
    if (hasCadastral) {
      entries.push({
        origin: "fonte",
        index: 1,
        description: "Receita Federal via BDC · dados cadastrais oficiais",
      })
    }
    agentSteps.forEach((s, i) =>
      entries.push({
        origin: "agente",
        index: i + 1,
        description: `${s.label} · conclusão registrada na trilha`,
        stationId: s.id,
      }),
    )
    adjustments.forEach((a, i) =>
      entries.push({ origin: "analista", index: i + 1, description: a }),
    )
    return entries
  }, [docs, hasCadastral, agentSteps, adjustments])

  const recoMeta =
    opinionOutput?.recommendation === "approve"
      ? { label: "Aprovação", color: "#059669", Icon: RiCheckboxCircleFill }
      : opinionOutput?.recommendation === "deny"
        ? { label: "Negada", color: "#DC2626", Icon: RiCloseCircleLine }
        : opinionOutput
          ? { label: "Aprovação condicional", color: "#059669", Icon: RiCheckboxCircleFill }
          : null

  const sortedFlags = [...redFlags].sort((a, b) => severityRank(a) - severityRank(b))

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col">
      {/* Toolbar */}
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-gray-200 bg-white px-8 dark:border-gray-800 dark:bg-gray-950">
        <span className="text-[13px] text-gray-500 dark:text-gray-400">
          Dossiê de crédito ·{" "}
          <strong className="font-semibold text-gray-900 dark:text-gray-50">
            {dossier.status === "finalized"
              ? "pronto para o comitê"
              : `${progressPct}% montado`}
          </strong>
        </span>
        <div className="flex items-center gap-1.5">
          <Button variant="ghost" className="h-8" onClick={onOpenTrail}>
            <RiHistoryLine className="mr-1.5 size-4" aria-hidden />
            Trilha · {trailCount} eventos
          </Button>
          <Button className="h-8" onClick={() => window.print()}>
            <RiFileDownloadLine className="mr-1.5 size-4" aria-hidden />
            Exportar PDF
          </Button>
        </div>
      </div>

      {/* Documento */}
      <div className="flex-1 overflow-y-auto bg-gray-50 px-8 pt-7 dark:bg-gray-925">
        <article className="mx-auto max-w-[860px] rounded-t border border-gray-200 bg-white px-14 py-12 shadow-xs dark:border-gray-800 dark:bg-gray-950">
          {/* Raio-X de cobertura — bate o olho e sabe o que foi visto. */}
          {coverage && coverage.length > 0 && (
            <div className="mb-8">
              <DossierCoverageStrip items={coverage} />
            </div>
          )}
          {/* Capa */}
          <header className="flex items-start justify-between border-b-2 border-gray-900 pb-6 dark:border-gray-100">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500">
                Dossiê de crédito · {dossier.code ?? dossier.id.slice(0, 8).toUpperCase()}
              </p>
              <h1 className="mt-1.5 text-2xl font-bold tracking-[-0.02em] text-gray-900 dark:text-gray-50">
                {titleLabel}
              </h1>
              <p className="mt-1 text-[13px] text-gray-500 tabular-nums dark:text-gray-400">
                {dossier.target_cnpj && <>CNPJ {dossier.target_cnpj} · </>}
                {dossier.status === "finalized" && dossier.finalized_at
                  ? `concluído em ${fmtDate(dossier.finalized_at)}`
                  : `em montagem · atualizado em ${fmtDate(dossier.updated_at)}`}
              </p>
            </div>
            <StrataIcon height={36} />
          </header>

          {/* Cabeçalho de auditoria — workflow de origem + analista + conclusão
              (handoff workflow JUCESP, snapshot 07). Requisito de auditoria:
              quem decidiu, com base em qual workflow/versão, e quando fechou. */}
          <section className="grid grid-cols-3 gap-6 border-b border-gray-100 py-5 dark:border-gray-900">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500">
                Workflow
              </p>
              <p className="mt-1 text-[13px] font-medium leading-snug text-gray-900 dark:text-gray-100">
                {workflowName ?? "—"}
              </p>
              {workflowVersion != null && (
                <p className="mt-0.5 text-[11px] text-gray-400 tabular-nums dark:text-gray-500">
                  v{workflowVersion}
                </p>
              )}
            </div>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500">
                Analista
              </p>
              <p className="mt-1 text-[13px] font-medium text-gray-900 dark:text-gray-100">
                {analystName ?? "—"}
              </p>
            </div>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500">
                Conclusão
              </p>
              <p className="mt-1 text-[13px] font-medium text-gray-900 tabular-nums dark:text-gray-100">
                {dossier.status === "finalized" && dossier.finalized_at
                  ? fmtDate(dossier.finalized_at)
                  : "Em andamento"}
              </p>
            </div>
          </section>

          {/* Resumo da decisão */}
          {opinionOutput && recoMeta ? (
            <section className="grid grid-cols-[auto_1fr] gap-5 border-b border-gray-100 py-6 dark:border-gray-900">
              <div className="border-r border-gray-100 pr-6 dark:border-gray-900">
                <p
                  className="flex items-center gap-1.5 text-[15px] font-bold"
                  style={{ color: recoMeta.color }}
                >
                  <recoMeta.Icon className="size-[18px]" aria-hidden />
                  {recoMeta.label}
                </p>
                {dossier.requested_amount && (
                  <>
                    <p className="mt-2 text-[26px] font-bold tracking-[-0.025em] text-gray-900 tabular-nums dark:text-gray-50">
                      {fmtBRLFull(Number(dossier.requested_amount))}
                    </p>
                    <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
                      valor pleiteado na análise
                    </p>
                  </>
                )}
              </div>
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-400">
                  {opinionOutput.conditions?.length ? "Condições" : "Síntese"}
                </p>
                {opinionOutput.conditions?.length ? (
                  <ol className="mt-2 space-y-1.5">
                    {opinionOutput.conditions.map((c, i) => (
                      <li key={i} className="flex gap-2 text-[13px] leading-[1.55] text-gray-700 dark:text-gray-300">
                        <span className="font-semibold text-gray-400 tabular-nums">
                          {String(i + 1).padStart(2, "0")}
                        </span>
                        {c}
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="mt-2 text-[13px] leading-[1.6] text-gray-700 dark:text-gray-300">
                    {opinionOutput.executive_summary}
                  </p>
                )}
              </div>
            </section>
          ) : (
            <section className="border-b border-gray-100 py-6 dark:border-gray-900">
              <p className="text-[13px] text-gray-400">
                Resumo da decisão — aparece quando o parecer for assinado. Dossiê{" "}
                {progressPct}% montado.
              </p>
            </section>
          )}

          {/* Indicadores-chave */}
          <section className="grid grid-cols-2 gap-y-4 border-b border-gray-100 py-5 sm:grid-cols-4 dark:border-gray-900">
            <Indicator
              label="Faturamento médio mensal"
              value={monthly.length ? fmtBRLCompact(avg) : "—"}
              sup={monthly.length ? { origin: "documento", index: 1 } : undefined}
              first
            />
            <Indicator
              label="Tendência"
              value={
                revenueOutput
                  ? `${revenueOutput.tendencia.direcao} · ${revenueOutput.tendencia.intensidade}`
                  : "—"
              }
              sup={revenueOutput ? { origin: "agente", index: 1 } : undefined}
            />
            <Indicator
              label="Meses analisados"
              value={monthly.length ? String(monthly.length) : "—"}
              sup={monthly.length ? { origin: "documento", index: 1 } : undefined}
            />
            <Indicator
              label="Apontamentos"
              value={`${redFlags.length}${redFlags.some((f) => f.severity === "critical") ? " · crítico" : ""}`}
            />
          </section>

          {descriptorStations ? (
            /* §miolo UNIFICADO: as §seções vêm do /descriptor via SectionRenderer
               read-mode (Fase 1 / Etapa 1.4 — mesma gramática do workbench). Flag
               ?descriptor=1. Sem flag, cai no miolo hand-built abaixo. */
            descriptorStations
              .filter((st) => st.sections.length > 0)
              .map((st) => (
                <SectionBlock key={st.id} title={st.label}>
                  <div className="space-y-4">
                    {st.sections.map((sec) => (
                      <SectionRenderer key={sec.id} section={sec} mode="read" />
                    ))}
                  </div>
                </SectionBlock>
              ))
          ) : (
            <>
              {/* §Cadastral */}
              {hasCadastral && (
                <SectionBlock title="Identificação e cadastro">
                  <CadastralCard dossierId={dossier.id} />
                  <SourceNote>
                    Fonte: Receita Federal via BDC
                    <ProvenanceSup origin="fonte" index={1} />
                  </SourceNote>
                </SectionBlock>
              )}

              {/* §Faturamento — série mensal via bloco canônico `serie_temporal`. */}
              {monthly.length > 0 && (
                <SectionBlock title="Faturamento">
                  <SectionRenderer
                    mode="read"
                    section={{
                      id: "dossie-faturamento-serie",
                      stationId: "faturamento",
                      titulo: "Faturamento",
                      generatesDossierSection: false,
                      blocks: [
                        {
                          id: "fat-serie",
                          type: "serie_temporal",
                          titulo: "Faturamento mensal",
                          kpi: {
                            eyebrow: `Faturamento mensal · ${monthly.length} meses`,
                            valor: fmtBRLCompact(avg) ?? "—",
                            contexto: `média mensal · total ${fmtBRLCompact(sum) ?? "—"}`,
                          },
                          pontos: monthly.map((r) => ({
                            periodo: fmtMonth(r.month),
                            valor: r.value,
                          })),
                          formato: "brl",
                        },
                      ],
                    }}
                  />
                  <SourceNote>
                    Fonte: {primaryDoc?.original_filename ?? "documento homologado"}
                    <ProvenanceSup origin="documento" index={1} />
                    {revenueOutput && (
                      <>
                        {" "}
                        · leitura do agente: {revenueOutput.leitura_para_credito}
                        <ProvenanceSup origin="agente" index={1} />
                      </>
                    )}
                  </SourceNote>
                </SectionBlock>
              )}
            </>
          )}

          {/* §Apontamentos */}
          {sortedFlags.length > 0 && (
            <SectionBlock title="Apontamentos e cruzamentos">
              <ul className="space-y-2.5">
                {sortedFlags.map((f) => (
                  <li key={f.id} className="flex items-start gap-2.5">
                    <RiErrorWarningLine
                      className={cx(
                        "mt-0.5 size-4 shrink-0",
                        f.severity === "critical"
                          ? "text-red-600"
                          : f.severity === "important"
                            ? "text-amber-600"
                            : "text-gray-400",
                      )}
                      aria-hidden
                    />
                    <div>
                      <p className="text-[13px] font-semibold text-gray-900 dark:text-gray-50">
                        {f.title}
                        <span className="ml-2 text-[10px] font-semibold uppercase tracking-[0.04em] text-gray-400">
                          {f.severity === "critical"
                            ? "crítico"
                            : f.severity === "important"
                              ? "importante"
                              : "informativo"}
                        </span>
                      </p>
                      <p className="mt-0.5 text-[12.5px] leading-relaxed text-gray-600 dark:text-gray-400">
                        {f.description}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            </SectionBlock>
          )}

          {/* §Parecer */}
          {opinionOutput && (
            <SectionBlock title="Parecer do analista">
              <p className="text-sm leading-[1.85] text-gray-700 dark:text-gray-300" style={{ textWrap: "pretty" }}>
                {opinionOutput.executive_summary}
              </p>
              {(opinionOutput.strengths?.length || opinionOutput.concerns?.length) ? (
                <div className="mt-4 grid grid-cols-1 gap-5 sm:grid-cols-2">
                  {opinionOutput.strengths && opinionOutput.strengths.length > 0 && (
                    <div>
                      <p className="text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-400">
                        Pontos fortes
                      </p>
                      <ul className="mt-1.5 space-y-1">
                        {opinionOutput.strengths.map((s, i) => (
                          <li key={i} className="flex gap-1.5 text-[12.5px] leading-relaxed text-gray-700 dark:text-gray-300">
                            <RiCheckboxCircleFill className="mt-0.5 size-3.5 shrink-0" style={{ color: "#059669" }} aria-hidden />
                            {s}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {opinionOutput.concerns && opinionOutput.concerns.length > 0 && (
                    <div>
                      <p className="text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-400">
                        Pontos de atenção
                      </p>
                      <ul className="mt-1.5 space-y-1">
                        {opinionOutput.concerns.map((s, i) => (
                          <li key={i} className="flex gap-1.5 text-[12.5px] leading-relaxed text-gray-700 dark:text-gray-300">
                            <RiErrorWarningLine className="mt-0.5 size-3.5 shrink-0 text-amber-600" aria-hidden />
                            {s}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ) : null}
              {dossier.status === "finalized" && (
                <div className="mt-5 flex items-center gap-2.5 border-t border-gray-100 pt-4 dark:border-gray-900">
                  <span className="flex size-7 items-center justify-center rounded-full bg-gray-800 text-[10px] font-semibold text-white">
                    {initials(dossier.analyst_id)}
                  </span>
                  <div>
                    <p className="text-[12.5px] font-semibold text-gray-900 dark:text-gray-50">
                      Analista responsável
                    </p>
                    <p className="text-[11px] text-gray-400">
                      parecer assinado em {dossier.finalized_at ? fmtDate(dossier.finalized_at) : "—"} ·
                      rascunho inicial da IA, editado pelo analista — colaboração declarada
                    </p>
                  </div>
                </div>
              )}
            </SectionBlock>
          )}

          {/* Lastro */}
          {lastro.length > 0 && (
            <section className="border-t border-gray-100 pb-2 pt-4 dark:border-gray-900">
              <p className="text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-400">
                Lastro do dossiê — {lastro.length} origens, 100% rastreáveis
              </p>
              <div className="mt-2.5 grid grid-cols-1 gap-x-8 gap-y-1.5 sm:grid-cols-2">
                {lastro.map((e) => {
                  const t = provenanceTokens[e.origin]
                  const code = `${t.supPrefix}${e.index}`
                  const row = (
                    <span className="flex gap-2 text-[11px] leading-normal text-gray-500 dark:text-gray-400">
                      <span className="shrink-0 font-semibold" style={{ color: t.color }}>
                        {code}
                      </span>
                      <span className="min-w-0">{e.description}</span>
                    </span>
                  )
                  if (e.stationId && onGoToStation) {
                    return (
                      <button
                        key={`${code}-${e.description}`}
                        type="button"
                        onClick={() => onGoToStation(e.stationId!)}
                        className="rounded text-left hover:bg-gray-50 dark:hover:bg-gray-900"
                      >
                        {row}
                      </button>
                    )
                  }
                  return <div key={`${code}-${e.description}`}>{row}</div>
                })}
                <button
                  type="button"
                  onClick={onOpenTrail}
                  className="text-left text-[11px] font-medium text-blue-600 hover:text-blue-700 dark:text-blue-400"
                >
                  ver as origens na trilha →
                </button>
              </div>
            </section>
          )}
        </article>
      </div>
    </div>
  )
}

// ─── Blocos ─────────────────────────────────────────────────────────────────

function SectionBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-b border-gray-100 py-6 dark:border-gray-900">
      <h2 className="mb-3.5 text-sm font-semibold text-gray-900 dark:text-gray-50">
        {title}
      </h2>
      {children}
    </section>
  )
}

function SourceNote({ children }: { children: React.ReactNode }) {
  return <p className="mt-2 text-[11px] text-gray-400 dark:text-gray-500">{children}</p>
}

function Indicator({
  label,
  value,
  sup,
  first,
}: {
  label: string
  value: string
  sup?: { origin: ProvenanceOrigin; index: number }
  first?: boolean
}) {
  return (
    <div className={cx("px-5", first ? "pl-0" : "border-l border-gray-100 dark:border-gray-900")}>
      <p className="text-[10px] font-semibold uppercase tracking-[0.05em] text-gray-400">
        {label}
      </p>
      <p className="mt-1 text-[17px] font-semibold text-gray-900 tabular-nums dark:text-gray-50">
        {value}
        {sup && <ProvenanceSup origin={sup.origin} index={sup.index} />}
      </p>
    </div>
  )
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function severityRank(f: RedFlagItem): number {
  return f.severity === "critical" ? 0 : f.severity === "important" ? 1 : 2
}

function initials(s: string | null): string {
  if (!s) return "—"
  return s.slice(0, 2).toUpperCase()
}

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("pt-BR")
  } catch {
    return iso
  }
}

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" })

function fmtBRLFull(v: number): string {
  if (!Number.isFinite(v)) return "—"
  return brl.format(v)
}

function fmtBRLCompact(v: number): string {
  const fmt = (n: number) =>
    n.toLocaleString("pt-BR", { maximumFractionDigits: 2 })
  if (Math.abs(v) >= 1_000_000_000) return `R$ ${fmt(v / 1_000_000_000)} bi`
  if (Math.abs(v) >= 1_000_000) return `R$ ${fmt(v / 1_000_000)} mi`
  if (Math.abs(v) >= 1_000) return `R$ ${fmt(v / 1_000)} mil`
  return brl.format(v)
}

function fmtMonth(s: string): string {
  const m = /^(\d{4})-(\d{2})$/.exec(s)
  if (!m) return s
  const months = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
  const idx = Number(m[2]) - 1
  return months[idx] ? `${months[idx]}/${m[1].slice(2)}` : s
}
