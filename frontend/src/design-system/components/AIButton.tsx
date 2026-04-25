"use client"

import * as React from "react"
import { RiSparklingFill } from "@remixicon/react"
import { Slot } from "@radix-ui/react-slot"

import { cx, focusRing } from "@/lib/utils"

//
// AIButton -- excecao oficial ao §4 do CLAUDE.md.
//
// Combinacao fixa: bg preto (gray-900) + icone violeta (violet-400).
// Unico ponto do sistema que combina preto solido + violeta. Aparece no
// header de TODA pagina de BI (Zona Z2) como ultimo botao da direita,
// abrindo o AIDrawer com chat contextualizado.
//
// Especificacao: handoff COMPONENTS.md §1 (variante `ai`).
//

type AIButtonProps = {
  asChild?: boolean
  label?: string
} & React.ButtonHTMLAttributes<HTMLButtonElement>

export const AIButton = React.forwardRef<HTMLButtonElement, AIButtonProps>(
  function AIButton(
    { asChild, label = "Perguntar à IA", className, children, ...props },
    ref,
  ) {
    const Component = asChild ? Slot : "button"
    return (
      <Component
        ref={ref}
        className={cx(
          "relative inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded border border-transparent px-3 py-2 text-center text-sm font-medium shadow-xs transition-all duration-100 ease-in-out",
          "bg-gray-900 text-white hover:bg-gray-800",
          "dark:bg-gray-50 dark:text-gray-900 dark:hover:bg-white",
          "disabled:pointer-events-none disabled:opacity-60",
          focusRing,
          className,
        )}
        {...props}
      >
        <RiSparklingFill
          aria-hidden="true"
          className="size-4 shrink-0 text-violet-400 dark:text-violet-500"
        />
        {children ?? label}
      </Component>
    )
  },
)
