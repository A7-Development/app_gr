"use client"

import * as React from "react"

import { Button } from "@/components/tremor/Button"
import { Label } from "@/components/tremor/Label"
import { Switch } from "@/components/tremor/Switch"
import { FilterPill } from "@/components/app/FilterPill"
import {
  MonthRangePicker,
  type MonthRange,
} from "@/components/app/MonthRangePicker"
import { PeriodoPresets } from "@/components/app/PeriodoPresets"
import { cx } from "@/lib/utils"

import { useBenchmarkFilters } from "../_hooks/useBenchmarkFilters"

//
// Barra de filtros da L2 Benchmark.
//
// Layout:
//   [ YTD · 3M · 6M · 12M* · 24M · 36M · ALL ]  [📅 picker]
//   [Tipo de fundo] [Incluir exclusivos ○→●]  [Limpar]
//
// Diferente de BiFiltersBar: zero Produto/UA, + Switch de exclusivos,
// + FilterPill de tipo_fundo. Granularidade mensal (YYYY-MM).
//

const TIPO_FUNDO_OPTIONS = [
  { value: "Fundo", label: "Fundo" },
  { value: "Classe", label: "Classe" },
]

/** Converte 'YYYY-MM' em Date (primeiro dia do mes). */
function ymToDate(ym?: string): Date | undefined {
  if (!ym) return undefined
  const [y, m] = ym.split("-").map(Number)
  return new Date(y, m - 1, 1)
}

/** Converte Date em 'YYYY-MM'. */
function dateToYm(d?: Date): string | undefined {
  if (!d) return undefined
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, "0")
  return `${y}-${m}`
}

type BenchmarkFiltersBarProps = {
  /**
   * Ultima competencia publicada pela CVM (YYYY-MM) — quando disponivel,
   * fim dos ranges rolling acompanha essa data em vez do mes corrente (que
   * ainda nao foi publicado).
   */
  fimMercado?: string
  className?: string
}

export function BenchmarkFiltersBar({
  fimMercado,
  className,
}: BenchmarkFiltersBarProps) {
  const { filters, preset, setFilter, resetFilters } =
    useBenchmarkFilters(fimMercado)

  const range: MonthRange = {
    from: ymToDate(filters.periodoInicio),
    to: ymToDate(filters.periodoFim),
  }

  const tipoFundoValue = filters.tipoFundo ?? []
  const hasAnyFilter =
    tipoFundoValue.length > 0 ||
    !!filters.incluirExclusivos ||
    preset !== "12m"

  return (
    <div
      className={cx(
        "flex flex-wrap items-center gap-2 py-2",
        className,
      )}
    >
      <PeriodoPresets
        value={preset}
        onChange={(p) => setFilter({ preset: p })}
      />

      <MonthRangePicker
        value={range}
        onChange={(v) => {
          // Editar no picker sai do modo preset.
          setFilter({
            periodoInicio: dateToYm(v?.from),
            periodoFim: dateToYm(v?.to),
          })
        }}
      />

      <FilterPill
        title="Tipo de fundo"
        options={TIPO_FUNDO_OPTIONS}
        value={tipoFundoValue}
        onChange={(next) =>
          setFilter({ tipoFundo: next.length > 0 ? next : undefined })
        }
      />

      <label
        className="inline-flex items-center gap-2 rounded border border-dashed border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 dark:border-gray-700 dark:text-gray-300"
        title="Por padrao, fundos exclusivos (fundo_exclusivo='S') sao excluidos do benchmark para evitar distorcer medianas do mercado."
      >
        <Switch
          id="bm-incluir-exclusivos"
          checked={!!filters.incluirExclusivos}
          onCheckedChange={(v) =>
            setFilter({ incluirExclusivos: v === true })
          }
        />
        <Label htmlFor="bm-incluir-exclusivos" className="cursor-pointer">
          Incluir fundos exclusivos
        </Label>
      </label>

      <Button
        variant="ghost"
        onClick={resetFilters}
        disabled={!hasAnyFilter}
        className="font-semibold text-blue-600 disabled:text-gray-400 dark:text-blue-400 dark:disabled:text-gray-600"
      >
        Limpar filtros
      </Button>
    </div>
  )
}
