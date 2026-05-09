// src/design-system/components/ApprovalQueueBadge/index.tsx
// Compact badge for sidebar items with pending approval jobs.
// Inspired by Modern Treasury approval queue pattern.
// Pulses when count > 0 to draw attention without being disruptive.

import * as React from "react"
import { cx } from "@/lib/utils"

export interface ApprovalQueueBadgeProps {
  count: number
  className?: string
}

export function ApprovalQueueBadge({ count, className }: ApprovalQueueBadgeProps) {
  if (count <= 0) return null

  const label = count > 99 ? "99+" : String(count)

  return (
    <span
      aria-label={`${label} pendente${count !== 1 ? "s" : ""}`}
      className={cx(
        "ml-auto inline-flex min-w-[18px] items-center justify-center",
        "rounded-full px-1.5 py-px",
        "text-[10px] font-semibold leading-none tabular-nums",
        "bg-red-600/90 text-white dark:bg-red-500/90",
        "animate-pulse",
        className,
      )}
    >
      {label}
    </span>
  )
}
