"use client"

/**
 * BandaKpi — copia LITERAL (classe por classe) do `CotaSubStatusBand` da
 * cota-sub, o card de KPI que o Ricardo definiu como padrao (2026-06-12).
 *
 * Container, Col, tamanhos e cores identicos ao original
 * (`cota-sub/_components/CotaSubStatusBand.tsx`):
 *   section  flex flex-wrap items-center gap-x-8 gap-y-3 rounded border
 *            border-gray-200 bg-white px-4 py-3
 *   label    text-[10px] font-semibold uppercase tracking-[0.06em] gray-500
 *   headline text-[23px] font-bold tracking-[-0.025em] tabular gray-900
 *   demais   text-[17px] font-semibold tabular (cor semantica opcional
 *            pelo sinal via `tone`: emerald-700 / rose-700 / gray-500)
 *   divisor  border-l border-gray-200 pl-8
 *
 * Local da pagina (espelha a pratica da cota-sub, que tambem mantem o dela
 * local). Promocao a design-system fica para depois da validacao visual.
 */

import * as React from "react"

import { cx } from "@/lib/utils"

function toneText(v: number): string {
  return v > 0
    ? "text-emerald-700 dark:text-emerald-400"
    : v < 0
      ? "text-rose-700 dark:text-rose-400"
      : "text-gray-500 dark:text-gray-400"
}

export function BandaKpiCol({
  label,
  headline = false,
  divider = false,
  tone,
  children,
}: {
  label: string
  headline?: boolean
  divider?: boolean
  /** Numero cru para cor semantica pelo sinal (regra CotaSubStatusBand). */
  tone?: number
  children: React.ReactNode
}) {
  return (
    <div className={cx(divider && "border-l border-gray-200 pl-8 dark:border-gray-800")}>
      <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-500 dark:text-gray-400">
        {label}
      </div>
      <div className="mt-0.5">
        <span
          className={cx(
            "leading-none tabular-nums",
            headline
              ? "text-[23px] font-bold tracking-[-0.025em] text-gray-900 dark:text-gray-50"
              : cx(
                  "text-[17px] font-semibold",
                  tone != null ? toneText(tone) : "text-gray-900 dark:text-gray-50",
                ),
          )}
        >
          {children}
        </span>
      </div>
    </div>
  )
}

export function BandaKpi({
  children,
  right,
  loading = false,
  className,
}: {
  children: React.ReactNode
  /** Slot a direita (status pills), identico ao do CotaSubStatusBand. */
  right?: React.ReactNode
  loading?: boolean
  className?: string
}) {
  if (loading) {
    return (
      <section
        className={cx(
          "flex flex-wrap items-center gap-x-8 gap-y-2 rounded border border-gray-200 bg-white px-4 py-3 dark:border-gray-800 dark:bg-gray-950",
          className,
        )}
      >
        {[0, 1, 2].map((i) => (
          <div key={i}>
            <div className="h-3 w-20 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
            <div className="mt-1.5 h-6 w-24 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
          </div>
        ))}
      </section>
    )
  }
  return (
    <section
      className={cx(
        "flex flex-wrap items-center gap-x-8 gap-y-3 rounded border border-gray-200 bg-white px-4 py-3 dark:border-gray-800 dark:bg-gray-950",
        className,
      )}
    >
      {children}
      {right && (
        <div className="ml-auto flex flex-col items-end gap-1.5">{right}</div>
      )}
    </section>
  )
}
