// src/design-system/components/Provenance/index.tsx
//
// Primitivos da linguagem de proveniência (handoff Conceito D, 2026-06-10).
// Assinatura canônica = ícone + cor + forma de linha — nunca cor sozinha.
//
//   <ProvenanceChip>  — selo E1 (pill h18, ícone 12 + label 11px/500).
//                       Linguagem de detalhe/fallback + células de situação.
//   <ProvenanceTile>  — tile 32×32 com ícone 16 (headers de card, avatares).
//   <ProvenanceSup>   — sobrescrito de lastro E5 (9px/600, código F1/D1/IA1/A1).
//   <ProvenanceValue> — valor com sublinha E3 (contínua/tracejada/pontilhada/dupla).
//   PROVENANCE_ICON   — mapa origem → componente Remix.

"use client"

import * as React from "react"
import {
  RiBankLine,
  RiFileTextLine,
  RiQuillPenLine,
  RiSparkling2Line,
  type RemixiconComponentType,
} from "@remixicon/react"

import {
  provenanceTokens,
  provenanceUnderline,
  type ProvenanceOrigin,
} from "@/design-system/tokens/provenance"
import { cx } from "@/lib/utils"

export const PROVENANCE_ICON: Record<ProvenanceOrigin, RemixiconComponentType> = {
  fonte: RiBankLine,
  agente: RiSparkling2Line,
  documento: RiFileTextLine,
  analista: RiQuillPenLine,
}

// ─── ProvenanceChip (E1 · selo) ─────────────────────────────────────────────

export type ProvenanceChipProps = {
  origin: ProvenanceOrigin
  children: React.ReactNode
  className?: string
  title?: string
}

export function ProvenanceChip({ origin, children, className, title }: ProvenanceChipProps) {
  const t = provenanceTokens[origin]
  const Icon = PROVENANCE_ICON[origin]
  return (
    <span
      title={title}
      className={cx(
        "inline-flex h-[18px] items-center gap-1 rounded-full px-[7px] text-[11px] font-medium leading-none",
        className,
      )}
      style={{ background: t.chipBg, color: t.chipText }}
    >
      <Icon className="size-3 shrink-0" aria-hidden />
      <span className="truncate">{children}</span>
    </span>
  )
}

// ─── ProvenanceTile (tile 32×32) ────────────────────────────────────────────

export type ProvenanceTileProps = {
  origin: ProvenanceOrigin
  size?: number
  className?: string
}

export function ProvenanceTile({ origin, size = 32, className }: ProvenanceTileProps) {
  const t = provenanceTokens[origin]
  const Icon = PROVENANCE_ICON[origin]
  return (
    <span
      className={cx("inline-flex shrink-0 items-center justify-center rounded", className)}
      style={{ width: size, height: size, background: t.tileBg }}
      aria-label={t.label}
    >
      <Icon className="size-4" style={{ color: t.color }} aria-hidden />
    </span>
  )
}

// ─── ProvenanceSup (E5 · nota de lastro) ────────────────────────────────────

export type ProvenanceSupProps = {
  origin: ProvenanceOrigin
  /** Índice da nota (1 → "F1" / "IA1" / "D1" / "A1"). */
  index: number
  /** Clicar leva à estação/trecho que produziu a nota. */
  onClick?: () => void
  className?: string
}

export function ProvenanceSup({ origin, index, onClick, className }: ProvenanceSupProps) {
  const t = provenanceTokens[origin]
  const code = `${t.supPrefix}${index}`
  const body = (
    <sup
      className={cx("ml-px text-[9px] font-semibold leading-none", className)}
      style={{ color: t.color }}
    >
      {code}
    </sup>
  )
  if (!onClick) return body
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-sm hover:opacity-70"
      aria-label={`Lastro ${code}`}
    >
      {body}
    </button>
  )
}

// ─── ProvenanceValue (E3 · sublinha tipográfica) ────────────────────────────

export type ProvenanceValueProps = {
  origin: ProvenanceOrigin
  /** Conclusão de IA não homologada = pontilhada; assenta em contínua ao aceitar. */
  homologado?: boolean
  children: React.ReactNode
  className?: string
  title?: string
}

export function ProvenanceValue({
  origin,
  homologado = true,
  children,
  className,
  title,
}: ProvenanceValueProps) {
  return (
    <span
      title={title}
      className={cx("transition-[border-color] duration-150", className)}
      style={provenanceUnderline(origin, homologado)}
    >
      {children}
    </span>
  )
}

export type { ProvenanceOrigin }
