// src/design-system/components/DenseTable.tsx
//
// Família de tabela densa canônica — preenche o gap entre a <DataTable> (pesada,
// com toolbar/colunas/export/virtualização) e o caso de série temporal. Dois modos:
//
//   <DenseTable>          linha × coluna padrão — blocos de dossiê, fichas,
//                         breakdowns simples (mês × valor). Colunas tipadas.
//   <DenseTable.Series>   TRANSPOSTA — períodos como COLUNAS, indicadores como
//                         linhas (estilo agência de rating: Austin/Fitch). Ênfases
//                         hierárquicas (header/subtotal/total), indent, separator,
//                         coluna-label sticky. Absorveu a antiga CompactSeriesTable.
//
// Visual padrão: contêiner `rounded-md border`, header eyebrow (10px), linhas
// compactas (py-0.5), rodapé de reconciliação opcional. Só `tableTokens`.
// Para listagem grande (sort/virtualização/export) use <DataTable>.

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
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

// ════════════════════════════════════════════════════════════════════════════
// Modo padrão — linha × coluna
// ════════════════════════════════════════════════════════════════════════════

export type DenseAlign = "left" | "right" | "center"
export type DenseFormat = "texto" | "numero" | "brl" | "pct" | "data"

export type DenseColumn = {
  key: string
  label: string
  align?: DenseAlign
  /** Como formatar o valor cru. numero/brl/pct usam tabular-nums + alinham à direita por default. */
  format?: DenseFormat
}

export type DenseValue = string | number | null
export type DenseRow = Record<string, DenseValue>

export type DenseTableProps = {
  columns: DenseColumn[]
  rows: DenseRow[]
  /** Linha de rodapé (reconciliação §14.6) — soma que bate o headline. */
  footer?: DenseRow
  /** Eyebrow acima da tabela. */
  caption?: string
  className?: string
}

const _brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" })

function isNumericFormat(f?: DenseFormat): boolean {
  return f === "numero" || f === "brl" || f === "pct"
}

function formatValue(value: DenseValue, format?: DenseFormat): string {
  if (value == null || value === "") return "—"
  if (typeof value === "string") {
    // 'data': normaliza YYYY-MM / YYYY-MM-DD para MM/AA ou DD/MM/AA.
    if (format === "data") {
      const m = /^(\d{4})-(\d{2})(?:-(\d{2}))?$/.exec(value)
      if (m) return m[3] ? `${m[3]}/${m[2]}/${m[1].slice(2)}` : `${m[2]}/${m[1].slice(2)}`
    }
    return value
  }
  switch (format) {
    case "brl":
      return _brl.format(value)
    case "pct":
      return `${value.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`
    case "numero":
      return value.toLocaleString("pt-BR")
    default:
      return String(value)
  }
}

function alignClass(col: DenseColumn): string {
  const a = col.align ?? (isNumericFormat(col.format) ? "right" : "left")
  return a === "right" ? "text-right" : a === "center" ? "text-center" : "text-left"
}

