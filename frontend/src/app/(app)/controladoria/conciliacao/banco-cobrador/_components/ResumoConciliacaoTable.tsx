"use client"

/**
 * ResumoConciliacaoTable — tabela-resumo do confronto (Entrega 3, §2: "Resumo
 * consolidado por status: quantidade, percentual, valor BITFIN, valor banco e
 * diferenca"). Substitui o KpiStrip no topo da pagina.
 *
 * CANONICO, sem invencoes: `<DataTable>` padrao do projeto envolta no `<Card>`
 * padrao (`tableTokens.cardWrapper`). Sem filtros nem toolbar (column manager /
 * density / export off). Total via `renderFooter` (prop canonica da DataTable)
 * — reconcilia on-screen (§14.6): soma das 5 linhas = Total. Cells via
 * `tableTokens`. Sempre os 5 status na ordem canonica (0 onde nao ha linha).
 * O `resumo` ja vem no escopo da UA selecionada (computado das linhas na pagina).
 */

import * as React from "react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import { cx } from "@/lib/utils"
import { Card } from "@/components/tremor/Card"
import { DataTable } from "@/design-system/components/DataTable"
import { tableTokens } from "@/design-system/tokens/table"
import type { ResumoStatusConciliacao, StatusConciliacaoBoleto } from "@/lib/api-client"
import { STATUS_META, STATUS_ORDER } from "./status"

const fmtInt = new Intl.NumberFormat("pt-BR")
const fmtBRL = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

function brlOrDash(v: number) {
  if (Math.abs(v) < 0.005) return <span className={tableTokens.cellNumberSecondary}>—</span>
  return <span className={tableTokens.cellNumber}>{fmtBRL.format(v)}</span>
}

function diffNode(v: number) {
  if (Math.abs(v) < 0.005) return <span className={tableTokens.cellNumberSecondary}>—</span>
  return (
    <span className={tableTokens.cellNumberNegative}>
      {v > 0 ? "+" : ""}
      {fmtBRL.format(v)}
    </span>
  )
}

const col = createColumnHelper<ResumoStatusConciliacao>()

const COLUMNS: ColumnDef<ResumoStatusConciliacao, unknown>[] = [
  col.accessor("status", {
    id: "status", header: "Status", size: 220,
    cell: (info) => {
      const s = info.getValue<StatusConciliacaoBoleto>()
      const m = STATUS_META[s]
      const Icon = m.icon
      return (
        <span className="inline-flex items-center gap-1.5">
          <Icon className={cx("size-4 shrink-0", m.iconTone)} aria-hidden="true" />
          <span className={cx("font-medium", m.textTone)}>{m.label}</span>
        </span>
      )
    },
  }) as ColumnDef<ResumoStatusConciliacao, unknown>,
  col.accessor("quantidade", {
    id: "quantidade", header: "Qtd", size: 80, meta: { align: "right" },
    cell: (info) => {
      const q = info.getValue<number>()
      return (
        <div className={cx("text-right", q > 0 ? tableTokens.cellNumber : tableTokens.cellNumberSecondary)}>
          {q > 0 ? fmtInt.format(q) : "—"}
        </div>
      )
    },
  }) as ColumnDef<ResumoStatusConciliacao, unknown>,
  col.accessor("percentual", {
    id: "percentual", header: "%", size: 70, meta: { align: "right" },
    cell: (info) => {
      const p = info.getValue<number>()
      return (
        <div className={cx("text-right", tableTokens.cellNumberSecondary)}>
          {p > 0 ? `${p.toFixed(1)}%` : "—"}
        </div>
      )
    },
  }) as ColumnDef<ResumoStatusConciliacao, unknown>,
  col.accessor("valor_bitfin", {
    id: "valor_bitfin", header: "Valor BITFIN (R$)", size: 150, meta: { align: "right" },
    cell: (info) => <div className="text-right">{brlOrDash(info.getValue<number>())}</div>,
  }) as ColumnDef<ResumoStatusConciliacao, unknown>,
  col.accessor("valor_banco", {
    id: "valor_banco", header: "Valor banco (R$)", size: 150, meta: { align: "right" },
    cell: (info) => <div className="text-right">{brlOrDash(info.getValue<number>())}</div>,
  }) as ColumnDef<ResumoStatusConciliacao, unknown>,
  col.accessor("diferenca", {
    id: "diferenca", header: "Diferença (R$)", size: 140, meta: { align: "right" },
    cell: (info) => <div className="text-right">{diffNode(info.getValue<number>())}</div>,
  }) as ColumnDef<ResumoStatusConciliacao, unknown>,
]

export function ResumoConciliacaoTable({
  resumo,
}: {
  resumo: ResumoStatusConciliacao[]
}) {
  // Sempre as 5 linhas, ordem canonica (0 onde nao ha).
  const rows = React.useMemo<ResumoStatusConciliacao[]>(() => {
    const by = new Map(resumo.map((r) => [r.status, r]))
    return STATUS_ORDER.map(
      (s) =>
        by.get(s) ?? {
          status: s,
          quantidade: 0,
          percentual: 0,
          valor_bitfin: 0,
          valor_banco: 0,
          diferenca: 0,
        },
    )
  }, [resumo])

  const total = React.useMemo(
    () =>
      rows.reduce(
        (a, r) => ({
          quantidade: a.quantidade + r.quantidade,
          valor_bitfin: a.valor_bitfin + r.valor_bitfin,
          valor_banco: a.valor_banco + r.valor_banco,
          diferenca: a.diferenca + r.diferenca,
        }),
        { quantidade: 0, valor_bitfin: 0, valor_banco: 0, diferenca: 0 },
      ),
    [rows],
  )

  const renderFooter = React.useCallback(
    () => (
      <tr className="border-t-2 border-gray-200 dark:border-gray-700">
        <td className={cx("px-3 py-1.5", tableTokens.cellStrong)}>Total</td>
        <td className={cx("px-3 py-1.5 text-right font-semibold", tableTokens.cellNumber)}>
          {fmtInt.format(total.quantidade)}
        </td>
        <td className={cx("px-3 py-1.5 text-right", tableTokens.cellNumberSecondary)}>
          {total.quantidade > 0 ? "100,0%" : "—"}
        </td>
        <td className="px-3 py-1.5 text-right">{brlOrDash(total.valor_bitfin)}</td>
        <td className="px-3 py-1.5 text-right">{brlOrDash(total.valor_banco)}</td>
        <td className="px-3 py-1.5 text-right">{diffNode(total.diferenca)}</td>
      </tr>
    ),
    [total],
  )

  // Card padrao (tableTokens.cardWrapper) envolvendo a DataTable canonica —
  // mesma anatomy do DataTableShell, sem filtros/toolbar/title band.
  return (
    <Card className={tableTokens.cardWrapper}>
      <DataTable
        data={rows}
        columns={COLUMNS}
        density="compact"
        showColumnManager={false}
        showDensityToggle={false}
        showExport={false}
        virtualize={false}
        renderFooter={renderFooter}
      />
    </Card>
  )
}
