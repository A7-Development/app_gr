"use client"

import * as React from "react"

import { cx } from "@/lib/utils"
import { Tooltip } from "@/components/tremor/Tooltip"

//
// OriginDot -- ponto de proveniencia (handoff COMPONENTS.md §11).
//
// 12x12 no canto inferior direito de KpiCard / VizCard. Indica fonte do
// dado + timestamp. Hover revela tooltip completo. Nao usa cor semantica
// de sucesso/erro: e um ponto neutro (gray-400) que realca em hover.
//

type OriginDotProps = {
  source: string
  updatedAtISO?: string | null
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
  className,
}: OriginDotProps) {
  const tooltipText = updatedAtISO
    ? `Fonte: ${source} -- atualizado ${formatRelative(updatedAtISO)}`
    : `Fonte: ${source}`

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
