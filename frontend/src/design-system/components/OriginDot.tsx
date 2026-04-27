"use client"

import * as React from "react"

import { cx } from "@/lib/utils"
import { Tooltip } from "@/components/tremor/Tooltip"

//
// OriginDot -- proveniencia em KpiCard / VizCard.
//
// Dois modos:
//   - `inline` (default): label visivel "🟢 Fonte · ha N min" no flow do
//     card. Alinhado com handoff bi-padrao 2026-04-26 (KpiCard.source).
//   - `pinned`: dot 12x12 absolute bottom-right, label so no hover. Usado
//     em VizCard onde o footer ja carrega a fonte e o ponto e marcador
//     redundante. Variante legada do handoff COMPONENTS.md §11.
//

type OriginDotProps = {
  source: string
  updatedAtISO?: string | null
  /** "inline" (default) shows visible label; "pinned" is dot-only absolute. */
  variant?: "inline" | "pinned"
  className?: string
}

function formatRelative(iso: string): string {
  const ts = new Date(iso).getTime()
  if (Number.isNaN(ts)) return iso
  const diffMs = Date.now() - ts
  const diffMin = Math.round(diffMs / 60_000)
  if (diffMin < 1) return "agora"
  if (diffMin < 60) return `ha ${diffMin} min`
  const diffH = Math.round(diffMin / 60)
  if (diffH < 24) return `ha ${diffH} h`
  const diffD = Math.round(diffH / 24)
  return `ha ${diffD} d`
}

export function OriginDot({
  source,
  updatedAtISO,
  variant = "inline",
  className,
}: OriginDotProps) {
  const relative = updatedAtISO ? formatRelative(updatedAtISO) : null
  const tooltipText = relative
    ? `Fonte: ${source} -- atualizado ${relative}`
    : `Fonte: ${source}`

  if (variant === "inline") {
    return (
      <span
        aria-label={tooltipText}
        className={cx(
          "mt-0.5 inline-flex items-center gap-1.5 text-[10px] leading-none",
          "text-gray-500 dark:text-gray-400",
          className,
        )}
      >
        <span
          aria-hidden="true"
          className="inline-block size-1.5 shrink-0 rounded-full bg-emerald-500"
        />
        <span>
          <span className="font-medium text-gray-900 dark:text-gray-50">{source}</span>
          {relative ? ` · ${relative}` : ""}
        </span>
      </span>
    )
  }

  return (
    <Tooltip content={tooltipText} side="top">
      <span
        aria-label={tooltipText}
        className={cx(
          "absolute bottom-1.5 right-2 inline-flex size-3 items-center justify-center rounded-full",
          "border border-gray-300 bg-gray-100 transition-colors duration-100",
          "hover:bg-gray-900 hover:border-gray-900",
          "dark:border-gray-700 dark:bg-gray-800 dark:hover:bg-gray-50 dark:hover:border-gray-50",
          className,
        )}
      />
    </Tooltip>
  )
}
