"use client"

import * as React from "react"

import { cx } from "@/lib/utils"
import { Tooltip } from "@/components/tremor/Tooltip"
import {
  type Provenance,
  TRUST_DOT_COLOR,
  formatAdapterId,
  formatProvenanceTooltip,
  formatSourceLabel,
} from "@/design-system/types/provenance"

//
// OriginDot -- proveniencia em KpiCard / VizCard / EChartsCard / DataTableShell.
//
// Aceita duas APIs:
//
//   1) Canonica (preferida):
//      <OriginDot provenance={p} variant="dot" />
//      Recebe um Provenance (CLAUDE.md §14.1). Cor do dot pelo trustLevel
//      (high=emerald, medium=amber, low=red). Tooltip mostra fonte + adapter@v
//      + sincronizado + confianca. Mock = `provenance={undefined|null}` ->
//      nada renderiza.
//
//   2) Legacy:
//      <OriginDot source="Bitfin" updatedAtISO="..." variant="inline" />
//      Continua funcionando para chamadas antigas que ainda nao migraram.
//      Sem trustLevel — dot sempre verde, como era antes.
//
// 3 variants:
//   - `inline` (default): label visivel "🟢 Fonte · ha N min" no flow do
//     card. Alinhado com handoff bi-padrao 2026-04-26 (KpiCard.source).
//   - `pinned`: dot 12x12 absolute bottom-right (positioning interno). Usado
//     em VizCard / EChartsCard / DataTableShell — caller marca o
//     container parent como `relative`. Variante do handoff COMPONENTS.md §11.
//   - `dot`: dot 6x6 SEM positioning interno (caller wrappa). Usado em
//     KpiCard para colar a proveniencia no canto superior direito sem
//     forcar 18-20px de altura extra (handoff pos-iteracao 2026-04-30).
//

type OriginDotVariant = "inline" | "pinned" | "dot"

type CanonicalProps = {
  provenance: Provenance | null | undefined
  source?: never
  updatedAtISO?: never
  variant?: OriginDotVariant
  className?: string
}

type LegacyProps = {
  provenance?: never
  source: string
  updatedAtISO?: string | null
  variant?: OriginDotVariant
  className?: string
}

type OriginDotProps = CanonicalProps | LegacyProps

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

const LEGACY_DOT_COLOR =
  "bg-emerald-500 hover:bg-emerald-600 dark:bg-emerald-500 dark:hover:bg-emerald-400"

export function OriginDot(props: OriginDotProps) {
  // ── Canonica: provenance ─────────────────────────────────────────────
  if ("provenance" in props && props.provenance != null) {
    const p = props.provenance
    const variant = props.variant ?? "inline"
    const tooltipText = formatProvenanceTooltip(p)
    const dotColor = TRUST_DOT_COLOR[p.trustLevel]
    const sourceLabel = formatSourceLabel(p)
    const adapterId = formatAdapterId(p)
    const relative = formatRelative(p.ingestedAt)

    if (variant === "inline") {
      return (
        <span
          aria-label={tooltipText}
          title={tooltipText}
          className={cx(
            "mt-0.5 inline-flex items-center gap-1.5 text-[10px] leading-none",
            "text-gray-500 dark:text-gray-400",
            props.className,
          )}
        >
          <span
            aria-hidden="true"
            className={cx("inline-block size-1.5 shrink-0 rounded-full", dotColor)}
          />
          <span>
            <span className="font-medium text-gray-900 dark:text-gray-50">
              {sourceLabel}
            </span>
            {" · "}
            {adapterId}
            {" · "}
            {relative}
          </span>
        </span>
      )
    }

    if (variant === "dot") {
      return (
        <Tooltip content={tooltipText} side="top">
          <span
            aria-label={tooltipText}
            className={cx(
              "inline-block size-1.5 shrink-0 rounded-full",
              dotColor,
              "transition-colors duration-100",
              "cursor-help",
              props.className,
            )}
          />
        </Tooltip>
      )
    }

    // variant === "pinned"
    return (
      <Tooltip content={tooltipText} side="top">
        <span
          aria-label={tooltipText}
          className={cx(
            "absolute bottom-1.5 right-2 inline-flex size-2 items-center justify-center rounded-full",
            dotColor,
            "ring-2 ring-white dark:ring-[#090E1A]",
            "transition-colors duration-100",
            "cursor-help",
            props.className,
          )}
        />
      </Tooltip>
    )
  }

  // ── Mock (provenance explicitamente null/undefined sem source) ───────
  if (!("source" in props) || props.source == null) {
    return null
  }

  // ── Legacy: source + updatedAtISO ────────────────────────────────────
  const { source, updatedAtISO, variant = "inline", className } = props
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
          className={cx("inline-block size-1.5 shrink-0 rounded-full", LEGACY_DOT_COLOR)}
        />
        <span>
          <span className="font-medium text-gray-900 dark:text-gray-50">{source}</span>
          {relative ? ` · ${relative}` : ""}
        </span>
      </span>
    )
  }

  if (variant === "dot") {
    return (
      <Tooltip content={tooltipText} side="top">
        <span
          aria-label={tooltipText}
          className={cx(
            "inline-block size-1.5 shrink-0 rounded-full",
            LEGACY_DOT_COLOR,
            "transition-colors duration-100",
            "cursor-help",
            className,
          )}
        />
      </Tooltip>
    )
  }

  // variant === "pinned" (legacy)
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
