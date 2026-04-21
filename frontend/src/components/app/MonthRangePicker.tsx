"use client"

import * as React from "react"
import {
  RiArrowDownSLine,
  RiArrowLeftSLine,
  RiArrowRightSLine,
  RiCalendar2Line,
} from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import {
  Popover,
  PopoverClose,
  PopoverContent,
  PopoverTrigger,
} from "@/components/tremor/Popover"
import { cx, focusRing } from "@/lib/utils"

//
// Tipos
//

/**
 * Range de meses. `from`/`to` sao Dates "normais" (dia dentro do mes
 * nao importa internamente), mas `onChange` sempre devolve:
 *   from = 1o dia do mes selecionado (YYYY-MM-01)
 *   to   = ultimo dia do mes selecionado (YYYY-MM-<lastDay>)
 *
 * Essa semantica casa com o filtro de BI do projeto, que opera sempre em
 * granularidade mensal — evita drama de timezone/fuso e alinha com os
 * presets (YTD, 3M, 12M, etc.).
 */
export type MonthRange = {
  from: Date | undefined
  to: Date | undefined
}

type MonthRangePickerProps = {
  value: MonthRange
  onChange: (range: MonthRange) => void
  /** Ano minimo navegavel (default: 5 anos atras). */
  minYear?: number
  /** Ano maximo navegavel (default: ano atual + 1). */
  maxYear?: number
  className?: string
  /** Se true, desabilita interacao (apenas display). Raro. */
  disabled?: boolean
}

//
// Constantes
//

const MESES_PT = [
  "jan",
  "fev",
  "mar",
  "abr",
  "mai",
  "jun",
  "jul",
  "ago",
  "set",
  "out",
  "nov",
  "dez",
] as const

//
// Helpers puros
//

function startOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1)
}

function endOfMonth(d: Date): Date {
  // Dia 0 do mes (m+1) = ultimo dia do mes m.
  return new Date(d.getFullYear(), d.getMonth() + 1, 0)
}

/** Compara dois Dates apenas na granularidade mes-ano. */
function sameMonth(a: Date | undefined, b: Date | undefined): boolean {
  if (!a || !b) return false
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth()
}

/** Formata 'abr/2025' (ou 'abr/25' em modo compacto). */
function formatMonthLabel(d: Date | undefined, compact = false): string {
  if (!d) return "—"
  const mes = MESES_PT[d.getMonth()]
  const ano = compact
    ? String(d.getFullYear()).slice(-2)
    : String(d.getFullYear())
  return `${mes}/${ano}`
}

//
// Sub-componente: grid de 12 meses para um ano
//

type MonthGridProps = {
  ano: number
  onAnoChange: (ano: number) => void
  minAno: number
  maxAno: number
  selected: Date | undefined
  /** Title label ("Início" ou "Fim"). */
  label: string
  onSelectMonth: (d: Date) => void
  /** Usado para desabilitar meses fora do limite valido (ex.: grid "Fim"
   *  nao deve permitir um mes anterior ao `from` ja selecionado). */
  isMonthDisabled?: (ano: number, mes: number) => boolean
}

