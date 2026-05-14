"use client"

/**
 * StatusHeadlineCompact — banda Z1 compacta da aba "Eventos do dia".
 *
 * Inspirado no handoff `Cota Sub - Eventos do Dia.html` (variant-b). Layout:
 *
 *   [PL COTA SUB · D0  R$ 18.700.580]  |  [VARIACAO DIA  +132k  +0,71%]   .....   [chips]
 *
 * Substitui visualmente o KpiHeadline aqui — single line, denso, sem hero
 * isolado. Sparkline 15d do handoff foi omitido: ainda nao temos endpoint
 * de serie historica de PL Sub. Quando o endpoint subir, adicionamos no
 * slot direito antes do divisor.
 *
 * Tone do numero primary: vira `neutral` quando ha pendente COSIF OU
 * `data_quality.comparable=false`. Coerente com a logica do KpiHeadline
 * antigo — CLAUDE.md §14 explicabilidade > inferencia.
 */

import * as React from "react"

import { cx } from "@/lib/utils"

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency", currency: "BRL",
  minimumFractionDigits: 2, maximumFractionDigits: 2,
})

const fmtPct = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(2).replace(".", ",")}%`

export type StatusHeadlineChip = {
  label: string
  tone:  "ok" | "warn" | "error" | "neutral"
}

export type StatusHeadlineCompactProps = {
  /** Data D0 formatada (ex.: "13/05/2026"). */
  dataD0?: string
  /** PL Cota Sub em D0. Quando indefinido, mostra "—". */
  plSubD0?: number
  /** Δ R$ vs D-1. */
  deltaReal?: number
  /** Δ % vs D-1. */
  deltaPct?: number
  /** Numero primary vira cinza (snapshot parcial OU pendentes COSIF). */
  forceNeutral?: boolean
  /** Chips de status no canto direito. */
  chips?: StatusHeadlineChip[]
  /** Loading visual quando true (skeleton bars). */
  loading?: boolean
}

export function StatusHeadlineCompact({
  dataD0,
  plSubD0,
  deltaReal,
  deltaPct,
  forceNeutral = false,
  chips = [],
  loading = false,
}: StatusHeadlineCompactProps) {
  const deltaToneCls =
    forceNeutral
      ? "text-gray-600 dark:text-gray-300"
      : deltaReal != null && deltaReal >= 0
        ? "text-emerald-700 dark:text-emerald-400"
        : "text-rose-700 dark:text-rose-400"

  return (
    <section
      className={cx(
        "flex flex-wrap items-center gap-x-7 gap-y-2 rounded border px-4 py-3",
        "border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
      )}
    >
      {/* Coluna 1: PL Sub D0 */}
      <div className="flex items-baseline gap-3">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-500 dark:text-gray-400">
            PL Cota Sub{dataD0 ? ` · ${formatBrazilianDate(dataD0)}` : ""}
          </div>
          {loading ? (
            <div className="mt-1 h-[26px] w-44 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
          ) : (
            <div
              className={cx(
                "mt-0.5 text-[26px] font-semibold leading-[1.05] tracking-[-0.025em] tabular-nums",
                forceNeutral
                  ? "text-gray-600 dark:text-gray-300"
                  : "text-gray-900 dark:text-gray-50",
              )}
            >
              {plSubD0 != null ? fmtBRL.format(plSubD0) : "—"}
            </div>
          )}
        </div>

        {/* Coluna 2: Variacao dia */}
        <div className="ml-1 border-l border-gray-200 pl-4 dark:border-gray-800">
          <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-500 dark:text-gray-400">
            Variação dia
          </div>
          {loading ? (
            <div className="mt-1 h-[20px] w-28 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
          ) : (
            <div className="mt-0.5 flex items-baseline gap-2">
              <span
                className={cx(
                  "text-[20px] font-semibold leading-tight tracking-[-0.02em] tabular-nums",
                  deltaToneCls,
                )}
              >
                {deltaReal != null
                  ? `${deltaReal >= 0 ? "+" : ""}${fmtBRL.format(deltaReal)}`
                  : "—"}
              </span>
              {deltaPct != null && (
                <span
                  className={cx(
                    "inline-flex items-center rounded px-1.5 py-0.5 text-[12px] font-semibold tabular-nums",
                    forceNeutral
                      ? "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300"
                      : deltaPct >= 0
                        ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400"
                        : "bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-400",
                  )}
                >
                  {fmtPct(deltaPct)}
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Chips no canto direito */}
      {chips.length > 0 && (
        <div className="ml-auto flex flex-wrap items-center gap-1.5">
          {chips.map((c, i) => (
            <ChipPill key={i} chip={c} />
          ))}
        </div>
      )}
    </section>
  )
}

function ChipPill({ chip }: { chip: StatusHeadlineChip }) {
  const palette = {
    ok:      "bg-emerald-50 text-emerald-700 border-emerald-100 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-900/40",
    warn:    "bg-amber-50 text-amber-700 border-amber-100 dark:bg-amber-500/10 dark:text-amber-300 dark:border-amber-900/40",
    error:   "bg-red-50 text-red-700 border-red-100 dark:bg-red-500/10 dark:text-red-300 dark:border-red-900/40",
    neutral: "bg-gray-50 text-gray-700 border-gray-200 dark:bg-gray-900 dark:text-gray-300 dark:border-gray-800",
  }[chip.tone]
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded border px-2 py-0.5 text-[11px] font-medium leading-tight",
        palette,
      )}
    >
      <span
        className={cx(
          "inline-block size-1.5 rounded-full",
          {
            ok:      "bg-emerald-500",
            warn:    "bg-amber-500",
            error:   "bg-red-500",
            neutral: "bg-gray-400",
          }[chip.tone],
        )}
        aria-hidden="true"
      />
      {chip.label}
    </span>
  )
}

function formatBrazilianDate(iso: string): string {
  // ISO "YYYY-MM-DD" -> "DD/MM/YYYY". Tolera valor ja formatado.
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  if (!m) return iso
  return `${m[3]}/${m[2]}/${m[1]}`
}
