// src/design-system/components/Sidebar/useSidebarCollapsed.ts
// Persists sidebar collapsed state in localStorage.

"use client"

import * as React from "react"

const STORAGE_KEY = "sidebar:collapsed"

export function useSidebarCollapsed(defaultCollapsed = false) {
  const [collapsed, setCollapsedState] = React.useState<boolean>(() => {
    if (typeof window === "undefined") return defaultCollapsed
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      return stored !== null ? stored === "true" : defaultCollapsed
    } catch {
      return defaultCollapsed
    }
  })

  const setCollapsed = React.useCallback((value: boolean | ((prev: boolean) => boolean)) => {
    setCollapsedState((prev) => {
      const next = typeof value === "function" ? value(prev) : value
      try { localStorage.setItem(STORAGE_KEY, String(next)) } catch {}
      return next
    })
  }, [])

  const toggle = React.useCallback(() => setCollapsed((c) => !c), [setCollapsed])

  return { collapsed, setCollapsed, toggle }
}
