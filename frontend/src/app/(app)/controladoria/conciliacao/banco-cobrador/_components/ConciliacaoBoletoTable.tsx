"use client"

/**
 * ConciliacaoBoletoTable — tabela titulo-a-titulo da conciliacao de boletos.
 *
 * Recebe as `linhas` ja filtradas pelo status (segmento ativo) e renderiza na
 * `DataTable` canonica (density compact, virtualiza >100 linhas). Colunas
 * unificadas com "—" onde nao se aplica (ex.: "So em banco" nao tem valor
 * BITFIN). Cells via `tableTokens` (regra dura §6). A coluna Status ajuda no
 * segmento "Todos"; nos demais e redundante (cheap).
 */

import * as React from "react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import { cx } from "@/lib/utils"
import { DataTable } from "@/design-system/components/DataTable"
import { Badge } from "@/components/tremor/Badge"
import { tableTokens } from "@/design-system/tokens/table"
import type {
  LinhaConciliacaoBoleto,
  StatusConciliacaoBoleto,
} from "@/lib/api-client"

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

function fmtDateBR(iso: string | null): string {
  if (!iso) return "—"
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  return m ? `${m[3]}/${m[2]}/${m[1].slice(2)}` : iso
}

const STATUS_META: Record<
  StatusConciliacaoBoleto,
  { label: string; variant: "success" | "error" | "warning" | "default" | "neutral" }
> = {
  conciliado:             { label: "Conciliado",  variant: "success" },
  divergencia_valor:      { label: "Dif. valor",  variant: "error" },
  divergencia_vencimento: { label: "Dif. venc.",  variant: "warning" },
  so_em_bitfin:           { label: "Só BITFIN",   variant: "default" },
  so_em_banco:            { label: "Só banco",    variant: "neutral" },
}

// ── Cells (via tableTokens) ─────────────────────────────────────────────────

function NumCell({ value }: { value: number | null }) {
  if (value === null) return <div className={cx("text-right", tableTokens.cellNumberSecondary)}>—</div>
  return <div className={cx("text-right", tableTokens.cellNumber)}>{fmtBRL.format(value)}</div>
}

function DateCell({ value }: { value: string | null }) {
  return <div className={cx("text-right", tableTokens.cellNumberSecondary)}>{fmtDateBR(value)}</div>
}

/** Diferenca contextual: valor (toned) quando ha; senao dias; senao "—". */
function DiffCell({ row }: { row: LinhaConciliacaoBoleto }) {
  if (row.diferenca_valor !== null && Math.abs(row.diferenca_valor) >= 0.005) {
    const positive = row.diferenca_valor > 0
    return (
      <div
        className={cx(
          "text-right text-xs font-semibold tabular-nums",
          positive ? "text-red-600 dark:text-red-400" : "text-amber-600 dark:text-amber-400",
        )}
      >
        {positive ? "+" : ""}
        {fmtBRL.format(row.diferenca_valor)}
      </div>
    )
  }
  if (row.diferenca_dias !== null && row.diferenca_dias !== 0) {
    return (
      <div className="text-right text-xs font-semibold tabular-nums text-amber-600 dark:text-amber-400">
        {row.diferenca_dias > 0 ? "+" : ""}
        {row.diferenca_dias}d
      </div>
    )
  }
  return <div className={cx("text-right", tableTokens.cellNumberSecondary)}>—</div>
}

const col = createColumnHelper<LinhaConciliacaoBoleto>()

const COLUMNS: ColumnDef<LinhaConciliacaoBoleto, unknown>[] = [
  col.accessor("status", {
    id: "status", header: "Status", size: 110,
    cell: (info) => {
      const m = STATUS_META[info.getValue<StatusConciliacaoBoleto>()]
      return <Badge variant={m.variant}>{m.label}</Badge>
    },
  }) as ColumnDef<LinhaConciliacaoBoleto, unknown>,
  col.accessor("numero", {
    id: "numero", header: "Número", size: 110,
    cell: (info) => (
      <span className={cx("block truncate font-mono", tableTokens.cellTextMono)}>
        {info.getValue<string>()}
      </span>
    ),
  }) as ColumnDef<LinhaConciliacaoBoleto, unknown>,
  col.accessor("produto", {
    id: "produto", header: "Produto", size: 80,
    cell: (info) => <span className={tableTokens.cellSecondary}>{info.getValue<string>() ?? "—"}</span>,
  }) as ColumnDef<LinhaConciliacaoBoleto, unknown>,
  col.accessor("banco", {
    id: "banco", header: "Banco", size: 100,
    cell: (info) => {
      const b = info.getValue<string>()
      return <span className={cx("capitalize", tableTokens.cellSecondary)}>{b ?? "—"}</span>
    },
  }) as ColumnDef<LinhaConciliacaoBoleto, unknown>,
  col.accessor("cedente_documento", {
    id: "cedente", header: "Cedente (CNPJ)", size: 140,
    cell: (info) => (
      <span className={cx("block truncate font-mono", tableTokens.cellSecondary)}>
        {info.getValue<string>() ?? "—"}
      </span>
    ),
  }) as ColumnDef<LinhaConciliacaoBoleto, unknown>,
  col.accessor("venc_bitfin", {
    id: "venc_bitfin", header: "Venc. BITFIN", size: 110, meta: { align: "right" },
    cell: (info) => <DateCell value={info.getValue<string | null>()} />,
  }) as ColumnDef<LinhaConciliacaoBoleto, unknown>,
  col.accessor("venc_banco", {
    id: "venc_banco", header: "Venc. banco", size: 110, meta: { align: "right" },
    cell: (info) => <DateCell value={info.getValue<string | null>()} />,
  }) as ColumnDef<LinhaConciliacaoBoleto, unknown>,
  col.accessor("valor_bitfin", {
    id: "valor_bitfin", header: "Valor BITFIN", size: 130, meta: { align: "right" },
    cell: (info) => <NumCell value={info.getValue<number | null>()} />,
  }) as ColumnDef<LinhaConciliacaoBoleto, unknown>,
  col.accessor("valor_banco", {
    id: "valor_banco", header: "Valor banco", size: 130, meta: { align: "right" },
    cell: (info) => <NumCell value={info.getValue<number | null>()} />,
  }) as ColumnDef<LinhaConciliacaoBoleto, unknown>,
  col.display({
    id: "diferenca", header: "Diferença", size: 120, meta: { align: "right" },
    cell: (info) => <DiffCell row={info.row.original} />,
  }) as ColumnDef<LinhaConciliacaoBoleto, unknown>,
]

export function ConciliacaoBoletoTable({ linhas }: { linhas: LinhaConciliacaoBoleto[] }) {
  return (
    <DataTable
      data={linhas}
      columns={COLUMNS}
      density="compact"
      showColumnManager={false}
      showDensityToggle={false}
      showExport={false}
      className="rounded border border-gray-200 dark:border-gray-800"
    />
  )
}
