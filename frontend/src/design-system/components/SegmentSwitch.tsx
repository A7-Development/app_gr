// src/design-system/components/SegmentSwitch.tsx
//
// SegmentSwitch — filtro segment-style (single-select) inline.
//
// Visual: grupo de pills "Todos / Ativos / Suspensos" no topo de uma listagem.
// Sem mudanca de URL, sem trocar de pagina — apenas filtra a view atual.
//
// NAO confundir com:
// - `<TabNavigation>` (Tremor) — usado para L3 da hierarquia (CLAUDE.md §11.6),
//   geralmente troca conteudo da pagina e e deep-linkavel via URL.
// - `<FilterChip>` (FilterBar) — chip clickavel que abre Popover com opcoes
//   multi-select. SegmentSwitch e single-select toggle inline.
//
// Use para: status simples (Todos/Ativos/Inativos), tipos (Pessoa Fisica/Juridica),
// estados de fluxo (Pendente/Aprovado/Rejeitado). Maximo ~5 opcoes — acima disso,
// prefira <FilterChip> com Popover.

"use client"

import * as React from "react"

import { cx, focusRing } from "@/lib/utils"

export type SegmentDef<T extends string> = {
  value: T
  label: string
  /** Contagem opcional ao lado do label (ex.: "Ativos 12"). */
  count?: number
}

export type SegmentSwitchProps<T extends string> = {
  options: SegmentDef<T>[]
  value: T
  onChange: (next: T) => void
  /** Label acessivel para leitores de tela. */
  ariaLabel?: string
  className?: string
}

export function SegmentSwitch<T extends string>({
  options,
  value,
  onChange,
  ariaLabel = "Filtrar por segmento",
  className,
}: SegmentSwitchProps<T>) {
  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className={cx(
        "inline-flex items-center gap-0.5 rounded border border-gray-200 bg-gray-50 p-0.5",
        "dark:border-gray-800 dark:bg-gray-900",
        className,
      )}
    >
      {options.map((opt) => {
        const active = opt.value === value
        return (
          <button
            key={opt.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(opt.value)}
            className={cx(
              "inline-flex items-center gap-1 rounded px-2 py-1 text-xs transition-colors",
              active
                ? "bg-white text-gray-900 shadow-sm dark:bg-gray-950 dark:text-gray-50"
                : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200",
              focusRing,
            )}
          >
            <span>{opt.label}</span>
            {opt.count !== undefined && (
              <span
                className={cx(
                  "rounded px-1 text-[10px] font-medium tabular-nums",
                  active
                    ? "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300"
                    : "bg-gray-200/60 text-gray-500 dark:bg-gray-800/60 dark:text-gray-400",
                )}
              >
                {opt.count}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
