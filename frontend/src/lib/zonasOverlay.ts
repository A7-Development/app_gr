// src/lib/zonasOverlay.ts
//
// Store em memória do overlay "Zonas" (andaime de identificação de estrutura).
// Um único flag compartilhado entre o toggle da topbar e os rótulos espalhados
// (áreas, nodes e BLOCOS via SectionRenderer) — assim ligar/desligar reflete
// em todos ao vivo, sem prop-drilling. Persiste em localStorage `gr.zonas`.

"use client"

import * as React from "react"

const KEY = "gr.zonas"
let current = false
let loaded = false
const listeners = new Set<() => void>()

function load(): void {
  if (loaded) return
  try {
    current = window.localStorage.getItem(KEY) === "1"
  } catch {
    /* localStorage indisponível — segue off */
  }
  loaded = true
}

export function getZonas(): boolean {
  load()
  return current
}

export function setZonas(value: boolean): void {
  current = value
  try {
    window.localStorage.setItem(KEY, value ? "1" : "0")
  } catch {
    /* ignore */
  }
  listeners.forEach((l) => l())
}

export function toggleZonas(): void {
  setZonas(!getZonas())
}

/** Hook reativo: re-renderiza quando o overlay liga/desliga. */
export function useZonas(): boolean {
  const [value, setValue] = React.useState(false)
  React.useEffect(() => {
    load()
    setValue(current)
    const l = () => setValue(current)
    listeners.add(l)
    return () => {
      listeners.delete(l)
    }
  }, [])
  return value
}