function MonthGrid({
  ano,
  onAnoChange,
  minAno,
  maxAno,
  selected,
  label,
  onSelectMonth,
  isMonthDisabled,
}: MonthGridProps) {
  const canPrev = ano > minAno
  const canNext = ano < maxAno

  return (
    <div className="flex flex-col gap-2">
      {/* Label + nav de ano */}
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
          {label}
        </span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-label="Ano anterior"
            disabled={!canPrev}
            onClick={() => canPrev && onAnoChange(ano - 1)}
            className={cx(
              "inline-flex size-6 items-center justify-center rounded text-gray-500 transition hover:text-gray-900 disabled:cursor-not-allowed disabled:opacity-40 dark:text-gray-400 hover:dark:text-gray-50",
              focusRing,
            )}
          >
            <RiArrowLeftSLine className="size-4" />
          </button>
          <span className="min-w-12 text-center text-sm font-semibold tabular-nums text-gray-900 dark:text-gray-50">
            {ano}
          </span>
          <button
            type="button"
            aria-label="Próximo ano"
            disabled={!canNext}
            onClick={() => canNext && onAnoChange(ano + 1)}
            className={cx(
              "inline-flex size-6 items-center justify-center rounded text-gray-500 transition hover:text-gray-900 disabled:cursor-not-allowed disabled:opacity-40 dark:text-gray-400 hover:dark:text-gray-50",
              focusRing,
            )}
          >
            <RiArrowRightSLine className="size-4" />
          </button>
        </div>
      </div>

      {/* Grid 3x4 de meses */}
      <div className="grid grid-cols-3 gap-1">
        {MESES_PT.map((nome, idx) => {
          const monthDate = new Date(ano, idx, 1)
          const isSelected = sameMonth(selected, monthDate)
          const disabled = isMonthDisabled?.(ano, idx) ?? false

          return (
            <button
              key={nome}
              type="button"
              disabled={disabled}
              aria-pressed={isSelected}
              aria-label={`${nome}/${ano}`}
              onClick={() => onSelectMonth(monthDate)}
              className={cx(
                "rounded px-2 py-1.5 text-xs font-medium capitalize transition",
                isSelected
                  ? "bg-blue-500 text-white dark:bg-blue-500"
                  : "text-gray-700 hover:bg-gray-100 dark:text-gray-300 hover:dark:bg-gray-800",
                disabled &&
                  "cursor-not-allowed text-gray-300 line-through hover:bg-transparent dark:text-gray-700 hover:dark:bg-transparent",
                focusRing,
              )}
            >
              {nome}
            </button>
          )
        })}
      </div>
    </div>
  )
}

//
// MonthRangePicker
//

