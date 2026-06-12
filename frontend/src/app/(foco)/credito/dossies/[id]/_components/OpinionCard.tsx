"use client"

import * as React from "react"
import {
  RiAlertLine,
  RiCheckboxCircleFill,
  RiCloseCircleFill,
  RiErrorWarningLine,
  RiInformationLine,
  RiShieldCheckLine,
} from "@remixicon/react"

import { Card } from "@/components/tremor/Card"
import { cardTokens } from "@/design-system/tokens/card"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

// ─── Types ───────────────────────────────────────────────────────────────

type Recommendation = "approve" | "deny" | "conditional"

type RedFlag = {
  severity: "critical" | "important" | "informational"
  title: string
  description: string
  evidence: string
}

export type OpinionDraft = {
  executive_summary: string
  strengths: string[]
  concerns: string[]
  recommendation: Recommendation
  conditions: string[] | null
  rationale: string
}

export type IndebtednessAnalysis = {
  total_debt_brl: number | null
  debt_concentration_top1_pct: number | null
  debt_concentration_top3_pct: number | null
  debt_to_revenue_pct: number | null
  declared_vs_scr_consistency: "consistent" | "minor_diff" | "major_diff" | "unknown"
  summary: string
  red_flags: RedFlag[]
}

// ─── Visual tokens ───────────────────────────────────────────────────────

const RECOMMENDATION_META: Record<
  Recommendation,
  { label: string; tone: string; icon: typeof RiShieldCheckLine }
> = {
  approve: {
    label: "APROVAR",
    tone: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/30",
    icon: RiShieldCheckLine,
  },
  conditional: {
    label: "APROVAR COM CONDIÇÕES",
    tone: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:border-amber-500/30",
    icon: RiAlertLine,
  },
  deny: {
    label: "NEGAR",
    tone: "bg-red-50 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/30",
    icon: RiCloseCircleFill,
  },
}

const SEVERITY_META: Record<
  RedFlag["severity"],
  { label: string; tone: string; icon: typeof RiErrorWarningLine }
> = {
  critical: {
    label: "Crítico",
    tone: "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",
    icon: RiErrorWarningLine,
  },
  important: {
    label: "Importante",
    tone: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
    icon: RiAlertLine,
  },
  informational: {
    label: "Informativo",
    tone: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
    icon: RiInformationLine,
  },
}

// ─── Helpers ─────────────────────────────────────────────────────────────

function formatPercent(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—"
  return `${v.toFixed(1)}%`
}

