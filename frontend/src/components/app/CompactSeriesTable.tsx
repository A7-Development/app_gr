"use client"

import * as React from "react"

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRoot,
  TableRow,
} from "@/components/tremor/Table"
import { cx } from "@/lib/utils"

type Density = "ultra" | "compact" | "comfortable"
type Emphasis = "header" | "subtotal" | "total" | "emphasis"
type RowFormat =
  | "brl"
  | "brlFull"
  | "brlK"
  | "pct"
  | "pctPl"
  | "num"
  | "dias"
  | "cota"

export type CompactSeriesRow =
  | {
      label: string
      format?: RowFormat
      values: Record<string, number | null | undefined>
      emphasis?: Emphasis
      indent?: 0 | 1 | 2
      separator?: false
    }
  | { separator: true; label?: undefined }

type PeriodFormat = "mm/aa" | "mmm/aa" | "mm/aaaa"

export type CompactSeriesTableProps = {
  label?: string
  periods: string[]
  rows: CompactSeriesRow[]
  density?: Density
  periodFormat?: PeriodFormat
  footnote?: React.ReactNode
  className?: string
  /**
   * Envolve a tabela em um container com borda + cantos arredondados.
   * Desligue (false) quando a tabela ja estiver dentro de um Card/ChartCard.
   */
  bordered?: boolean
}

const MESES_ABBR = [
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
]

function parsePeriod(iso: string): { year: number; month: number } {
  const m = /^(\d{4})-(\d{2})/.exec(iso)
  if (m) return { year: Number(m[1]), month: Number(m[2]) }
  const d = new Date(iso)
  return { year: d.getFullYear(), month: d.getMonth() + 1 }
}

function formatPeriod(iso: string, fmt: PeriodFormat): string {
  const { year, month } = parsePeriod(iso)
  const mm = String(month).padStart(2, "0")
  const aa = String(year).slice(-2)
  if (fmt === "mm/aa") return `${mm}/${aa}`
  if (fmt === "mm/aaaa") return `${mm}/${year}`
  return `${MESES_ABBR[month - 1]}/${aa}`
}

function formatValue(v: number | null | undefined, fmt: RowFormat): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—"
  switch (fmt) {
    case "brl": {
      const abs = Math.abs(v)
      if (abs >= 1_000_000)
        return `${(v / 1_000_000).toLocaleString("pt-BR", {
          minimumFractionDigits: 1,
          maximumFractionDigits: 1,
        })}M`
      if (abs >= 10_000)
        return `${(v / 1_000).toLocaleString("pt-BR", {
          minimumFractionDigits: 1,
          maximumFractionDigits: 1,
        })}k`
      return v.toLocaleString("pt-BR", { maximumFractionDigits: 0 })
    }
    case "brlFull":
      return v.toLocaleString("pt-BR", { maximumFractionDigits: 0 })
    case "brlK":
      return (v / 1_000).toLocaleString("pt-BR", {
        maximumFractionDigits: 0,
      })
    case "pct":
    case "pctPl":
      return `${v.toLocaleString("pt-BR", {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
      })}%`
    case "num":
      return v.toLocaleString("pt-BR", { maximumFractionDigits: 0 })
    case "dias":
      return `${Math.round(v)}d`
    case "cota":
      return v.toLocaleString("pt-BR", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })
    default:
      return String(v)
  }
}

const DENSITY: Record<
  Density,
  { cell: string; header: string; font: string; labelFont: string }
> = {
  ultra: {
    cell: "px-1.5 py-0 leading-[1.1]",
    header: "px-1.5 py-0.5 leading-[1.1]",
    font: "text-[11px]",
    labelFont: "text-[11px]",
  },
  compact: {
    cell: "px-2 py-0.5 leading-tight",
    header: "px-2 py-1 leading-tight",
    font: "text-xs",
    labelFont: "text-xs",
  },
  comfortable: {
    cell: "px-3 py-1.5 leading-snug",
    header: "px-3 py-2 leading-snug",
    font: "text-xs",
    labelFont: "text-sm",
  },
}

const STICKY_BG = "bg-white dark:bg-gray-950"
const STICKY_BG_HEADER = "bg-gray-50 dark:bg-gray-900"