export function MonthRangePicker({
  value,
  onChange,
  minYear,
  maxYear,
  className,
  disabled,
}: MonthRangePickerProps) {
  const hoje = new Date()
  const minAno = minYear ?? hoje.getFullYear() - 10
  const maxAno = maxYear ?? hoje.getFullYear() + 1

  // Estado do popover
  const [open, setOpen] = React.useState(false)

  // Estado pending — so commita quando clica "Aplicar".
  const [pendingFrom, setPendingFrom] = React.useState<Date | undefined>(
    value.from,
  )
  const [pendingTo, setPendingTo] = React.useState<Date | undefined>(value.to)

  // Ano "navegado" em cada grid. Independente dos valores selecionados —
  // usuario pode querer ver outro ano sem desmarcar nada.
  const [anoInicio, setAnoInicio] = React.useState<number>(
    value.from?.getFullYear() ?? hoje.getFullYear() - 1,
  )
  const [anoFim, setAnoFim] = React.useState<number>(
    value.to?.getFullYear() ?? hoje.getFullYear(),
  )

  // Toda vez que o popover abre, sincroniza o pending com o value atual.
  React.useEffect(() => {
    if (open) {
      setPendingFrom(value.from)
      setPendingTo(value.to)
      setAnoInicio(value.from?.getFullYear() ?? hoje.getFullYear() - 1)
      setAnoFim(value.to?.getFullYear() ?? hoje.getFullYear())
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  // Regras:
  //  - Grid "Fim" nao permite mes anterior ao `pendingFrom`.
  //  - Grid "Inicio" nao permite mes posterior ao `pendingTo`.
  const isFimDisabled = (ano: number, mes: number) => {
    if (!pendingFrom) return false
    const candidate = new Date(ano, mes, 1)
    return candidate < startOfMonth(pendingFrom)
  }
  const isInicioDisabled = (ano: number, mes: number) => {
    if (!pendingTo) return false
    const candidate = new Date(ano, mes, 1)
    return candidate > startOfMonth(pendingTo)
  }

  const handleSelectInicio = (d: Date) => {
    // Forca dia 1 (inicio do mes)
    const inicio = startOfMonth(d)
    setPendingFrom(inicio)
    // Se pendingTo for anterior, zera
    if (pendingTo && pendingTo < inicio) setPendingTo(undefined)
  }

  const handleSelectFim = (d: Date) => {
    // Forca ultimo dia do mes
    const fim = endOfMonth(d)
    setPendingTo(fim)
    if (pendingFrom && pendingFrom > fim) setPendingFrom(undefined)
  }

  const canApply = Boolean(pendingFrom && pendingTo)

  const handleApply = () => {
    if (canApply) {
      onChange({
        from: pendingFrom ? startOfMonth(pendingFrom) : undefined,
        to: pendingTo ? endOfMonth(pendingTo) : undefined,
      })
      setOpen(false)
    }
  }

  // Label do trigger (formato compacto mes/aa)
  const triggerLabel = React.useMemo(() => {
    if (value.from && value.to) {
      return `${formatMonthLabel(value.from, true)} — ${formatMonthLabel(value.to, true)}`
    }
    if (value.from) return `Desde ${formatMonthLabel(value.from, true)}`
    if (value.to) return `Ate ${formatMonthLabel(value.to, true)}`
    return "Selecione o periodo"
  }, [value.from, value.to])

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          disabled={disabled}
          className={cx(
            "inline-flex items-center gap-x-2 rounded border border-gray-300 bg-white px-2 py-1.5 text-xs font-medium text-gray-900 shadow-xs transition",
            "hover:bg-gray-50 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-50 hover:dark:bg-gray-950/50",
            "disabled:cursor-not-allowed disabled:opacity-50",
            focusRing,
            className,
          )}
        >
          <RiCalendar2Line
            aria-hidden="true"
            className="size-4 shrink-0 text-gray-400 dark:text-gray-600"
          />
          <span className="tabular-nums">{triggerLabel}</span>
          <RiArrowDownSLine
            aria-hidden="true"
            className="size-4 shrink-0 text-gray-500"
          />
        </button>
      </PopoverTrigger>

      <PopoverContent align="start" sideOffset={6} className="w-auto p-4">
        <div className="flex flex-col gap-4">
          {/* Dois grids lado a lado */}
          <div className="flex gap-4">
            <MonthGrid
              ano={anoInicio}
              onAnoChange={setAnoInicio}
              minAno={minAno}
              maxAno={maxAno}
              selected={pendingFrom}
              label="Início"
              onSelectMonth={handleSelectInicio}
              isMonthDisabled={isInicioDisabled}
            />
            <div className="w-px bg-gray-200 dark:bg-gray-800" aria-hidden />
            <MonthGrid
              ano={anoFim}
              onAnoChange={setAnoFim}
              minAno={minAno}
              maxAno={maxAno}
              selected={pendingTo}
              label="Fim"
              onSelectMonth={handleSelectFim}
              isMonthDisabled={isFimDisabled}
            />
          </div>

          {/* Rodape */}
          <div className="flex items-center justify-between gap-2 border-t border-gray-200 pt-3 dark:border-gray-800">
            <span className="text-[11px] text-gray-500 dark:text-gray-400">
              {pendingFrom && pendingTo
                ? `${formatMonthLabel(pendingFrom, false)} a ${formatMonthLabel(pendingTo, false)}`
                : "Escolha o mês de início e o mês de fim"}
            </span>
            <div className="flex items-center gap-2">
              <PopoverClose asChild>
                <Button variant="secondary" className="h-auto px-3 py-1">
                  Cancelar
                </Button>
              </PopoverClose>
              <Button
                type="button"
                disabled={!canApply}
                onClick={handleApply}
                className="h-auto px-3 py-1"
              >
                Aplicar
              </Button>
            </div>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  )
}
