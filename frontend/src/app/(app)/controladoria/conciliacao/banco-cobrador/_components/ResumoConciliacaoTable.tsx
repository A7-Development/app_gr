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
 * `tableTokens`. Sempre todos os status na ordem canonica (0 onde nao ha linha).
 * O `resumo` ja vem no escopo da UA selecionada (computado das linhas na pagina).
 */

import * as React from "react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import { cx } from "@/lib/utils"
import { Card } from "@/components/tremor/Card"
import { DataTable } from "@/design-system/components/DataTable"
import { tableTokens } from "@/design-system/tokens/table"
import type { ResumoStatusConciliacao, StatusConciliacaoBoleto } from "@/lib/api-client"
import { STATUS_BADGE_LABEL, STATUS_META, STATUS_ORDER } from "./status"

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

// Colunas compactas (layout 50/50 com os charts): a coluna "%" saiu — a
// proporcao agora e visual no donut ao lado. Mantem qtd + os 3 valores (R$),
// que reconciliam com o Total (footer) e com o detalhe (§14.6).
const COLUMNS: ColumnDef<ResumoStatusConciliacao, unknown>[] = [
  col.accessor("status", {
    id: "status", header: "Status", size: 150,
    // Badge canonico (tableTokens.badge + tone), sem icone, com o MESMO label
    // curto do detalhe (STATUS_BADGE_LABEL) — resumo e detalhe nao divergem
    // ("So BITFIN", nao "So em BITFIN").
    cell: (info) => {
      const s = info.getValue<StatusConciliacaoBoleto>()
      return (
        <span className={cx(tableTokens.badge, STATUS_META[s].tone)}>
          {STATUS_BADGE_LABEL[s]}
        </span>
      )
    },
  }) as ColumnDef<ResumoStatusConciliacao, unknown>,
  col.accessor("quantidade", {
    id: "quantidade", header: "Qtd", size: 60, meta: { align: "right" },
    cell: (info) => {
      const q = info.getValue<number>()
      return (
        <div className={cx("text-right", q > 0 ? tableTokens.cellNumber : tableTokens.cellNumberSecondary)}>
          {q > 0 ? fmtInt.format(q) : "—"}
        </div>
      )
    },
  }) as ColumnDef<ResumoStatusConciliacao, unknown>,
  col.accessor("valor_bitfin", {
    id: "valor_bitfin", header: "BITFIN (R$)", size: 120, meta: { align: "right" },
    cell: (info) => <div className="text-right">{brlOrDash(info.getValue<number>())}</div>,
  }) as ColumnDef<ResumoStatusConciliacao, unknown>,
  col.accessor("valor_banco", {
    id: "valor_banco", header: "Banco (R$)", size: 120, meta: { align: "right" },
    cell: (info) => <div className="text-right">{brlOrDash(info.getValue<number>())}</div>,
  }) as ColumnDef<ResumoStatusConciliacao, unknown>,
  col.accessor("diferenca", {
    id: "diferenca", header: "Dif. (R$)", size: 110, meta: { align: "right" },
    cell: (info) => <div className="text-right">{diffNode(info.getValue<number>())}</div>,
  }) as ColumnDef<ResumoStatusConciliacao, unknown>,
]

export function ResumoConciliacaoTable({
  resumo,
  statusFilter,
  onStatusToggle,
}: {
  resumo: ResumoStatusConciliacao[]
  /** Filtro Status ativo na pagina (valores canonicos do status). */
  statusFilter: string[]
  /** Clique na linha -> toggle do filtro Status da pagina (re-escopo total). */
  onStatusToggle: (status: StatusConciliacaoBoleto) => void
}) {
  // Sempre todas as linhas, ordem canonica (0 onde nao ha).
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
        <td className="px-3 py-1.5 text-right">{brlOrDash(total.valor_bitfin)}</td>
        <td className="px-3 py-1.5 text-right">{brlOrDash(total.valor_banco)}</td>
        <td className="px-3 py-1.5 text-right">{diffNode(total.diferenca)}</td>
      </tr>
    ),
    [total],
  )

  // Card padrao (tableTokens.cardWrapper) envolvendo a DataTable canonica —
  // mesma anatomy do DataTableShell, sem filtros/toolbar/title band.
  // Linha clicavel = toggle do filtro Status da pagina (re-escopo total: com
  // status filtrado o proprio resumo colapsa pro subset — clique de novo
  // desfaz; mesma mecanica do chip Status e das linhas de banco do card ao
  // lado). Linha selecionada destacada em azul (§4: blue = selecao).
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
        onRowClick={(row) => onStatusToggle(row.status)}
        rowClassName={(row) =>
          statusFilter.includes(row.status)
            ? "bg-blue-50 dark:bg-blue-500/10"
            : ""
        }
      />
    </Card>
  )
}
