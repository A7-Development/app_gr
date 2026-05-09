// src/design-system/components/StatusPill/index.tsx
// Canonical status pill for FIDC cessão lifecycle.
// Rule: always double-coded — color + icon (8% of men are colorblind).
// Rule: use dot variant for inline text, pill (default) for table cells.

import * as React from "react"
import {
  RiCheckLine,
  RiCheckDoubleLine,
  RiAlertLine,
  RiErrorWarningLine,
  RiCloseCircleLine,
  RiArrowGoBackLine,
} from "@remixicon/react"
import { tv, type VariantProps } from "tailwind-variants"
import { cx } from "@/lib/utils"
import type { StatusKey } from "@/design-system/tokens"

export const STATUS_CONFIG = {
  "em-dia": {
    label:   "Em dia",
    icon:    RiCheckLine,
    classes: "bg-[rgba(22,163,74,.10)] text-[#16A34A] dark:bg-[rgba(74,222,128,.10)] dark:text-[#4ADE80]",
  },
  "atrasado-30": {
    label:   "Atrasado 30d",
    icon:    RiAlertLine,
    classes: "bg-[rgba(202,138,4,.10)] text-[#CA8A04] dark:bg-[rgba(252,211,77,.10)] dark:text-[#FCD34D]",
  },
  "atrasado-60": {
    label:   "Atrasado 60d",
    icon:    RiErrorWarningLine,
    classes: "bg-[rgba(234,88,12,.10)] text-[#EA580C] dark:bg-[rgba(251,146,60,.10)] dark:text-[#FB923C]",
  },
  "inadimplente": {
    label:   "Inadimplente",
    icon:    RiCloseCircleLine,
    classes: "bg-[rgba(220,38,38,.10)] text-[#DC2626] dark:bg-[rgba(248,113,113,.10)] dark:text-[#F87171]",
  },
  "recomprado": {
    label:   "Recomprado",
    icon:    RiArrowGoBackLine,
    classes: "bg-[rgba(115,115,115,.10)] text-[#737373] dark:bg-[rgba(163,163,163,.10)] dark:text-[#A3A3A3]",
  },
  "liquidado": {
    label:   "Liquidado",
    icon:    RiCheckDoubleLine,
    classes: "bg-[rgba(8,145,178,.10)] text-[#0891B2] dark:bg-[rgba(34,211,238,.10)] dark:text-[#22D3EE]",
  },
} as const satisfies Record<StatusKey, {
  label:   string
  icon:    React.ElementType
  classes: string
}>

const pillVariants = tv({
  base: "inline-flex items-center font-medium whitespace-nowrap leading-none",
  variants: {
    variant: {
      pill: "gap-1 rounded-full px-2 py-0.5",
      dot:  "gap-1.5",
    },
    size: {
      sm: "text-[11px]",
      md: "text-xs",
    },
  },
  defaultVariants: {
    variant: "pill",
    size:    "sm",
  },
})

export interface StatusPillProps extends VariantProps<typeof pillVariants> {
  status:    StatusKey
  showIcon?: boolean
  iconOnly?: boolean
  className?: string
}

export function StatusPill({
  status,
  variant = "pill",
  size    = "sm",
  showIcon = true,
  iconOnly = false,
  className,
}: StatusPillProps) {
  const config = STATUS_CONFIG[status]
  const Icon = config.icon
  const iconSize = size === "md" ? "size-3.5" : "size-3"

  if (variant === "dot") {
    return (
      <span className={cx(pillVariants({ variant, size }), config.classes, className)}>
        <span className="size-1.5 rounded-full bg-current shrink-0" aria-hidden="true" />
        {!iconOnly && config.label}
      </span>
    )
  }

  return (
    <span className={cx(pillVariants({ variant, size }), config.classes, className)}>
      {showIcon && !iconOnly && (
        <Icon className={cx(iconSize, "shrink-0")} aria-hidden="true" />
      )}
      {!iconOnly && config.label}
      {iconOnly && <Icon className={cx(iconSize, "shrink-0")} aria-label={config.label} />}
    </span>
  )
}

export type { StatusKey }
