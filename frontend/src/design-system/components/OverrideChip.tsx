"use client"

import * as React from "react"
import { RiCloseLine } from "@remixicon/react"

import { cx } from "@/lib/utils"

//
// OverrideChip -- comunica "este card tem override local" + reset em 1-click.
//
// Handoff COMPONENTS.md §14. Aparece no card-head de um VizCard sempre que
// o usuario muda Agrupar / Recorte / Tipo via CardMenu. O texto e livre
// (ex.: "Top 10"). Click no X reseta para o default do card.
//

type OverrideChipProps = {
  label: string
  onReset: () => void
  className?: string
}

export function OverrideChip({ label, onReset, className }: OverrideChipProps) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-sm border border-blue-200 bg-blue-50 px-1.5 py-0.5",
        "text-[11px] font-medium text-blue-700",
        "dark:border-blue-900/50 dark:bg-blue-950/40 dark:text-blue-400",
        className,
      )}
    >
      <span>{label}</span>
      <span
        aria-hidden="true"
        className="h-2.5 w-px bg-blue-300 dark:bg-blue-700"
      />
      <button
        type="button"
        aria-label={`Resetar override "${label}"`}
        onClick={onReset}
        className="inline-flex size-3.5 items-center justify-center rounded-xs text-blue-600 hover:bg-blue-100 hover:text-blue-800 dark:text-blue-400 dark:hover:bg-blue-900/40"
      >
        <RiCloseLine className="size-3" />
      </button>
    </span>
  )
}
