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
import { RiCheckboxCircleFill, RiHistoryLine, RiMoreLine } from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { cx } from "@/lib/utils"

export type StationSubstep = {
  label: string
  state: "done" | "active" | "future"
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
          <div className="mt-2 flex flex-wrap">
            {substeps.map((s, i) => {
              const number = i + 1
              return (
                <button
                  key={`${s.label}-${i}`}
                  type="button"
                  onClick={onSubstepClick ? () => onSubstepClick(i) : undefined}
                  className={cx(
                    "flex items-center gap-1.5 border-b-2 px-4 py-[9px] text-[12.5px] transition-colors duration-100",
                    s.state === "active"
                      ? "border-blue-500 font-semibold text-blue-600"
                      : "border-transparent",
                    s.state === "done" && "font-medium",
                    s.state === "future" && "font-medium text-gray-500 dark:text-gray-400",
                    !onSubstepClick && "cursor-default",
                  )}
                  style={s.state === "done" ? { color: "#059669" } : undefined}
                >
                  {s.state === "done" ? (
                    <RiCheckboxCircleFill className="size-3.5 shrink-0" aria-hidden />
                  ) : (
                    <span
                      className={cx(
                        "flex size-4 shrink-0 items-center justify-center rounded-full text-[10px] leading-none",
                        s.state === "active"
                          ? "bg-blue-500 font-bold text-white"
                          : "border-[1.5px] border-gray-300 font-semibold text-gray-500 dark:border-gray-700 dark:text-gray-400",
                      )}
                    >
                      {number}
                    </span>
                  )}
                  {s.label}
                </button>
              )
            })}
          </div>
        )}
      </div>
    </header>
  )
}
