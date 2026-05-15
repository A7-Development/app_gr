// src/design-system/components/Sidebar/SidebarTrigger.tsx
// Toggle button for the sidebar — always rendered in the topbar.
//
// V3 collapse is BINARY: when the sidebar is hidden (returns null), this is
// the only visible affordance (besides Cmd/Ctrl+B) to bring it back.

"use client"

import * as React from "react"
import { cx, focusRing } from "@/lib/utils"
import { useSidebarCollapsed } from "./useSidebarCollapsed"

function PanelLeftIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <rect x="3" y="4" width="18" height="16" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M9 4v16" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  )
}

export interface SidebarTriggerProps {
  className?: string
  labelShow?: string
  labelHide?: string
}

export function SidebarTrigger({
  className,
  labelShow = "Mostrar sidebar (⌘B)",
  labelHide = "Ocultar sidebar (⌘B)",
}: SidebarTriggerProps) {
  const { collapsed, toggle } = useSidebarCollapsed()
  const label = collapsed ? labelShow : labelHide
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={label}
      title={label}
      className={cx(
        "inline-flex size-[30px] items-center justify-center rounded-md",
        "text-gray-600 dark:text-gray-300",
        "hover:bg-gray-200/50 hover:text-gray-900 dark:hover:bg-gray-900 dark:hover:text-gray-50",
        "transition-colors duration-100",
        focusRing,
        className,
      )}
    >
      <PanelLeftIcon className="size-[18px] shrink-0" />
    </button>
  )
}
