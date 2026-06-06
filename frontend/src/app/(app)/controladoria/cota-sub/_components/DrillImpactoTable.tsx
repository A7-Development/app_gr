"use client"

/**
 * DrillImpactoTable — tabela canonica dos drills de "impacto na cota".
 *
 * Mesmo shape da tabela "Aplicações · impacto na cota" (DrillAplicacoesContent):
 * 5 colunas [Nome | Detalhe | D-1 | D0 | Impacto], DataTable density="ultra",
 * sem toolbar, container bordado, total no rodape somando as 3 colunas numericas.
 * Headers das colunas numericas e da 1a coluna sao configuraveis (semantica varia:
 * VLR/Saldo/Patrimonio, Rendimento/Δ/Impacto) — a ESTRUTURA e identica.
 *
 * Reusado por: Aplicações (referencia), Provisões de despesa (Contas a Pagar),
 * Cotas Prioritárias. Mantem as tabelas absolutamente alinhadas (§ consistencia).
 */

import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import { cx } from "@/lib/utils"
import { DataTable } from "@/design-system/components/DataTable"
import { tableTokens } from "@/design-system/tokens/table"
import { fmtBRL, fmtBRLSigned, toneClass } from "./drillKit"

export type DrillImpactoRow = {
  nome:     string
  detalhe:  string
  valor_d1: number
  valor_d0: number
  impacto:  number
}

export type DrillImpactoHeaders = {
  nome:    string
  d1:      string
  d0:      string
  impacto: string
}

// Props compartilhadas — ultra, sem toolbar, container bordado (igual Aplicações).
const DT_PROPS = {
  density:           "ultra",
  virtualize:        false,
  showColumnManager: false,
  showDensityToggle: false,
  showExport:        false,
  className:         "rounded border border-gray-200 dark:border-gray-800",
} as const

const FOOT_ROW = "border-t-2 border-t-gray-300 dark:border-t-gray-700"

const col = createColumnHelper<DrillImpactoRow>()

export function makeImpactoColumns(h: DrillImpactoHeaders): ColumnDef<DrillImpactoRow, unknown>[] {
  return [
    col.accessor("nome", {
      id: "nome", header: h.nome, size: 160,
      cell: (i) => {
        const v = i.getValue<string>()
        return <span className={cx("block truncate", tableTokens.cellText)} title={v}>{v}</span>
      },
    }),
    col.accessor("detalhe", {
      id: "detalhe", header: "Detalhe", size: 190,
      cell: (i) => {
        const v = i.getValue<string>()
        return <span className={cx("block truncate", tableTokens.cellSecondary)} title={v}>{v}</span>
      },
    }),
    col.accessor("valor_d1", {
      id: "valor_d1", header: h.d1, size: 120, meta: { align: "right" },
      cell: (i) => <div className={cx("text-right", tableTokens.cellNumberSecondary)}>{fmtBRL.format(i.getValue<number>())}</div>,
    }),
    col.accessor("valor_d0", {
      id: "valor_d0", header: h.d0, size: 120, meta: { align: "right" },
      cell: (i) => <div className={cx("text-right", tableTokens.cellNumber)}>{fmtBRL.format(i.getValue<number>())}</div>,
    }),
    col.accessor("impacto", {
      id: "impacto", header: h.impacto, size: 130, meta: { align: "right" },
      cell: (i) => {
        const v = i.getValue<number>()
        return <div className={cx("text-right text-xs font-semibold tabular-nums", toneClass(v))}>{fmtBRLSigned(v)}</div>
      },
    }),
  ] as ColumnDef<DrillImpactoRow, unknown>[]
}

export function DrillImpactoTable({
  columns, itens,
}: {
  columns: ColumnDef<DrillImpactoRow, unknown>[]
  itens:   DrillImpactoRow[]
}) {
  const renderFooter = () => {
    const s1 = itens.reduce((a, x) => a + x.valor_d1, 0)
    const s0 = itens.reduce((a, x) => a + x.valor_d0, 0)
    const sd = itens.reduce((a, x) => a + x.impacto, 0)
    return (
      <tr className={FOOT_ROW}>
        <td colSpan={2} className="px-3"><span className={tableTokens.cellStrong}>Total ({itens.length})</span></td>
        <td className="px-3"><div className={cx("text-right tabular-nums", tableTokens.cellNumberSecondary)}>{fmtBRL.format(s1)}</div></td>
        <td className="px-3"><div className={cx("text-right tabular-nums", tableTokens.cellStrong)}>{fmtBRL.format(s0)}</div></td>
        <td className="px-3"><div className={cx("text-right text-xs font-semibold tabular-nums", toneClass(sd))}>{fmtBRLSigned(sd)}</div></td>
      </tr>
    )
  }
  return <DataTable<DrillImpactoRow> {...DT_PROPS} columns={columns} data={itens} renderFooter={renderFooter} />
}
