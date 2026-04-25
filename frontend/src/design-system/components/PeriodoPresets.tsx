"use client"

import * as React from "react"

import { cx, focusRing } from "@/lib/utils"
import { PRESET_KEYS, type PresetKey } from "@/lib/hooks/useBiFilters"

const PRESET_LABELS: Record<PresetKey, string> = {
  ytd: "YTD",
  "3m": "3M",
  "6m": "6M",
  "12m": "12M",
  "24m": "24M",
  "36m": "36M",
  all: "ALL",
}

const PRESET_HINTS: Record<PresetKey, string> = {
  ytd: "Ano ate hoje",
  "3m": "Ultimos 3 meses",
  "6m": "Ultimos 6 meses",
  "12m": "Ultimos 12 meses",
  "24m": "Ultimos 24 meses",
  "36m": "Ultimos 36 meses",
  all: "Todo o historico disponivel",
}

type PeriodoPresetsProps = {
  /** Preset ativo. `null` = modo custom (nenhum preset destacado). */
  value: PresetKey | null
  /** Chamado quando o usuario clica num preset. */
  onChange: (preset: PresetKey) => void
  className?: string
}

/**
 * PeriodoPresets — segmented control com atalhos de periodo.
 *
 * Inspirado em PowerBI/Looker: 7 botoes (YTD, 3M, 6M, 12M, 24M, 36M, ALL)
 * num container unificado, com o ativo destacado (fundo branco + shadow).
 *
 * - value = preset ativo; null quando o usuario esta em modo custom
 *   (mexeu no DateRangePicker). Nesse caso, nenhum botao fica destacado.
 * - onChange apenas sinaliza a escolha; a persistencia em URL/filtros
 *   fica a cargo de quem usa (tipicamente via `useBiFilters.setFilter`).
 * - Mobile: container tem `overflow-x-auto` + `scrollbar-none`; em telas
 *   apertadas o usuario rola horizontalmente.
 * - A11y: role="radiogroup" + aria-checked em cada item.
 */
export function PeriodoPresets({
  value,
  onChange,
  className,
}: PeriodoPresetsProps) {
  return (
    <div
      role="radiogroup"
      aria-label="Periodo pre-definido"
      className={cx(
        "inline-flex max-w-full overflow-x-auto rounded border border-gray-200 bg-gray-50 p-0.5",
        "dark:border-gray-800 dark:bg-gray-900",
        "[&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]",
        className,
      )}
    >
      {PRESET_KEYS.map((key) => {
        const active = value === key
        return (
          <button
            key={key}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={`${PRESET_LABELS[key]} — ${PRESET_HINTS[key]}`}
            title={PRESET_HINTS[key]}
            onClick={() => onChange(key)}
            className={cx(
              "shrink-0 rounded px-2.5 py-1 text-xs font-medium transition",
              // Dual palette (CLAUDE.md §4): blue sinaliza preset ativo com
              // bg sutil + ring blue + texto blue. Inativo fica quase invisivel
              // no container cinza.
              active
                ? "bg-white text-blue-700 shadow-xs ring-1 ring-blue-500 dark:bg-blue-500/10 dark:text-blue-400 dark:ring-blue-400"
                : "text-gray-600 hover:text-gray-900 dark:text-gray-400 hover:dark:text-gray-50",
              focusRing,
            )}
          >
            {PRESET_LABELS[key]}
          </button>
        )
      })}
    </div>
  )
}
