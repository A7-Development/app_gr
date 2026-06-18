"use client"

//
// ConcentracaoCard — card de ranking Top-10 (cedentes ou sacados).
// Tabela canonica (DataTable, toolbar off) + linha "10 maiores" no footer
// que reconcilia o total (§14.6). Cells via tableTokens (§6).
//

import * as React from "react"
import { type ColumnDef } from "@tanstack/react-table"

import { Card } from "@/components/tremor/Card"
import { DataTable } from "@/design-system/components/DataTable"
import { cardTokens } from "@/design-system/tokens/card"
import { tableTokens } from "@/design-system/tokens/table"
import type { ConcentracaoItem, ConcentracaoTabela } from "@/lib/api-client"
import { cx } from "@/lib/utils"

const fmtNum = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 })
const fmtPct = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})

export function ConcentracaoCard({
  titulo,
  eyebrow,
  posicao,
  tabela,
  loading,
}: {
  titulo: string
  eyebrow: string
  posicao: string
  tabela: ConcentracaoTabela | undefined
  loading: boolean
}) {
  const columns = React.useMemo<ColumnDef<ConcentracaoItem, unknown>[]>(
    () => [
      {
        accessorKey: "nome",
        header: eyebrow,
        cell: ({ row }) => (
          <span className={cx(tableTokens.cellText, "block truncate")}>
            {row.original.nome}
          </span>
        ),
      },
      {
        accessorKey: "financeiro",
        header: () => <div className="text-right">Financeiro</div>,
        cell: ({ row }) => (
          <div className={cx(tableTokens.cellNumber, "text-right")}>
            {fmtNum.format(row.original.financeiro)}
          </div>
        ),
      },
      {
        accessorKey: "pct_pl",
        header: () => <div className="text-right">% PL</div>,
        cell: ({ row }) => (
          <div className={cx(tableTokens.cellNumber, "text-right")}>
            {fmtPct.format(row.original.pct_pl)}
          </div>
        ),
      },
    ],
    [eyebrow],
  )

  const renderFooter = React.useCallback(() => {
    if (!tabela) return null
    return (
      <>
        <tr className="border-t border-t-gray-200 dark:border-t-gray-800">
          <td className="px-3 py-2.5">
            <span className={tableTokens.cellStrong}>10 maiores</span>
          </td>
          <td className="px-3 py-2.5 text-right">
            <span className={cx(tableTokens.cellStrong, "tabular-nums")}>
              {fmtNum.format(tabela.total_financeiro)}
            </span>
          </td>
          <td className="px-3 py-2.5 text-right">
            <span className={cx(tableTokens.cellStrong, "tabular-nums")}>
              {fmtPct.format(tabela.total_pct_pl)}
            </span>
          </td>
        </tr>
        <tr>
          <td className="px-3 py-2">
            <span className={tableTokens.cellSecondary}>
              Outros ({fmtNum.format(tabela.outros_qtd)})
            </span>
          </td>
          <td className="px-3 py-2 text-right">
            <span className={cx(tableTokens.cellNumberSecondary)}>
              {fmtNum.format(tabela.outros_financeiro)}
            </span>
          </td>
          <td className="px-3 py-2 text-right">
            <span className={cx(tableTokens.cellNumberSecondary)}>
              {fmtPct.format(tabela.outros_pct_pl)}
            </span>
          </td>
        </tr>
      </>
    )
  }, [tabela])

  return (
    <Card className="p-0">
      <div className={cx(cardTokens.header, "flex items-baseline gap-2")}>
        <h3 className="text-[15px] font-semibold text-gray-900 dark:text-gray-50">
          {titulo}
        </h3>
        <span className="text-[12px] text-gray-500 dark:text-gray-400">
          10 maiores · {posicao}
        </span>
      </div>
      <DataTable<ConcentracaoItem>
        data={tabela?.itens ?? []}
        columns={columns}
        density="compact"
        loading={loading}
        showDensityToggle={false}
        showColumnManager={false}
        showExport={false}
        renderFooter={renderFooter}
      />
    </Card>
  )
}
