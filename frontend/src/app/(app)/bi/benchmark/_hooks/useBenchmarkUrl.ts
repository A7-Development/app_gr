"use client"

import { usePathname, useRouter, useSearchParams } from "next/navigation"
import * as React from "react"

//
// Hooks URL-driven locais da feature Benchmark.
// Seguem CLAUDE.md §11.6: URL e a fonte unica da verdade.
// Padrao espelhado de src/lib/hooks/useBiFilters.ts (multi-select via sp.getAll).
//

const CNPJS_PARAM = "cnpjs"
const CNPJ_PARAM = "cnpj"
const MAX_SELECTED = 5

/**
 * Gerencia o CNPJ unitario (tab Ficha). Singular.
 */
export function useFundoCnpj() {
  const router = useRouter()
  const pathname = usePathname()
  const sp = useSearchParams()
  const cnpj = sp.get(CNPJ_PARAM) ?? null

  const setCnpj = React.useCallback(
    (next: string | null) => {
      const n = new URLSearchParams(sp.toString())
      if (next) n.set(CNPJ_PARAM, next)
      else n.delete(CNPJ_PARAM)
      router.replace(`${pathname}?${n.toString()}`, { scroll: false })
    },
    [router, pathname, sp],
  )

  return { cnpj, setCnpj }
}

/**
 * Gerencia os CNPJs selecionados para comparativo (tab Lista + Comparativo).
 * Multi-valor via `?cnpjs=A&cnpjs=B`, cap de 5.
 */
export function useSelectedFundos() {
  const router = useRouter()
  const pathname = usePathname()
  const sp = useSearchParams()

  const selected = React.useMemo(() => sp.getAll(CNPJS_PARAM), [sp])

  const replace = React.useCallback(
    (next: string[]) => {
      const n = new URLSearchParams()
      // Preserva todos os parametros que nao sao cnpjs
      sp.forEach((value, key) => {
        if (key !== CNPJS_PARAM) n.append(key, value)
      })
      for (const cnpj of next) n.append(CNPJS_PARAM, cnpj)
      router.replace(`${pathname}?${n.toString()}`, { scroll: false })
    },
    [router, pathname, sp],
  )

  const toggle = React.useCallback(
    (cnpj: string) => {
      if (selected.includes(cnpj)) {
        replace(selected.filter((c) => c !== cnpj))
      } else {
        if (selected.length >= MAX_SELECTED) return
        replace([...selected, cnpj])
      }
    },
    [selected, replace],
  )

  const remove = React.useCallback(
    (cnpj: string) => replace(selected.filter((c) => c !== cnpj)),
    [selected, replace],
  )

  const clear = React.useCallback(() => replace([]), [replace])

  const isSelected = React.useCallback(
    (cnpj: string) => selected.includes(cnpj),
    [selected],
  )

  const isFull = selected.length >= MAX_SELECTED

  return { selected, toggle, remove, clear, isSelected, isFull, max: MAX_SELECTED }
}

/** Ajuda a construir href de tab preservando demais parametros. */
export function useBuildTabHref() {
  const pathname = usePathname()
  const sp = useSearchParams()
  return React.useCallback(
    (tab: string) => {
      const n = new URLSearchParams(sp.toString())
      n.set("tab", tab)
      return `${pathname}?${n.toString()}`
    },
    [pathname, sp],
  )
}