export function DenseTable({ columns, rows, footer, caption, className }: DenseTableProps) {
  const renderRow = (row: DenseRow, strong = false) =>
    columns.map((col) => (
      <td key={col.key} className={cx("px-3 py-0.5", alignClass(col))}>
        <span
          className={cx(
            isNumericFormat(col.format) ? tableTokens.cellNumber : tableTokens.cellText,
            strong && "font-semibold",
          )}
        >
          {formatValue(row[col.key] ?? null, col.format)}
        </span>
      </td>
    ))

  return (
    <div className={cx("space-y-1.5", className)}>
      {caption && <p className={cx(tableTokens.header, "mb-1")}>{caption}</p>}
      <div className="overflow-hidden rounded-md border border-gray-200 dark:border-gray-800">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-100 bg-gray-50/60 dark:border-gray-900 dark:bg-gray-900/40">
              {columns.map((col) => (
                <th key={col.key} className={cx(tableTokens.header, "px-3 py-1", alignClass(col))}>
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-b border-gray-50 last:border-0 dark:border-gray-900/60">
                {renderRow(row)}
              </tr>
            ))}
            {footer && (
              <tr className="border-t border-t-gray-200 bg-gray-50/60 dark:border-t-gray-800 dark:bg-gray-900/40">
                {renderRow(footer, true)}
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════════
// Modo série — transposta (períodos como colunas). Absorvida da CompactSeriesTable.
// ════════════════════════════════════════════════════════════════════════════

type SeriesDensity = "ultra" | "compact" | "comfortable"
type SeriesEmphasis = "header" | "subtotal" | "total" | "emphasis"
type SeriesRowFormat =
  | "brl"
  | "brlFull"
  | "brlK"
  | "pct"
  | "pctPl"
  | "num"
  | "dias"
  | "cota"

export type DenseSeriesRow =
  | {
      label: string
      format?: SeriesRowFormat
      values: Record<string, number | null | undefined>
      emphasis?: SeriesEmphasis
      indent?: 0 | 1 | 2
      separator?: false
    }
  | { separator: true; label?: undefined }

type SeriesPeriodFormat = "mm/aa" | "mmm/aa" | "mm/aaaa"

export type DenseSeriesTableProps = {
  label?: string
  periods: string[]
  rows: DenseSeriesRow[]
  density?: SeriesDensity
  periodFormat?: SeriesPeriodFormat
  footnote?: React.ReactNode
  className?: string
  /**
   * Envolve a tabela em um container com borda + cantos arredondados.
   * Desligue (false) quando a tabela ja estiver dentro de um Card/ChartCard.
   */
  bordered?: boolean
  /**
   * "fill" (default) — tabela ocupa 100% do container, colunas expandem.
   * "adaptive" — tabela cresce conforme numero de colunas (w-auto) respeitando
   * largura fixa das colunas; excedendo o container, usa barra de rolagem.
   */
  widthMode?: "fill" | "adaptive"
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

function formatSeriesPeriod(iso: string, fmt: SeriesPeriodFormat): string {
  const { year, month } = parsePeriod(iso)
  const mm = String(month).padStart(2, "0")
  const aa = String(year).slice(-2)
  if (fmt === "mm/aa") return `${mm}/${aa}`
  if (fmt === "mm/aaaa") return `${mm}/${year}`
  return `${MESES_ABBR[month - 1]}/${aa}`
}

function formatSeriesValue(v: number | null | undefined, fmt: SeriesRowFormat): string {
  if (v === null || v === undefined || Number.isNaN(v) || v === 0) return "—"
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

const SERIES_DENSITY: Record<
  SeriesDensity,
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

const SERIES_STICKY_BG = "bg-white dark:bg-gray-950"
const SERIES_STICKY_BG_HEADER = "bg-gray-50 dark:bg-gray-900"

function seriesEmphasisClasses(e: SeriesEmphasis | undefined): {
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
        stickyBg: SERIES_STICKY_BG,
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
        stickyBg: SERIES_STICKY_BG,
        label: "font-medium text-gray-900 dark:text-gray-50",
      }
    default:
      return {
        tr: "",
        stickyBg: SERIES_STICKY_BG,
        label: "text-gray-700 dark:text-gray-300",
      }
  }
}

const SERIES_INDENT_CLASS: Record<0 | 1 | 2, string> = {
  0: "",
  1: "pl-3",
  2: "pl-6",
}

/**
 * Tabela densa TRANSPOSTA — períodos como colunas, indicadores como linhas.
 * Estilo agência de rating (Austin, Fitch): densidade alta, coluna label sticky,
 * ênfases hierárquicas (header / subtotal / total), formato de data curto
 * (MM/AA por default). Construída a partir dos primitivos `Table` do Tremor.
 *
 * Use via `<DenseTable.Series>`. Absorveu a antiga CompactSeriesTable.
 */
function DenseSeriesTable({
  label = "",
  periods,
  rows,
  density = "compact",
  periodFormat = "mm/aa",
  footnote,
  className,
  bordered = true,
  widthMode = "fill",
}: DenseSeriesTableProps) {
  const d = SERIES_DENSITY[density]

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
        <Table
          className={cx("border-b-0", widthMode === "adaptive" && "w-auto")}
        >
          <TableHead className="sticky top-0 z-10">
            <TableRow
              className={cx(
                "[&_th:first-child]:pl-2 [&_th:last-child]:pr-2",
                SERIES_STICKY_BG_HEADER,
              )}
            >
              <TableHeaderCell
                className={cx(
                  "sticky left-0 z-20 border-r border-gray-200 dark:border-gray-800",
                  "min-w-[180px] max-w-[240px] text-left text-[10px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-500",
                  SERIES_STICKY_BG_HEADER,
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
                  {formatSeriesPeriod(p, periodFormat)}
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

              const emp = seriesEmphasisClasses(row.emphasis)
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
                      SERIES_INDENT_CLASS[row.indent ?? 0],
                    )}
                    title={row.label}
                  >
                    {row.label}
                  </TableCell>
                  {periods.map((p) => {
                    const raw = row.values[p]
                    const isNegative =
                      typeof raw === "number" &&
                      !Number.isNaN(raw) &&
                      raw < 0
                    return (
                      <TableCell
                        key={p}
                        className={cx(
                          "w-16 text-right tabular-nums",
                          d.cell,
                          d.font,
                          emp.label,
                          isNegative && "text-red-600 dark:text-red-500",
                        )}
                      >
                        {isHeaderRow ? "" : formatSeriesValue(raw, fmt)}
                      </TableCell>
                    )
                  })}
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

// Compound: <DenseTable.Series> é o modo transposto (série temporal).
DenseTable.Series = DenseSeriesTable
