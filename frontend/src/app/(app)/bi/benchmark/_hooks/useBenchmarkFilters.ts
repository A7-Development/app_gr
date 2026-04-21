"use client"

import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { useCallback, useMemo } from "react"

import type { BenchmarkRangeFilters } from "@/lib/api-client"
import { PRESET_KEYS, type PresetKey } from "@/lib/hooks/useBiFilters"

//
// Filtros globais da L2 Benchmark, sincronizados com a URL (CLAUDE.md §11.6.3).
//
// Diferente de `useBiFilters` (operacoes internas do tenant):
//   - granularidade mensal (YYYY-MM), nao diaria
//   - SEM produto/UA (dado publico CVM — nao tem taxonomia do tenant)
//   - COM tipo_fundo (Fundo vs Classe) + incluir_exclusivos (switch)
//
// Reutiliza `PresetKey` + `PRESET_KEYS` de useBiFilters pra aproveitar o
// componente `PeriodoPresets` sem adaptacao de tipo.
//

const DEFAULT_PRESET: PresetKey = "12m"

// Fallback para o preset `all` caso ainda nao tenhamos a competencia minima
// vinda do backend (endpoint /benchmark/data-minima nao existe hoje; CVM
// publica desde 2017, entao 2015 cobre com folga).
const FALLBACK_ALL_START_YM = "2015-01"

//
// Helpers puros — granularidade mensal (YYYY-MM).
//

function toYm(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, "0")
  return `${y}-${m}`
}

function subMonthsYm(base: Date, months: number): string {
  const d = new Date(base.getFullYear(), base.getMonth() - months, 1)
  return toYm(d)
}

/**
 * Calcula o range (inicio, fim) em 'YYYY-MM' a partir de um preset,
 * usando `today` como referencia. `fimMercado` e a ultima competencia
 * publicada pela CVM (ex.: 2 meses atras) — quando disponivel, fim do
 * range vai ate ela (em vez do mes corrente, que ainda nao foi publicado).
 */
export function computeBenchmarkPresetRange(
  preset: PresetKey,
  today: Date,
  fimMercado?: string,
): { inicio: string; fim: string } {
  const fim = fimMercado ?? toYm(today)
  // Base para subtracao: se temos fimMercado, usa ele; senao, today.
  const fimDate = fimMercado
    ? new Date(
        Number(fimMercado.slice(0, 4)),
        Number(fimMercado.slice(5, 7)) - 1,
        1,
      )
    : today

  switch (preset) {
    case "ytd":
      return { inicio: `${fimDate.getFullYear()}-01`, fim }
    case "3m":
      return { inicio: subMonthsYm(fimDate, 2), fim }
    case "6m":
      return { inicio: subMonthsYm(fimDate, 5), fim }
    case "12m":
      return { inicio: subMonthsYm(fimDate, 11), fim }
    case "24m":
      return { inicio: subMonthsYm(fimDate, 23), fim }
    case "36m":
      return { inicio: subMonthsYm(fimDate, 35), fim }
    case "all":
      return { inicio: FALLBACK_ALL_START_YM, fim }
  }
}

function isBenchmarkPresetKey(v: string | null): v is PresetKey {
  return v !== null && (PRESET_KEYS as readonly string[]).includes(v)
}

/** URL param name helpers — um unico lugar pra evitar typo. */
const P_INICIO = "periodo_inicio"
const P_FIM = "periodo_fim"
const P_TIPO = "tipo_fundo"
const P_INCL_EXCL = "incluir_exclusivos"
const P_PRESET = "preset"

/** Converte YYYY-MM-DD (legado) ou YYYY-MM em YYYY-MM. */
function normalizeYm(v: string | null): string | undefined {
  if (!v) return undefined
  // Aceita ambos YYYY-MM e YYYY-MM-DD na URL — devolve sempre YYYY-MM.
  return v.length >= 7 ? v.slice(0, 7) : undefined
}

export type BenchmarkFiltersPatch = {
  preset?: PresetKey | null
  periodoInicio?: string | undefined // 'YYYY-MM'
  periodoFim?: string | undefined // 'YYYY-MM'
  tipoFundo?: string[] | undefined
  incluirExclusivos?: boolean
}