function rowEmphasisClasses(e: Emphasis | undefined): {
  tr: string
  stickyBg: string
  label: string
} {
  switch (e) {
    case "header":
      return {
        tr: "bg-gray-50 dark:bg-gray-900",
        stickyBg: "bg-gray-50 dark:bg-gray-900",
        label: "font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide",
      }
    case "subtotal":
      return {
        tr: "border-t border-gray-200 dark:border-gray-800",
        stickyBg: STICKY_BG,
        label: "font-medium text-gray-900 dark:text-gray-50",
      }
    case "total":
      return {
        tr: "border-t-2 border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-900",
        stickyBg: "bg-gray-50 dark:bg-gray-900",
        label: "font-semibold text-gray-900 dark:text-gray-50",
      }
    case "emphasis":
      return {
        tr: "",
        stickyBg: STICKY_BG,
        label: "font-medium text-gray-900 dark:text-gray-50",
      }
    default:
      return {
        tr: "",
        stickyBg: STICKY_BG,
        label: "text-gray-700 dark:text-gray-300",
      }
  }
}

const INDENT_CLASS: Record<0 | 1 | 2, string> = {
  0: "",
  1: "pl-3",
  2: "pl-6",
}

/**
 * Tabela compacta para series temporais (periodos como colunas, indicadores
 * como linhas). Inspirada em relatorios de agencias de rating (Austin, Fitch):
 * densidade alta, coluna label sticky, ­enfases hierarquicas (header / subtotal
 * / total), formato de data curto (MM/AA por default).
 *
 * Construida a partir dos primitivos `Table` do Tremor (CLAUDE.md §1 / §3).
 */
export function CompactSeriesTable({
  label = "",
  periods,
  rows,
  density = "compact",
  periodFormat = "mm/aa",
  footnote,
  className,
  bordered = true,
}: CompactSeriesTableProps) {
  const d = DENSITY[density]

  return (
    <div
      className={cx(
        "overflow-hidden",
        bordered &&
          "rounded-lg border border-gray-200 dark:border-gray-800",
        className,
      )}
    >
      <TableRoot className="max-h-[640px]">
        <Table className="border-b-0">
          <TableHead className="sticky top-0 z-10">
            <TableRow
              className={cx(
                "[&_th:first-child]:pl-2 [&_th:last-child]:pr-2",
                STICKY_BG_HEADER,
              )}
            >
              <TableHeaderCell
                className={cx(
                  "sticky left-0 z-20 border-r border-gray-200 dark:border-gray-800",
                  "min-w-[180px] max-w-[240px] text-left text-[10px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-500",
                  STICKY_BG_HEADER,
                  d.header,
                )}
              >
                {label}
              </TableHeaderCell>
              {periods.map((p) => (
                <TableHeaderCell
                  key={p}
                  className={cx(
                    "w-16 text-right text-[10px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-500",
                    d.header,
                  )}
                >
                  {formatPeriod(p, periodFormat)}
                </TableHeaderCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody className="divide-y-0">
            {rows.map((row, idx) => {
              if (row.separator) {
                return (
                  <tr key={`sep-${idx}`}>
                    <td
                      colSpan={periods.length + 1}
                      className="h-1 border-b border-gray-200 p-0 dark:border-gray-800"
                    />
                  </tr>
                )
              }

              const emp = rowEmphasisClasses(row.emphasis)
              const fmt = row.format ?? "num"
              const isHeaderRow = row.emphasis === "header"

              return (
                <TableRow
                  key={`${row.label}-${idx}`}
                  className={cx(
                    "[&_td:first-child]:pl-2 [&_td:last-child]:pr-2",
                    emp.tr,
                  )}
                >
                  <TableCell
                    className={cx(
                      "sticky left-0 border-r border-gray-200 dark:border-gray-800",
                      "min-w-[180px] max-w-[240px] truncate",
                      d.cell,
                      d.labelFont,
                      emp.label,
                      emp.stickyBg,
                      INDENT_CLASS[row.indent ?? 0],
                    )}
                    title={row.label}
                  >
                    {row.label}
                  </TableCell>
                  {periods.map((p) => (
                    <TableCell
                      key={p}
                      className={cx(
                        "w-16 text-right tabular-nums",
                        d.cell,
                        d.font,
                        emp.label,
                      )}
                    >
                      {isHeaderRow ? "" : formatValue(row.values[p], fmt)}
                    </TableCell>
                  ))}
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </TableRoot>
      {footnote ? (
        <div className="border-t border-gray-200 px-3 py-1.5 text-[11px] text-gray-500 dark:border-gray-800 dark:text-gray-500">
          {footnote}
        </div>
      ) : null}
    </div>
  )
}
