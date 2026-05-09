// src/design-system/components/VizParam.tsx
//
// VizParam -- segmented control compacto para parametros de visualizacao
// dentro de um chart card (ex.: 12M | 6M | 3M | 1M, ou Mensal | Diario).
// Alinhado com handoff bi-padrao::VizParam (Components.jsx:413-421).
//
// Estilo: padding 2px 8px, radius 3px, font 11px. Active: bg blue-500 +
// text white. Inactive: text gray-muted, transparent bg, gray-border.
//

"use client"

import * as React from "react"
import { cx, focusRing } from "@/lib/utils"

type VizParamProps<T extends string> = {
  options:  readonly T[]
  value:    T
  onChange: (next: T) => void
  className?: string
  /** aria-label do grupo (default: "Parametro de visualizacao"). */
  ariaLabel?: string
}

export function VizParam<T extends string>({
  options,
  value,
  onChange,
  className,
  ariaLabel = "Parametro de visualizacao",
}: VizParamProps<T>) {
  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      className={cx("inline-flex gap-0.5", className)}
    >
      {options.map((opt) => {
        const active = opt === value
        return (
          <button
            key={opt}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(opt)}
            className={cx(
              "rounded-[3px] border px-2 py-[2px] text-[11px] transition-colors duration-100",
              active
                ? "border-blue-500 bg-blue-500 text-white"
                : "border-gray-200 bg-transparent text-gray-500 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800",
              focusRing,
            )}
          >
            {opt}
          </button>
        )
      })}
    </div>
  )
}