export type UseBenchmarkFiltersResult = {
  /** Filtros resolvidos — preset expandido em periodoInicio/periodoFim. */
  filters: BenchmarkRangeFilters
  /** Preset ativo, ou `null` em modo custom (usuario editou MonthRangePicker). */
  preset: PresetKey | null
  setFilter: (patch: BenchmarkFiltersPatch) => void
  resetFilters: () => void
}

/**
 * Mesma logica de precedencia do `useBiFilters`:
 *   1. `?periodo_inicio`+`?periodo_fim` explicitos → modo custom, preset = null
 *   2. `?preset=xx` → computa range rolling mensal
 *   3. Nada → default: preset `12m`
 *
 * `fimMercado` e passado por quem renderiza (tipicamente `BenchmarkFiltersBar`)
 * — pode ser a `competencia` do `/benchmark/resumo` sem filtros. Quando omitido,
 * fim do range rolling cai no mes corrente (que pode nao ter dado ainda).
 */
export function useBenchmarkFilters(
  fimMercado?: string,
): UseBenchmarkFiltersResult {
  const router = useRouter()
  const pathname = usePathname()
  const sp = useSearchParams()

  const presetFromUrl = sp.get(P_PRESET)
  const hasExplicitPeriodo =
    sp.get(P_INICIO) !== null || sp.get(P_FIM) !== null

  const preset: PresetKey | null = hasExplicitPeriodo
    ? null
    : isBenchmarkPresetKey(presetFromUrl)
      ? presetFromUrl
      : DEFAULT_PRESET

  const presetRange = useMemo(() => {
    if (!preset) return null
    return computeBenchmarkPresetRange(preset, new Date(), fimMercado)
  }, [preset, fimMercado])

  const filters: BenchmarkRangeFilters = useMemo(() => {
    const tipoFundo = sp.getAll(P_TIPO)
    const incluirExclusivos = sp.get(P_INCL_EXCL) === "true"

    const periodoInicio = presetRange
      ? presetRange.inicio
      : normalizeYm(sp.get(P_INICIO))
    const periodoFim = presetRange
      ? presetRange.fim
      : normalizeYm(sp.get(P_FIM))

    return {
      periodoInicio,
      periodoFim,
      tipoFundo: tipoFundo.length > 0 ? tipoFundo : undefined,
      incluirExclusivos,
    }
  }, [sp, presetRange])

  const setFilter = useCallback(
    (patch: BenchmarkFiltersPatch) => {
      const next = new URLSearchParams(sp.toString())

      // Coerencia preset ↔ periodo: mutuamente exclusivos.
      if ("preset" in patch) {
        if (patch.preset) {
          next.set(P_PRESET, patch.preset)
          next.delete(P_INICIO)
          next.delete(P_FIM)
        } else {
          next.delete(P_PRESET)
        }
      }
      if ("periodoInicio" in patch || "periodoFim" in patch) {
        if (!("preset" in patch)) next.delete(P_PRESET)
        if ("periodoInicio" in patch) {
          if (patch.periodoInicio) next.set(P_INICIO, patch.periodoInicio)
          else next.delete(P_INICIO)
        }
        if ("periodoFim" in patch) {
          if (patch.periodoFim) next.set(P_FIM, patch.periodoFim)
          else next.delete(P_FIM)
        }
      }

      if ("tipoFundo" in patch) {
        next.delete(P_TIPO)
        if (patch.tipoFundo && patch.tipoFundo.length > 0) {
          for (const t of patch.tipoFundo) next.append(P_TIPO, t)
        }
      }

      if ("incluirExclusivos" in patch) {
        if (patch.incluirExclusivos) next.set(P_INCL_EXCL, "true")
        else next.delete(P_INCL_EXCL)
      }

      router.replace(`${pathname}?${next.toString()}`, { scroll: false })
    },
    [router, pathname, sp],
  )

  const resetFilters = useCallback(() => {
    const next = new URLSearchParams(sp.toString())
    next.delete(P_INICIO)
    next.delete(P_FIM)
    next.delete(P_TIPO)
    next.delete(P_INCL_EXCL)
    next.delete(P_PRESET)
    router.replace(`${pathname}?${next.toString()}`, { scroll: false })
  }, [router, pathname, sp])

  return { filters, preset, setFilter, resetFilters }
}
