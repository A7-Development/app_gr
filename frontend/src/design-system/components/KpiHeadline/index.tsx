"use client"

/**
 * KpiHeadline — Z1 alternativa ao KpiStrip para paginas com pergunta dominante.
 *
 * Conceito: 1 statement curto + 1 numero primario destacado + chips de
 * diagnostico ao lado. Substitui o "tile syndrome" de 4 cards iguais em
 * paginas analiticas onde o usuario quer saber "o que mudou hoje?" e "tem
 * alguma anomalia?" de bate-pronto.
 *
 * Anatomia (2 linhas, ~70-80px altura total):
 *
 *   ┌────────────────────────────────────────────────────────────┐
 *   │ Cota Subordinada hoje variou                                │ ← linha 1 (statement)
 *   │                                                             │
 *   │ +0,31% · +R$ 36.942 vs D-1  [✓ ...] [✓ ...] [✓ ...]        │ ← linha 2 (number + chips)
 *   └────────────────────────────────────────────────────────────┘
 *
 * Quando ha anomalia, chips mudam de tone (warning/error) e podem incluir
 * acao (`onClick`). Altura do componente nao muda.
 *
 * Quando usar:
 *   - Pagina analitica com pergunta dominante ("o que mudou?")
 *   - Diagnostico/status mais importante que tabela de metricas
 *   - Ricardo's "tile syndrome" precisa ser evitado (paisagem de 4 cards iguais)
 *
 * Quando NAO usar:
 *   - Visao panoramica onde todos numeros importam igualmente (use `KpiStrip`)
 *   - Admin / sistema (use `KpiStrip` ou tabela)
 */

import * as React from "react"
import {
  RiArrowRightLine,
  RiCheckLine,
  RiErrorWarningLine,
  RiInformationLine,
} from "@remixicon/react"

import { cx } from "@/lib/utils"
import { Card } from "@/components/tremor/Card"

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

export type KpiHeadlineTone = "positive" | "negative" | "neutral"

export type DiagnosticTone = "ok" | "warning" | "error" | "info" | "action"

export type KpiHeadlineDiagnostic = {
  label:    string
  tone:     DiagnosticTone
  /** Click handler — quando presente o chip vira clicavel (action style). */
  onClick?: () => void
  /** Override do icone padrao (cada tone tem seu icone default). */
  icon?:    React.ComponentType<{ className?: string }>
}

export type KpiHeadlinePrimary = {
  /** Numero/string principal (ex.: "+0,31%"). */
  value: string
  /** Texto secundario logo apos (ex.: "+R$ 36.942 vs D-1"). */
  sub?:  string
  /** Cor do numero. Default: derivada da string (sinal); pode override. */
  tone?: KpiHeadlineTone
}

export interface KpiHeadlineProps {
  /** Texto da linha 1 — frase curta descrevendo a pergunta (ex.: "Cota Subordinada hoje variou"). */
  statement: string
  /** Numero/destaque principal da linha 2. */
  primary:   KpiHeadlinePrimary
  /** Chips de diagnostico ao lado do numero (linha 2). */
  diagnostics?: KpiHeadlineDiagnostic[]
  /** Estado de loading — renderiza skeleton com mesmas dimensoes. */
  loading?: boolean
  className?: string
}

// ─────────────────────────────────────────────────────────────────────────────
// Styles
// ─────────────────────────────────────────────────────────────────────────────

const PRIMARY_TONE: Record<KpiHeadlineTone, string> = {
  positive: "text-emerald-600 dark:text-emerald-400",
  negative: "text-red-600 dark:text-red-400",
  neutral:  "text-gray-900 dark:text-gray-50",
}

const DIAG_STYLES: Record<DiagnosticTone, { bg: string; text: string; icon: React.ComponentType<{ className?: string }> }> = {
  ok: {
    bg:   "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
    text: "text-emerald-700 dark:text-emerald-300",
    icon: RiCheckLine,
  },
  warning: {
    bg:   "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
    text: "text-amber-700 dark:text-amber-300",
    icon: RiErrorWarningLine,
  },
  error: {
    bg:   "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",
    text: "text-red-700 dark:text-red-300",
    icon: RiErrorWarningLine,
  },
  info: {
    bg:   "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300",
    text: "text-blue-700 dark:text-blue-300",
    icon: RiInformationLine,
  },
  action: {
    bg:   "bg-blue-50 text-blue-700 hover:bg-blue-100 dark:bg-blue-500/10 dark:text-blue-300 dark:hover:bg-blue-500/20",
    text: "text-blue-700 dark:text-blue-300",
    icon: RiArrowRightLine,
  },
}

// ─────────────────────────────────────────────────────────────────────────────
// Diagnostic chip
// ─────────────────────────────────────────────────────────────────────────────

function DiagnosticChip({ d }: { d: KpiHeadlineDiagnostic }) {
  const styles = DIAG_STYLES[d.tone]
  const Icon = d.icon ?? styles.icon
  const baseClass = cx(
    "inline-flex items-center gap-1 whitespace-nowrap rounded-sm px-2 py-0.5 text-[11px] font-medium",
    styles.bg,
  )

  if (d.onClick) {
    return (
      <button
        type="button"
        onClick={d.onClick}
        className={cx(baseClass, "transition-colors")}
      >
        <Icon className="size-3 shrink-0" aria-hidden="true" />
        <span>{d.label}</span>
      </button>
    )
  }

  return (
    <span className={baseClass}>
      <Icon className="size-3 shrink-0" aria-hidden="true" />
      <span>{d.label}</span>
    </span>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// KpiHeadline
// ─────────────────────────────────────────────────────────────────────────────

export function KpiHeadline({
  statement,
  primary,
  diagnostics,
  loading = false,
  className,
}: KpiHeadlineProps) {
  if (loading) {
    return (
      <Card className={cx("flex flex-col gap-2 px-4 py-3", className)}>
        <div className="h-3 w-48 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
        <div className="h-7 w-72 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
      </Card>
    )
  }

  // Derive tone do primary a partir do sinal do valor quando nao explicitamente
  // passado. "+" -> positive; "-" / "(" -> negative; resto -> neutral.
  const primaryTone: KpiHeadlineTone =
    primary.tone ??
    (primary.value.trimStart().startsWith("+") ? "positive" :
     primary.value.trimStart().startsWith("-") || primary.value.trimStart().startsWith("(") ? "negative" :
     "neutral")

  return (
    <Card className={cx("flex flex-col gap-1 px-4 py-3", className)}>
      {/* Linha 1 — eyebrow uppercase, alinhado com KpiCard canonico
          (text-[11px] tracking-[0.05em] font-medium uppercase gray-500). */}
      <p className="text-[11px] font-medium uppercase tracking-[0.05em] leading-tight text-gray-500 dark:text-gray-400">
        {statement}
      </p>

      {/* Linha 2 — number + chips. justify-between em wide; wrap em narrow */}
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1.5">
        <div className="flex items-baseline gap-2">
          <span
            className={cx(
              "text-[26px] font-semibold leading-tight tabular-nums tracking-tight",
              PRIMARY_TONE[primaryTone],
            )}
          >
            {primary.value}
          </span>
          {primary.sub && (
            <span className="text-[13px] text-gray-500 dark:text-gray-400">
              ({primary.sub})
            </span>
          )}
        </div>

        {diagnostics && diagnostics.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            {diagnostics.map((d, i) => (
              <DiagnosticChip key={`${d.label}:${i}`} d={d} />
            ))}
          </div>
        )}
      </div>
    </Card>
  )
}
