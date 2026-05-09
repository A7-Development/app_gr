"use client"

import * as React from "react"
import { RiMore2Fill } from "@remixicon/react"

import { cx, focusRing } from "@/lib/utils"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/tremor/DropdownMenu"

//
// CardMenu -- menu "..." canonico em cada VizCard (CLAUDE.md §19.2).
//
// 3 secoes fixas, nessa ordem:
//   1. "Agrupar por"
//   2. "Recorte"
//   3. "Tipo de visualizacao"
//
// Cada secao e um DropdownMenuRadioGroup (selecao unica). O consumidor passa
// as opcoes, o valor atual e o callback de mudanca. Quando o usuario altera
// qualquer selecao, a UI do VizCard deve mostrar <OverrideChip />.
//

export type MenuOption = {
  value: string
  label: string
}

export type MenuSection = {
  value: string
  options: MenuOption[]
  onChange: (value: string) => void
}

type CardMenuProps = {
  agrupar?: MenuSection
  recorte?: MenuSection
  tipo?: MenuSection
  className?: string
}

function MenuGroup({
  label,
  section,
}: {
  label: string
  section: MenuSection
}) {
  return (
    <>
      <DropdownMenuLabel>{label}</DropdownMenuLabel>
      <DropdownMenuRadioGroup
        value={section.value}
        onValueChange={section.onChange}
      >
        {section.options.map((opt) => (
          <DropdownMenuRadioItem key={opt.value} value={opt.value}>
            {opt.label}
          </DropdownMenuRadioItem>
        ))}
      </DropdownMenuRadioGroup>
    </>
  )
}

export function CardMenu({ agrupar, recorte, tipo, className }: CardMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label="Opcoes do grafico"
          className={cx(
            "inline-flex size-6 items-center justify-center rounded text-gray-500 transition-colors",
            "hover:bg-gray-100 hover:text-gray-900",
            "dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-50",
            focusRing,
            className,
          )}
        >
          <RiMore2Fill className="size-4" aria-hidden="true" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" sideOffset={4} className="min-w-60">
        {agrupar && <MenuGroup label="Agrupar por" section={agrupar} />}
        {agrupar && (recorte || tipo) && <DropdownMenuSeparator />}
        {recorte && <MenuGroup label="Recorte" section={recorte} />}
        {recorte && tipo && <DropdownMenuSeparator />}
        {tipo && <MenuGroup label="Tipo de visualizacao" section={tipo} />}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
