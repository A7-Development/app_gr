// src/design-system/components/ProvenanceFooter.tsx
//
// ProvenanceFooter -- Z5 do dashboard padrao (handoff bi-padrao::ProvenanceBar).
//
// Faixa fina no rodape mostrando proveniencia das fontes que alimentam a pagina:
// dot verde (fresh) ou amber (stale) + label (bold) + " · " + updated + SLA.
//
// Render no rodape do `<div className="flex h-[calc(100vh-Xrem)] flex-col">` da
// pagina, FORA do scroll do conteudo, para sempre estar visivel.
//

"use client"

import * as React from "react"
import { cx } from "@/lib/utils"

export type ProvenanceSource = {
  label:    string
  updated:  string
  sla?:     string
  stale?:   boolean
}

type ProvenanceFooterProps = {
  sources:    ProvenanceSource[]
  className?: string
}

export function ProvenanceFooter({ sources, className }: ProvenanceFooterProps) {
  return (
    <div
      role="contentinfo"
      aria-label="Proveniencia dos dados"
      className={cx(
        "flex shrink-0 flex-wrap items-center gap-4 border-t px-6 py-1.5",
        "border-gray-200 bg-gray-50",
        "dark:border-gray-800 dark:bg-gray-900/40",
        className,
      )}
    >
      {sources.map((s) => (
        <div key={s.label} className="flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className={cx(
              "size-1.5 shrink-0 rounded-full",
              s.stale ? "bg-amber-500" : "bg-emerald-500",
            )}
          />
          <span className="text-[11px] text-gray-600 dark:text-gray-400">
            <span className="font-medium text-gray-900 dark:text-gray-50">{s.label}</span>
            {" · "}
            {s.updated}
          </span>
          {s.sla && (
            <span className="text-[10px] text-gray-400 dark:text-gray-600">
              SLA {s.sla}
            </span>
          )}
        </div>
      ))}
    </div>
  )
}
