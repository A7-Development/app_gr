// src/design-system/components/Sidebar/BrandCard.tsx
// Brand header for the sidebar. Logo (Strata icon) in a card + brand name + tagline.
// Default logo uses the project Logo component (PNG with text fallback).

"use client"

import * as React from "react"
import { cx } from "@/lib/utils"
import { Logo } from "@/design-system/components/Logo"

export interface BrandCardProps {
  brandName?: string
  tagline?: string
  logo?: React.ReactNode
  className?: string
}

export function BrandCard({
  brandName = "Strata",
  tagline = "FIDC Analytics",
  logo,
  className,
}: BrandCardProps) {
  return (
    <div className={cx("flex items-center gap-2.5", className)}>
      {logo ?? <Logo variant="icon" className="size-8" />}
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold leading-tight tracking-[-0.005em] text-gray-900 dark:text-gray-50">
          {brandName}
        </p>
        <p className="truncate text-[11px] leading-tight text-gray-500 dark:text-gray-400">
          {tagline}
        </p>
      </div>
    </div>
  )
}
