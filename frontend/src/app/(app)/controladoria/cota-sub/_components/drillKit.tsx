/**
 * drillKit — primitivos visuais COMPARTILHADOS dos drills da Cota Sub.
 *
 * Padroniza a linguagem visual entre DrillDcContent / DrillPddContent /
 * DrillCprContent / DrillOrigemContent (que antes duplicavam formatadores,
 * titulo de secao e estilo de tabela divergente). Domain-specific (cota-sub),
 * por isso vive em _components/ e nao no design-system.
 *
 * Fase A da padronizacao do card de detalhamento (2026-05-28). Fase B
 * (base "ver origem" comum + extensao rica) vem depois.
 */

import {
  RiCheckboxCircleFill,
  RiErrorWarningFill,
  type RemixiconComponentType,
} from "@remixicon/react"
import type * as React from "react"

import { cx } from "@/lib/utils"

// ── Formatadores (unico ponto de verdade) ──────────────────────────────────

export const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style:                 "currency",
  currency:              "BRL",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

export function fmtBRLSigned(v: number): string {
  if (Math.abs(v) < 0.005) return "R$ 0,00"
  return `${v > 0 ? "+" : "−"}${fmtBRL.format(Math.abs(v))}`
}

/**
 * Cor de delta unificada (emerald = bom · red = ruim · gray = neutro).
 * `goodWhenPositive=false` inverte a polaridade — ex.: PDD, onde MAIS provisao
 * e ruim e reversao (delta<0) e bom.
 */
export function toneClass(v: number, goodWhenPositive = true): string {
  if (Math.abs(v) < 0.005) return "text-gray-400 dark:text-gray-600"
  const good = goodWhenPositive ? v > 0 : v < 0
  return good
    ? "text-emerald-700 dark:text-emerald-400"
    : "text-red-700 dark:text-red-400"
}

// ── Classes compartilhadas de tabela ────────────────────────────────────────

/** Container bordado de tabela/bloco. */
export const drillTableWrap =
  "overflow-hidden rounded border border-gray-200 dark:border-gray-800"

/** Cabecalho de tabela canonico (faixa cinza-50 — estilo unificado). */
export const drillThead =
  "bg-gray-50 text-[10px] font-medium uppercase tracking-[0.04em] text-gray-500 dark:bg-gray-900/30 dark:text-gray-400"

/** Borda entre linhas do corpo. */
export const drillRowBorder = "border-t border-gray-100 dark:border-gray-900"

/** Linha Total no rodape da tabela (tfoot). */
export const drillTfootRow =
  "border-t-2 border-gray-200 font-semibold dark:border-gray-700"

// ── Selo de fechamento (universal — topo de todo card de drill) ─────────────

/**
 * Badge verde/vermelho de conferenciabilidade. A mensagem principal vai em
 * `children`; `sub` e uma 2a linha opcional (ex.: "balanço X · soma Y" quando
 * diverge). Mesma identidade visual em DC/PDD/CPR/Origem.
 */
export function DrillClosureBadge({
  fecha, children, sub,
}: {
  fecha:     boolean
  children:  React.ReactNode
  sub?:      React.ReactNode
}) {
  return (
    <div className={cx(
      "flex items-start gap-2 rounded border px-3 py-2",
      fecha
        ? "border-emerald-200 bg-emerald-50/50 dark:border-emerald-900/60 dark:bg-emerald-950/20"
        : "border-red-200 bg-red-50/50 dark:border-red-900/60 dark:bg-red-950/20",
    )}>
      {fecha ? (
        <RiCheckboxCircleFill className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400" aria-hidden />
      ) : (
        <RiErrorWarningFill className="mt-0.5 size-4 shrink-0 text-red-600 dark:text-red-400" aria-hidden />
      )}
      <div className="flex flex-col">
        <span className={cx(
          "text-[12px] font-medium",
          fecha ? "text-emerald-800 dark:text-emerald-300" : "text-red-800 dark:text-red-300",
        )}>
          {children}
        </span>
        {sub != null && sub !== "" && (
          <span className="text-[11px] tabular-nums text-gray-600 dark:text-gray-400">{sub}</span>
        )}
      </div>
    </div>
  )
}

// ── Titulo de secao (versao rica, com help opcional + tom de alerta) ────────

export function DrillSectionTitle({
  icon: Icon, label, counter, help, tone = "neutral",
}: {
  icon:     RemixiconComponentType
  label:    string
  counter?: React.ReactNode
  help?:    string
  tone?:    "neutral" | "alert"
}) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <h4 className={cx(
        "flex items-center gap-1.5 text-[12px] font-semibold uppercase tracking-[0.04em]",
        tone === "alert"
          ? "text-amber-800 dark:text-amber-300"
          : "text-gray-700 dark:text-gray-300",
      )}>
        <Icon
          className={cx(
            "size-3.5",
            tone === "alert"
              ? "text-amber-600 dark:text-amber-400"
              : "text-gray-400 dark:text-gray-500",
          )}
          aria-hidden
        />
        {label}
        {help && (
          <span
            className="cursor-help text-[10px] font-normal normal-case tracking-normal text-gray-400 dark:text-gray-600"
            title={help}
          >
            (?)
          </span>
        )}
      </h4>
      {counter != null && counter !== "" && (
        <span className="text-[11px] tabular-nums text-gray-500 dark:text-gray-400">{counter}</span>
      )}
    </div>
  )
}
