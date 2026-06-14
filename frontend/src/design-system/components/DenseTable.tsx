// src/design-system/components/DenseTable.tsx
//
// Tabela densa "limpa" canônica — preenche o gap entre a <DataTable> (pesada,
// com toolbar/colunas/export/virtualização) e a <CompactSeriesTable> (específica
// de série temporal: períodos viram colunas). Para tabelas pequenas/médias de
// LEITURA — blocos de dossiê, fichas, breakdowns, séries simples (mês × valor).
//
// Visual: contêiner `rounded-md border`, header eyebrow (10px), linhas compactas
// (py-0.5), rodapé de reconciliação opcional. Só `tableTokens` — zero toolbar.
// Para listagem grande (sort/virtualização/export) use <DataTable>; para série
// transposta (períodos como colunas) use <CompactSeriesTable>.

"use client"

import * as React from "react"

import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

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
