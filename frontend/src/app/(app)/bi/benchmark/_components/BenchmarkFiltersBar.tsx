"use client"

import * as React from "react"
import {
  RiCalendarLine,
  RiFundsLine,
  RiLockUnlockLine,
} from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { Checkbox } from "@/components/tremor/Checkbox"
import { Label } from "@/components/tremor/Label"
import { Switch } from "@/components/tremor/Switch"
import { FilterChip } from "@/design-system/components/FilterBar"
import {
  MonthRangePicker,
  type MonthRange,
} from "@/design-system/components/MonthRangePicker"
import { PeriodoPresets } from "@/design-system/components/PeriodoPresets"

import { useBenchmarkFilters } from "../_hooks/useBenchmarkFilters"

//
// Barra de filtros da L2 Benchmark (Z1 v2 — chip format, 2026-04-24).
//
// Chips (esquerda \u2192 direita):
//   [Periodo | 12M]  [Tipo de fundo | Todos]  [Exclusivos | Excluidos]
//
// Cada chip e clicavel; abre popover com o controle real (presets + picker,
// checkboxes, switch). Active state (blue) quando o valor difere do default.
//
// Botao "Limpar filtros" fica a direita (extraActions do FilterBar).
//

const TIPO_FUNDO_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "Fundo", label: "Fundo" },
  { value: "Classe", label: "Classe" },
]

const PRESET_LABEL_SHORT: Record<string, string> = {
  ytd: "YTD",
  "3m": "3M",
  "6m": "6M",
  "12m": "12M",
  "24m": "24M",
  "36m": "36M",
  all: "ALL",
}

function ymToDate(ym?: string): Date | undefined {
  if (!ym) return undefined
  const [y, m] = ym.split("-").map(Number)
  return new Date(y, m - 1, 1)
}

function dateToYm(d?: Date): string | undefined {
  if (!d) return undefined
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, "0")
  return `${y}-${m}`
}

function fmtYmShort(ym?: string): string {
  if (!ym) return "--"
  const [y, m] = ym.split("-")
  const d = new Date(Number(y), Number(m) - 1, 1)
  return d
    .toLocaleString("pt-BR", { month: "short", year: "2-digit" })
    .replace(".", "")
}

type BenchmarkFiltersBarProps = {
  /** Ultima competencia publicada pela CVM (YYYY-MM). */
  fimMercado?: string
}

export function BenchmarkFiltersBar({ fimMercado }: BenchmarkFiltersBarProps) {
  const { filters, preset, setFilter, resetFilters } =
    useBenchmarkFilters(fimMercado)

  const range: MonthRange = {
    from: ymToDate(filters.periodoInicio),
    to: ymToDate(filters.periodoFim),
  }

  const tipoFundoValue = filters.tipoFundo ?? []
  const isPresetDefault = preset === "12m"
  const hasAnyFilter =
    tipoFundoValue.length > 0 ||
    !!filters.incluirExclusivos ||
    !isPresetDefault

  // Resumo textual do chip de Periodo.
  const periodoLabel = preset
    ? PRESET_LABEL_SHORT[preset] ?? "--"
    : `${fmtYmShort(filters.periodoInicio)} \u2192 ${fmtYmShort(filters.periodoFim)}`

  // Resumo textual do chip de Tipo de fundo.
  const tipoFundoLabel =
    tipoFundoValue.length === 0
      ? "Todos"
      : tipoFundoValue.length === 1
        ? tipoFundoValue[0]
        : `${tipoFundoValue.length} selecionados`

  const exclusivosLabel = filters.incluirExclusivos ? "Incluídos" : "Excluídos"

  return (
    <div className="flex flex-wrap items-center gap-2">
      <FilterChip
        icon={RiCalendarLine}
        label="Período"
        value={periodoLabel}
        active={!isPresetDefault}
      >
        <div className="flex flex-col gap-3">
          <div>
            <Label className="mb-1.5 block text-xs font-medium text-gray-500 dark:text-gray-400">
              Preset
            </Label>
            <PeriodoPresets
              value={preset}
              onChange={(p) => setFilter({ preset: p })}
            />
          </div>
          <div>
            <Label className="mb-1.5 block text-xs font-medium text-gray-500 dark:text-gray-400">
              Range customizado
            </Label>
            <MonthRangePicker
              value={range}
              onChange={(v) =>
                setFilter({
                  periodoInicio: dateToYm(v?.from),
                  periodoFim: dateToYm(v?.to),
                })
              }
            />
          </div>
        </div>
      </FilterChip>

      <FilterChip
        icon={RiFundsLine}
        label="Tipo de fundo"
        value={tipoFundoLabel}
        active={tipoFundoValue.length > 0}
      >
        <div className="space-y-2">
          <Label className="text-sm font-medium">Filtrar por tipo</Label>
          <div className="flex flex-col gap-2">
            {TIPO_FUNDO_OPTIONS.map((opt) => {
              const checked = tipoFundoValue.includes(opt.value)
              const id = `bm-tipo-${opt.value}`
              return (
                <div key={opt.value} className="flex items-center gap-2">
                  <Checkbox
                    id={id}
                    checked={checked}
                    onCheckedChange={(c) => {
                      const next = c
                        ? [...tipoFundoValue, opt.value]
                        : tipoFundoValue.filter((v) => v !== opt.value)
                      setFilter({
                        tipoFundo: next.length > 0 ? next : undefined,
                      })
                    }}
                  />
                  <Label htmlFor={id} className="text-sm">
                    {opt.label}
                  </Label>
                </div>
              )
            })}
          </div>
          {tipoFundoValue.length > 0 && (
            <Button
              variant="secondary"
              type="button"
              className="w-full"
              onClick={() => setFilter({ tipoFundo: undefined })}
            >
              Limpar
            </Button>
          )}
        </div>
      </FilterChip>

      <FilterChip
        icon={RiLockUnlockLine}
        label="Exclusivos"
        value={exclusivosLabel}
        active={!!filters.incluirExclusivos}
      >
        <div className="space-y-2">
          <Label className="text-sm font-medium">Fundos exclusivos</Label>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Por padrão, fundos exclusivos (fundo_exclusivo=&apos;S&apos;) são
            excluídos para não distorcer medianas do mercado.
          </p>
          <div className="flex items-center gap-2 pt-1">
            <Switch
              id="bm-incluir-exclusivos"
              checked={!!filters.incluirExclusivos}
              onCheckedChange={(v) =>
                setFilter({ incluirExclusivos: v === true })
              }
            />
            <Label htmlFor="bm-incluir-exclusivos" className="cursor-pointer text-sm">
              Incluir fundos exclusivos
            </Label>
          </div>
        </div>
      </FilterChip>

      {hasAnyFilter && (
        <Button
          variant="ghost"
          onClick={resetFilters}
          className="ml-auto text-xs font-medium text-blue-600 dark:text-blue-400"
        >
          Limpar filtros
        </Button>
      )}
    </div>
  )
}
