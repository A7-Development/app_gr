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
// Aceita duas APIs:
//
//   1) Canonica (preferida — CLAUDE.md §14.1):
//      <ProvenanceFooter provenances={[p1, p2]} />
//      Recebe Provenance[] (deduplica por adapter+versao). Cor do dot vem
//      do trustLevel (high=emerald, medium=amber, low=red). Mock = passar
//      lista vazia ou nao passar.
//
//   2) Legacy:
//      <ProvenanceFooter sources={[{ label, updated, sla, stale }, ...]} />
//      Continua funcionando para chamadas antigas que ainda nao migraram.
//

"use client"

import * as React from "react"
import { cx } from "@/lib/utils"
import {
  type Provenance,
  TRUST_DOT_COLOR,
  dedupeProvenances,
  formatAdapterId,
  formatSourceLabel,
} from "@/design-system/types/provenance"

export type ProvenanceSource = {
  label:    string
  updated:  string
  sla?:     string
  stale?:   boolean
}

type ProvenanceFooterProps =
  | {
      sources:      ProvenanceSource[]
      provenances?: never
      className?:   string
    }
  | {
      provenances:  Provenance[]
      sources?:     never
      className?:   string
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

export function ProvenanceFooter(props: ProvenanceFooterProps) {
  const className = props.className

  // ── Canonica: provenances ────────────────────────────────────────────
  if ("provenances" in props && props.provenances) {
    const items = dedupeProvenances(props.provenances)
    if (items.length === 0) return null
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
        {items.map((p) => {
          const dotColor = TRUST_DOT_COLOR[p.trustLevel]
          const label = formatSourceLabel(p)
          const adapterId = formatAdapterId(p)
          const relative = formatRelative(p.ingestedAt)
          return (
            <div key={adapterId} className="flex items-center gap-1.5">
              <span
                aria-hidden="true"
                className={cx("size-1.5 shrink-0 rounded-full", dotColor)}
              />
              <span className="text-[11px] text-gray-600 dark:text-gray-400">
                <span className="font-medium text-gray-900 dark:text-gray-50">
                  {label}
                </span>
                {" · "}
                {adapterId}
                {" · "}
                {relative}
              </span>
            </div>
          )
        })}
      </div>
    )
  }

  // ── Legacy: sources ──────────────────────────────────────────────────
  const sources = props.sources ?? []
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
