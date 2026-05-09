"use client"

import * as React from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { useQuery } from "@tanstack/react-query"

import { Button } from "@/components/tremor/Button"
import {
  MonthRangePicker,
  type MonthRange,
} from "@/design-system/components/MonthRangePicker"
import { PeriodoPresets } from "@/design-system/components/PeriodoPresets"
import { cx } from "@/lib/utils"
import { biBenchmark } from "@/lib/api-client"
import { useBiFilters } from "@/lib/hooks/useBiFilters"

import { FundoCombobox } from "./FundoCombobox"

function toISO(d?: Date): string | undefined {
  if (!d) return undefined
  const yyyy = d.getFullYear()
  const mm = String(d.getMonth() + 1).padStart(2, "0")
  const dd = String(d.getDate()).padStart(2, "0")
  return `${yyyy}-${mm}-${dd}`
}

function fromISO(s?: string): Date | undefined {
  if (!s) return undefined
  const [y, m, d] = s.split("-").map(Number)
  return new Date(y, m - 1, d)
}

//
// FichaFiltersBar — barra de filtros especifica da tab "Ficha do fundo".
// Estrutura igual a /bi/operacoes (BiFiltersBar) porem enxuta para o contexto
// de benchmark publico: apenas periodo (presets + picker) + seletor de fundo.
// Sem Produto/UA (nao se aplicam a dados CVM publicos).
//
// URL e fonte unica da verdade (CLAUDE.md §11.6.3):
//  - periodo: preset | periodo_inicio/fim (mutuamente exclusivos)
//  - cnpj: cnpj=<digits>
//
// "Limpar filtros" remove apenas preset/periodo/cnpj — preserva ?tab=ficha
// e demais parametros (ex.: cnpjs da tab Comparativo).
//
export function FichaFiltersBar() {
  const router = useRouter()
  const pathname = usePathname()
  const sp = useSearchParams()

  // Dado publico da CVM — dataMinima vem do range global de competencias
  // (cvm_remote.competencias). Cache 6h: so muda com ETL rodando.
  const cvmRangeQuery = useQuery({
    queryKey: ["bi", "benchmark", "cvm-range"],
    queryFn: () => biBenchmark.cvmRange(),
    staleTime: 6 * 60 * 60 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  })
  const dataMinima = cvmRangeQuery.data?.data_minima ?? undefined

  const { filters, preset, setFilter } = useBiFilters(dataMinima)

  const range: MonthRange = {
    from: fromISO(filters.periodoInicio),
    to: fromISO(filters.periodoFim),
  }

  const hasAnyFilter =
    sp.get("preset") !== null ||
    sp.get("periodo_inicio") !== null ||
    sp.get("periodo_fim") !== null ||
    sp.get("cnpj") !== null

  const resetFichaFilters = React.useCallback(() => {
    const next = new URLSearchParams(sp.toString())
    next.delete("preset")
    next.delete("periodo_inicio")
    next.delete("periodo_fim")
    next.delete("cnpj")
    router.replace(`${pathname}?${next.toString()}`, { scroll: false })
  }, [router, pathname, sp])

  return (
    <div className={cx("flex flex-wrap items-center gap-2 py-2")}>
      <PeriodoPresets
        value={preset}
        onChange={(p) => setFilter({ preset: p })}
      />

      <MonthRangePicker
        value={range}
        onChange={(v) => {
          setFilter({
            periodoInicio: toISO(v?.from),
            periodoFim: toISO(v?.to),
          })
        }}
      />

      <FundoCombobox />

      <Button
        variant="ghost"
        onClick={resetFichaFilters}
        disabled={!hasAnyFilter}
        className="font-semibold text-blue-600 disabled:text-gray-400 dark:text-blue-400 dark:disabled:text-gray-600"
      >
        Limpar filtros
      </Button>
    </div>
  )
}
