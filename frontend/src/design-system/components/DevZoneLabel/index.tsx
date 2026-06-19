// src/design-system/components/DevZoneLabel/index.tsx
//
// Rótulo de ANDAIME: nomeia uma área da tela (pequeno + faded) pra ajudar a
// identificar as estruturas e pedir ajustes referenciando o nome certo. Liga/
// desliga via toggle (não aparece no uso normal). Posicionado absoluto num
// canto da zona — o container pai precisa ser `relative`.

"use client"

import type * as React from "react"

import { cx } from "@/lib/utils"

type Corner = "tl" | "tr" | "bl" | "br"

const CORNER: Record<Corner, string> = {
  tl: "left-1.5 top-1.5",
  tr: "right-1.5 top-1.5",
  bl: "left-1.5 bottom-1.5",
  br: "right-1.5 bottom-1.5",
}

export function DevZoneLabel({
  children,
  corner = "tl",
  className,
}: {
  children: React.ReactNode
  corner?: Corner
  className?: string
}) {
  return (
    <span
      aria-hidden
      className={cx(
        "pointer-events-none absolute z-50 select-none rounded-sm border px-1.5 py-px",
        "text-[9px] font-medium uppercase tracking-[0.04em] leading-tight",
        "border-gray-300/40 bg-white/65 text-gray-400 backdrop-blur-[1px]",
        "dark:border-gray-600/40 dark:bg-gray-950/65 dark:text-gray-500",
        CORNER[corner],
        className,
      )}
    >
      {children}
    </span>
  )
}
