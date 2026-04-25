"use client"

import * as React from "react"
import { RiArrowDownSLine, type RemixiconComponentType } from "@remixicon/react"

import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/tremor/Popover"
import { cx, focusRing } from "@/lib/utils"

//
// FilterChip -- chip can\u00f4nico da Zona Z1 do BI Framework v2.
//
// Difere do <FilterPill /> (pending-state, multi-select com "Aplicar"):
// o FilterChip mostra SEMPRE o valor atual (label + pipe + value + chevron)
// e abre um popover com conteudo livre. Serve pra filtros single-select
// (Periodo, Produto, Filial, Granularidade, Competencia, ...) onde o valor
// selecionado e informativo por si so.
//
// Handoff v2 (BiCarteiraV2.jsx + kit.css):
//   <div className="fb-chip [active]">
//     <icon />
//     <span className="fb-label">Periodo</span>
//     <span className="fb-sep" />
//     <span className="fb-val">{value}</span>
//     <RiArrowDownSLine />
//   </div>
//
// Active state: quando o valor difere do default, border vira blue-400,
// bg vira blue-50 e o valor blue-700 (CLAUDE.md \u00a74 \u2014 azul = aten\u00e7\u00e3o/selecao).
//

type FilterChipProps = {
  /** Rotulo curto do filtro (ex.: "Periodo", "Produto"). */
  label: string
  /** Valor atual, exibido em destaque apos o separador. */
  value: React.ReactNode
  /** Quando true, pinta o chip em azul (filtro diferente do default). */
  active?: boolean
  /** Icone opcional antes do label (ex.: RiCalendarLine). */
  icon?: RemixiconComponentType
  /** Conteudo do popover \u2014 renderizado quando o chip e clicado. */
  children?: React.ReactNode
  className?: string
}

export function FilterChip({
  label,
  value,
  active = false,
  icon: Icon,
  children,
  className,
}: FilterChipProps) {
  const trigger = (
    <button
      type="button"
      className={cx(
        "inline-flex shrink-0 items-center gap-2 whitespace-nowrap rounded border px-2.5 py-1 text-xs transition",
        active
          ? "border-blue-400 bg-blue-50 text-gray-900 hover:bg-blue-100 dark:border-blue-500 dark:bg-blue-500/10 dark:text-gray-50 dark:hover:bg-blue-500/15"
          : "border-gray-200 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-300 dark:hover:bg-gray-900",
        focusRing,
        className,
      )}
    >
      {Icon && (
        <Icon
          className={cx(
            "size-3.5 shrink-0",
            active
              ? "text-blue-600 dark:text-blue-400"
              : "text-gray-500 dark:text-gray-400",
          )}
          aria-hidden="true"
        />
      )}
      <span
        className={cx(
          "text-[11px]",
          active
            ? "text-gray-600 dark:text-gray-400"
            : "text-gray-500 dark:text-gray-400",
        )}
      >
        {label}
      </span>
      <span
        aria-hidden="true"
        className={cx(
          "h-3.5 w-px",
          active ? "bg-blue-300 dark:bg-blue-700" : "bg-gray-200 dark:bg-gray-700",
        )}
      />
      <span
        className={cx(
          "font-medium",
          active
            ? "text-blue-700 dark:text-blue-300"
            : "text-gray-900 dark:text-gray-50",
        )}
      >
        {value}
      </span>
      <RiArrowDownSLine
        aria-hidden="true"
        className={cx(
          "size-3.5 shrink-0",
          active
            ? "text-blue-500 dark:text-blue-400"
            : "text-gray-400 dark:text-gray-500",
        )}
      />
    </button>
  )

  if (!children) return trigger

  return (
    <Popover>
      <PopoverTrigger asChild>{trigger}</PopoverTrigger>
      <PopoverContent align="start" sideOffset={6} className="min-w-56 max-w-72">
        {children}
      </PopoverContent>
    </Popover>
  )
}