function formatBRL(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—"
  return v.toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function consistencyLabel(c: IndebtednessAnalysis["declared_vs_scr_consistency"]): {
  label: string
  tone: string
} {
  switch (c) {
    case "consistent":
      return {
        label: "Consistente",
        tone: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
      }
    case "minor_diff":
      return {
        label: "Diferença leve",
        tone: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
      }
    case "major_diff":
      return {
        label: "Diferença significativa",
        tone: "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",
      }
    default:
      return {
        label: "Sem comparação",
        tone: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
      }
  }
}

// ─── Component ───────────────────────────────────────────────────────────

export function OpinionCard({
  opinion,
  indebtedness,
}: {
  opinion: OpinionDraft
  indebtedness?: IndebtednessAnalysis | null
}) {
  const recoMeta = RECOMMENDATION_META[opinion.recommendation]
  const RecoIcon = recoMeta.icon

  const allRedFlags = indebtedness?.red_flags ?? []
  const sortedFlags = [...allRedFlags].sort((a, b) => {
    const order: Record<RedFlag["severity"], number> = {
      critical: 0,
      important: 1,
      informational: 2,
    }
    return order[a.severity] - order[b.severity]
  })

  return (
    <Card>
      <div className={cardTokens.header}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className={cardTokens.headerTitle}>Parecer</p>
            <p className={cx(cardTokens.headerSubtitle, "mt-0.5")}>
              Síntese gerada pelo agente IA
            </p>
          </div>
          <span
            className={cx(
              "inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-semibold uppercase tracking-wide",
              recoMeta.tone,
            )}
          >
            <RecoIcon className="size-4" aria-hidden />
            {recoMeta.label}
          </span>
        </div>
      </div>

      <div className={cardTokens.body}>
        <p className="text-sm leading-relaxed text-gray-800 dark:text-gray-200">
          {opinion.executive_summary}
        </p>

        {opinion.rationale && (
          <p className="mt-3 text-xs italic text-gray-600 dark:text-gray-400">
            {opinion.rationale}
          </p>
        )}

        <div className="mt-5 grid grid-cols-1 gap-5 md:grid-cols-2">
          {opinion.strengths.length > 0 && (
            <div>
              <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-400">
                <RiCheckboxCircleFill className="size-4" aria-hidden />
                Pontos fortes
              </p>
              <ul className="space-y-1.5">
                {opinion.strengths.map((s, i) => (
                  <li
                    key={i}
                    className="flex gap-2 text-sm text-gray-800 dark:text-gray-200"
                  >
                    <span className="mt-1 size-1 shrink-0 rounded-full bg-emerald-500" />
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {opinion.concerns.length > 0 && (
            <div>
              <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-400">
                <RiAlertLine className="size-4" aria-hidden />
                Pontos de atenção
              </p>
              <ul className="space-y-1.5">
                {opinion.concerns.map((c, i) => (
                  <li
                    key={i}
                    className="flex gap-2 text-sm text-gray-800 dark:text-gray-200"
                  >
                    <span className="mt-1 size-1 shrink-0 rounded-full bg-amber-500" />
                    <span>{c}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {(opinion.conditions?.length ?? 0) > 0 && (
          <div className="mt-5 rounded-md border border-amber-200 bg-amber-50/50 p-3 dark:border-amber-500/30 dark:bg-amber-500/5">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-amber-800 dark:text-amber-300">
              Condições para aprovação
            </p>
            <ul className="space-y-1">
              {(opinion.conditions ?? []).map((cond, i) => (
                <li
                  key={i}
                  className="flex gap-2 text-sm text-gray-800 dark:text-gray-200"
                >
                  <span className="font-mono text-xs text-amber-700 dark:text-amber-400">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <span>{cond}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {sortedFlags.length > 0 && (
          <div className="mt-5">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-700 dark:text-gray-300">
              Red flags identificados
            </p>
            <ul className="space-y-2">
              {sortedFlags.map((flag, i) => {
                const sevMeta = SEVERITY_META[flag.severity]
                const SevIcon = sevMeta.icon
                return (
                  <li
                    key={i}
                    className="flex gap-2 rounded-md border border-gray-100 bg-gray-50/50 p-2.5 dark:border-gray-900 dark:bg-gray-950/50"
                  >
                    <SevIcon
                      className={cx(
                        "mt-0.5 size-4 shrink-0",
                        flag.severity === "critical" && "text-red-500",
                        flag.severity === "important" && "text-amber-500",
                        flag.severity === "informational" && "text-gray-500",
                      )}
                      aria-hidden
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                          {flag.title}
                        </span>
                        <span className={cx(tableTokens.badge, sevMeta.tone)}>
                          {sevMeta.label}
                        </span>
                      </div>
                      <p className="mt-0.5 text-xs text-gray-700 dark:text-gray-300">
                        {flag.description}
                      </p>
                      {flag.evidence && (
                        <p className="mt-0.5 text-[11px] italic text-gray-500 dark:text-gray-500">
                          Evidência: {flag.evidence}
                        </p>
                      )}
                    </div>
                  </li>
                )
              })}
            </ul>
          </div>
        )}

        {indebtedness && <IndicatorsRow indebtedness={indebtedness} />}
      </div>
    </Card>
  )
}

// ─── Indicators row ──────────────────────────────────────────────────────

function IndicatorsRow({
  indebtedness,
}: {
  indebtedness: IndebtednessAnalysis
}) {
  const consistency = consistencyLabel(indebtedness.declared_vs_scr_consistency)
  const items: Array<{ label: string; value: string; mono?: boolean }> = [
    {
      label: "Dívida total",
      value: formatBRL(indebtedness.total_debt_brl),
      mono: true,
    },
    {
      label: "Dívida ÷ Receita",
      value: formatPercent(indebtedness.debt_to_revenue_pct),
      mono: true,
    },
    {
      label: "Concentração top 1",
      value: formatPercent(indebtedness.debt_concentration_top1_pct),
      mono: true,
    },
    {
      label: "Concentração top 3",
      value: formatPercent(indebtedness.debt_concentration_top3_pct),
      mono: true,
    },
  ]

  return (
    <div className="mt-5 border-t border-gray-100 pt-4 dark:border-gray-900">
      <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-700 dark:text-gray-300">
        Indicadores de endividamento
      </p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {items.map((item) => (
          <div key={item.label}>
            <p className="text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-500">
              {item.label}
            </p>
            <p
              className={cx(
                "mt-0.5 text-sm font-semibold text-gray-900 dark:text-gray-100",
                item.mono && "tabular-nums",
              )}
            >
              {item.value}
            </p>
          </div>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-500">
          SCR vs declarado:
        </span>
        <span className={cx(tableTokens.badge, consistency.tone)}>
          {consistency.label}
        </span>
      </div>
    </div>
  )
}
