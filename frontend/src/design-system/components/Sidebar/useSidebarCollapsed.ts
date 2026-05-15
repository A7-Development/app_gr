// src/design-system/components/Sidebar/useSidebarCollapsed.ts
// Module-level store for sidebar collapsed state.
//
// Binary: expanded <-> hidden (no icon-rail middle state).
// Persisted in localStorage. Synced across all hook consumers in the same tab
// via a tiny pub-sub. Global Cmd/Ctrl+B is registered once on first mount.
//
// Multiple components (AppSidebar, SidebarTrigger, custom UI) read/write the
// same state without needing a Provider in the tree.

"use client"

import * as React from "react"

const STORAGE_KEY = "sidebar:collapsed"

function readInitial(): boolean {
  if (typeof window === "undefined") return false
  try {
    return localStorage.getItem(STORAGE_KEY) === "true"
  } catch {
    return false
  }
}

let _state = readInitial()
const _listeners = new Set<(v: boolean) => void>()
let _shortcutBound = false

function _write(value: boolean) {
  _state = value
  try { localStorage.setItem(STORAGE_KEY, String(value)) } catch {}
  _listeners.forEach((l) => l(value))
}

export function setSidebarCollapsed(value: boolean) { _write(value) }
export function toggleSidebarCollapsed() { _write(!_state) }

export function useSidebarCollapsed() {
  const [collapsed, setLocal] = React.useState(_state)

  React.useEffect(() => {
    _listeners.add(setLocal)
    // Sync the local copy in case the module-level state changed before the
    // effect ran (StrictMode double-invoke, race with another consumer).
    setLocal(_state)
    return () => { _listeners.delete(setLocal) }
  }, [])

  React.useEffect(() => {
    if (_shortcutBound) return
    _shortcutBound = true
    const onKey = (e: KeyboardEvent) => {
      const isMod = e.metaKey || e.ctrlKey
      if (isMod && e.key.toLowerCase() === "b") {
        e.preventDefault()
        toggleSidebarCollapsed()
      }
    }
    window.addEventListener("keydown", onKey)
    return () => {
      window.removeEventListener("keydown", onKey)
      _shortcutBound = false
    }
  }, [])

  const toggle = React.useCallback(() => toggleSidebarCollapsed(), [])
  const setCollapsed = React.useCallback((v: boolean) => setSidebarCollapsed(v), [])

  return { collapsed, setCollapsed, toggle }
}
