// src/design-system/components/StationHeader/index.tsx
//
// Cabeçalho de estação + sub-passos (handoff Conceito D).
// Anatomia fixa de TODA estação — o analista aprende uma vez:
//   1. Título "Estação N · Nome" (19px/600) + chip de estado
//   2. Linha "Rodou sozinho: … Falta você: …" (12.5px muted)
//   3. Ações à direita (ghost "Trilha da estação" + ghost ···)
//   4. Sub-passos como abas (✓ verde / ativo azul numerado / futuro cinza)
//
// Tabs sempre carregam border-bottom 2px transparent (evita jump de 2px
// entre estados — normalização decidida na implementação).

"use client"

import * as React from "react"
import {
  RiArrowRightSLine,
  RiCheckboxCircleFill,
  RiCheckDoubleLine,
  RiFileTextLine,
  RiHistoryLine,
  RiMoreLine,
  RiQuillPenLine,
  RiSparkling2Line,
  type RemixiconComponentType,
} from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { cx } from "@/lib/utils"

// Fases canônicas da estação (handoff: Documento → Conferência → Leitura →
// Homologação). `kind` escolhe o ícone; sem `kind`, cai no círculo numerado
// (back-compat com chamadores que ainda passam sub-passos genéricos).
export type StationPhaseKind = "documento" | "conferencia" | "leitura" | "homologacao"

export type StationSubstep = {
  label: string
  state: "done" | "active" | "future"
  kind?: StationPhaseKind
  /** Detalhe inline (ex.: "soma confere"). */
  detail?: string
}

const PHASE_ICON: Record<StationPhaseKind, RemixiconComponentType> = {
  documento: RiFileTextLine,
  conferencia: RiCheckDoubleLine,
  leitura: RiSparkling2Line,
  homologacao: RiQuillPenLine,
}

const C_ACTIVE = "#6366F1" // indigo — fase presente
const C_DONE = "#059669" // verde — fase percorrida

function PhaseGlyph({ s, number }: { s: StationSubstep; number: number }) {
  if (s.state === "done") {
    return (
      <RiCheckboxCircleFill
        className="size-4 shrink-0"
        style={{ color: C_DONE }}
        aria-hidden
      />
    )
  }
  const Icon = s.kind ? PHASE_ICON[s.kind] : null
  if (Icon) {
    return (
      <Icon
        className="size-4 shrink-0"
        style={{ color: s.state === "active" ? C_ACTIVE : undefined }}
        aria-hidden
      />
    )
  }
  // Fallback: círculo numerado (sub-passos sem kind).
  return (
    <span
      className={cx(
        "flex size-4 shrink-0 items-center justify-center rounded-full text-[10px] leading-none",
        s.state === "active"
          ? "font-bold text-white"
          : "border-[1.5px] border-gray-300 font-semibold text-gray-500 dark:border-gray-700 dark:text-gray-400",
      )}
      style={s.state === "active" ? { background: C_ACTIVE } : undefined}
    >
      {number}
    </span>
  )
}

export type StationHeaderProps = {
  /** Título completo (ex.: "Estação 2 · Faturamento"). */
  title: string
  /** Chip de estado (use <StationStateChip>). */
  chip?: React.ReactNode
  /** Linha "Rodou sozinho: … Falta você: …". */
  subtitle?: React.ReactNode
  /** Sub-passos (abas). Omitir quando a estação não tem sub-passos (D2). */
  substeps?: StationSubstep[]
  onSubstepClick?: (index: number) => void
  onOpenTrail?: () => void
  trailDisabled?: boolean
  /** Slot do menu "···" (DropdownMenu). Omitido = sem botão. */
  moreMenu?: React.ReactNode
  className?: string
}

export function StationHeader({
  title,
  chip,
  subtitle,
  substeps,
  onSubstepClick,
  onOpenTrail,
  trailDisabled,
  moreMenu,
  className,
}: StationHeaderProps) {
  return (
    <header
      className={cx(
        "shrink-0 border-b border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
        className,
      )}
    >
      <div className={cx("px-8 pt-[18px]", !substeps && "pb-4")}>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-[19px] font-semibold tracking-[-0.01em] text-gray-900 dark:text-gray-50">
            {title}
          </h1>
          {chip}
          <div className="ml-auto flex items-center gap-1.5">
            {onOpenTrail && (
              <Button
                variant="ghost"
                className="h-8"
                onClick={onOpenTrail}
                disabled={trailDisabled}
              >
                <RiHistoryLine className="mr-1.5 size-4" aria-hidden />
                Trilha da estação
              </Button>
            )}
            {moreMenu ?? (
              <Button variant="ghost" className="size-8 p-0" aria-label="Mais ações" disabled>
                <RiMoreLine className="size-4" aria-hidden />
              </Button>
            )}
          </div>
        </div>
        {subtitle && (
          <p className="mt-1 max-w-[860px] text-[12.5px] text-gray-500 dark:text-gray-400">
            {subtitle}
          </p>
        )}
        {substeps && (
          <div className="mt-2 flex flex-wrap items-center gap-0.5">
            {substeps.map((s, i) => (
              <React.Fragment key={`${s.label}-${i}`}>
                {i > 0 && (
                  <RiArrowRightSLine
                    className="size-4 shrink-0 text-gray-300 dark:text-gray-700"
                    aria-hidden
                  />
                )}
                <button
                  type="button"
                  onClick={onSubstepClick ? () => onSubstepClick(i) : undefined}
                  className={cx(
                    "flex items-center gap-1.5 rounded-md px-2.5 py-[7px] text-[12.5px] transition-colors duration-100",
                    s.state === "active" && "font-semibold",
                    s.state === "done" && "font-medium",
                    s.state === "future" && "font-medium text-gray-400 dark:text-gray-500",
                    onSubstepClick && s.state !== "future"
                      ? "hover:bg-gray-50 dark:hover:bg-gray-900"
                      : "cursor-default",
                  )}
                  style={
                    s.state === "done"
                      ? { color: C_DONE }
                      : s.state === "active"
                        ? { color: C_ACTIVE }
                        : undefined
                  }
                >
                  <PhaseGlyph s={s} number={i + 1} />
                  <span>
                    {s.label}
                    {s.detail && (
                      <span className="font-normal text-gray-400 dark:text-gray-500">
                        {" · "}
                        {s.detail}
                      </span>
                    )}
                  </span>
                </button>
              </React.Fragment>
            ))}
          </div>
        )}
      </div>
    </header>
  )
}
