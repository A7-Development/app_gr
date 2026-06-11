// src/design-system/components/StationStateChip.tsx
//
// Chip de estado no header da estação (handoff Conceito D):
// pill h20, padding 0 8px, 11px/600, ícone 12px. Variantes:
//   blue    — sua vez / decisão            (bg blue 10%, texto #2563EB)
//   indigo  — aguardando homologação        (bg indigo 8%, texto #4F46E5)
//   neutral — aguardando documento/externo  (bg gray-100, texto gray-600)
//   green   — estação fechada               (bg verde 8%, texto #047857)

import * as React from "react"
import type { RemixiconComponentType } from "@remixicon/react"

import { cx } from "@/lib/utils"

export type StationStateChipVariant = "blue" | "indigo" | "neutral" | "green"

const VARIANT_STYLE: Record<StationStateChipVariant, React.CSSProperties> = {
  blue: { background: "rgba(59,130,246,0.1)", color: "#2563EB" },
  indigo: { background: "rgba(99,102,241,0.08)", color: "#4F46E5" },
  neutral: {},
  green: { background: "rgba(5,150,105,0.08)", color: "#047857" },
}

export type StationStateChipProps = {
  variant: StationStateChipVariant
  icon?: RemixiconComponentType
  children: React.ReactNode
  className?: string
}

export function StationStateChip({
  variant,
  icon: Icon,
  children,
  className,
}: StationStateChipProps) {
  return (
    <span
      className={cx(
        "inline-flex h-5 items-center gap-[5px] rounded-full px-2 text-[11px] font-semibold leading-none",
        variant === "neutral" && "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
        className,
      )}
      style={variant === "neutral" ? undefined : VARIANT_STYLE[variant]}
    >
      {Icon && <Icon className="size-3 shrink-0" aria-hidden />}
      {children}
    </span>
  )
}
