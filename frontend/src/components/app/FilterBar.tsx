"use client"

import * as React from "react"
import { RiEqualizerLine } from "@remixicon/react"

import { cx, focusRing } from "@/lib/utils"

//
// FilterBar -- Zona Z1 canonica do BI Framework (v2, 2026-04-24).
//
// Layout (kit.css .filter-bar):
//   - sticky top 44px (logo abaixo do header global)
//   - padding 10px 24px, gap 8px, flex-wrap
//   - bg branco + border-bottom gray-200 (dark: gray-950 + gray-800)
//   - box-shadow sutil quando scrollado (estado "scrolled")
//
// Aceita qualquer conteudo (geralmente <FilterChip />), alinhado a esquerda.
// Prop `extraActions` fica a direita da barra (ex.: botao "Mais filtros").
//
// A deteccao de scroll e feita via IntersectionObserver com um sentinel
// acima da barra \u2014 mesmo padrao do handoff.
//

type FilterBarProps = {
  children: React.ReactNode
  /** Botoes/aces extras alinhados a direita (ex.: "Mais filtros"). */
  extraActions?: React.ReactNode
  className?: string
}

export function FilterBar({ children, extraActions, className }: FilterBarProps) {
  const [scrolled, setScrolled] = React.useState(false)
  const sentinelRef = React.useRef<HTMLDivElement | null>(null)

  React.useEffect(() => {
    const el = sentinelRef.current
    if (!el) return
    const obs = new IntersectionObserver(
      ([entry]) => setScrolled(!entry.isIntersecting),
      { threshold: 0, rootMargin: "0px 0px 0px 0px" },
    )
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  return (
    <>
      <div ref={sentinelRef} aria-hidden="true" className="h-px w-full" />
      <div
        className={cx(
          "sticky top-0 z-10 -mx-12 flex flex-wrap items-center gap-2 border-b px-12 py-2",
          "bg-white dark:bg-gray-950",
          "border-gray-200 dark:border-gray-800",
          scrolled && "shadow-xs",
          "transition-shadow",
          className,
        )}
      >
        <div className="flex flex-1 flex-wrap items-center gap-2">{children}</div>
        {extraActions && (
          <div className="flex shrink-0 items-center gap-2">{extraActions}</div>
        )}
      </div>
    </>
  )
}

//
// MoreFiltersButton -- botao opcional "Mais filtros" que costuma viver em
// extraActions. Abre um popover/drawer com filtros secundarios (raramente
// usados, que nao justificam um chip permanente).
//

type MoreFiltersButtonProps = {
  onClick?: () => void
  count?: number
  className?: string
}

export function MoreFiltersButton({
  onClick,
  count,
  className,
}: MoreFiltersButtonProps) {
  const hasCount = typeof count === "number" && count > 0
  return (
    <button
      type="button"
      onClick={onClick}
      className={cx(
        "inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded border px-2.5 py-1 text-xs transition",
        hasCount
          ? "border-blue-400 bg-blue-50 text-blue-700 hover:bg-blue-100 dark:border-blue-500 dark:bg-blue-500/10 dark:text-blue-300 dark:hover:bg-blue-500/15"
          : "border-gray-200 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-300 dark:hover:bg-gray-900",
        focusRing,
        className,
      )}
    >
      <RiEqualizerLine className="size-3.5 shrink-0" aria-hidden="true" />
      <span className="font-medium">Mais filtros</span>
      {hasCount && (
        <span
          aria-hidden="true"
          className="inline-flex min-w-4 items-center justify-center rounded-sm bg-blue-500 px-1 text-[10px] font-semibold text-white"
        >
          {count}
        </span>
      )}
    </button>
  )
}
