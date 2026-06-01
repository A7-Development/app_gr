"use client"

/**
 * DreBreakdownTable — receita de UM mes aberta por uma dimensao
 * (natureza / cedente / produto / subgrupo).
 *
 * Tabela plana canonica (DataTable). Colunas: Linha · Receita · % · Resultado.
 * Ordenada por receita desc (vem ordenada do backend). Click numa linha
 * dispara `onRowClick` (drill — cruzar dimensoes).
 *
 * Backend: GET /controladoria/dre/breakdown (DreBreakdownResponse).
 */

import * as React from "react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import { cx } from "@/lib/utils"
import { DataTable } from "@/design-system/components/DataTable"
import { tableTokens } from "@/design-system/tokens/table"
import type { DreBreakdownResponse, DreBreakdownRow } from "@/lib/api-client"

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
})
const fmtPct = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})

type Row = DreBreakdownRow & { pct: number }

const col = createColumnHelper<Row>()

const COLUMNS: ColumnDef<Row, unknown>[] = [
  col.accessor("label", {
    id: "label",
    header: "Linha",
    size: 300,
    cell: (info) => (
      <span
        title={info.getValue<string>()}
        className={cx("block max-w-full truncate whitespace-nowrap", tableTokens.cellText)}
      >
        {info.getValue<string>()}
      </span>
    ),
  }) as ColumnDef<Row, unknown>,
  col.accessor("receita", {
    id: "receita",
    header: () => <span className="block text-right">Receita</span>,
    size: 130,
    meta: { align: "right" },
    cell: (info) => (
      <div className={cx("text-right", tableTokens.cellNumber)}>
        {fmtBRL.format(info.getValue<number>())}
      </div>
    ),
  }) as ColumnDef<Row, unknown>,
  col.accessor("pct", {
    id: "pct",
    header: () => <span className="block text-right">%</span>,
    size: 70,
    meta: { align: "right" },
    cell: (info) => (
      <div className={cx("text-right", tableTokens.cellNumberSecondary)}>
        {fmtPct.format(info.getValue<number>())}%
      </div>
    ),
  }) as ColumnDef<Row, unknown>,
  col.accessor("resultado", {
    id: "resultado",
    header: () => <span className="block text-right">Resultado</span>,
    size: 130,
    meta: { align: "right" },
    cell: (info) => {
      const v = info.getValue<number>()
      return (
        <div
          className={cx(
            "text-right",
            v >= 0 ? tableTokens.cellNumber : tableTokens.cellNumberNegative,
          )}
        >
          {fmtBRL.format(v)}
        </div>
      )
    },
  }) as ColumnDef<Row, unknown>,
]

export function DreBreakdownTable({
  data,
  loading,
  onRowClick,
}: {
  data?: DreBreakdownResponse
  loading?: boolean
  onRowClick?: (row: Row) => void
}) {
  const rows = React.useMemo<Row[]>(() => {
    if (!data) return []
    const total = data.totalReceita || 1
    return data.linhas.map((l) => ({ ...l, pct: (l.receita / total) * 100 }))
  }, [data])

  return (
    <DataTable
      data={rows}
      columns={COLUMNS}
      density="compact"
      showColumnManager={false}
      showDensityToggle={false}
      showExport={false}
      virtualize={false}
      onRowClick={onRowClick}
      renderEmpty={() => (
        <div className="flex flex-col items-center justify-center gap-1 py-12 text-center">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {loading ? "Carregando..." : "Sem receita no mes selecionado"}
          </p>
        </div>
      )}
    />
  )
}
