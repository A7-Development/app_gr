"use client"

/**
 * ConciliacaoBoletoTable — tabela titulo-a-titulo da conciliacao de boletos.
 *
 * Recebe as `linhas` ja filtradas pelos chips globais (status/banco/produto/
 * cedente) e renderiza na `DataTable` CANONICA de listagem (density ULTRA +
 * toolbar completa: column manager, density toggle, export CSV; virtualiza >100
 * linhas). A busca por palavra mora na MESMA linha da toolbar (Exportar/colunas/
 * densidade), via slot `toolbarStart` da DataTable — alimenta o globalFilter do
 * TanStack. Colunas unificadas com "—" onde nao se aplica (ex.: "So em banco"
 * nao tem valor BITFIN). Cells via `tableTokens` (regra dura §6).
 */

import * as React from "react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import { cx } from "@/lib/utils"
import { DataTable } from "@/design-system/components/DataTable"
import { FilterSearch } from "@/design-system/components/FilterBar"
import { tableTokens } from "@/design-system/tokens/table"
import type {
  LinhaConciliacaoBoleto,
  StatusConciliacaoBoleto,
} from "@/lib/api-client"
import { STATUS_BADGE_LABEL, STATUS_META } from "./status"

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
    id: "status", header: "Status", size: 92,
    cell: (info) => {
      const s = info.getValue<StatusConciliacaoBoleto>()
      return <span className={cx(tableTokens.badge, STATUS_META[s].tone)}>{STATUS_BADGE_LABEL[s]}</span>
    },
  }) as ColumnDef<LinhaConciliacaoBoleto, unknown>,
  col.accessor("data_operacao", {
    id: "data_operacao", header: "Data operação", size: 104,
    cell: (info) => (
      <span className={cx("tabular-nums", tableTokens.cellSecondary)}>
        {fmtDateBR(info.getValue<string | null>())}
      </span>
    ),
  }) as ColumnDef<LinhaConciliacaoBoleto, unknown>,
  col.accessor("numero", {
    id: "numero", header: "Nº documento", size: 120,
    cell: (info) => (
      <span className={cx("block truncate font-mono", tableTokens.cellTextMono)}>
        {info.getValue<string>()}
      </span>
    ),
  }) as ColumnDef<LinhaConciliacaoBoleto, unknown>,
  col.accessor("nosso_numero", {
    id: "nosso_numero", header: "Nº no banco", size: 110,
    cell: (info) => {
      const v = info.getValue<string | null>()
      return (
        <span className={cx("block truncate font-mono", tableTokens.cellTextMono)}>
          {v ?? "—"}
        </span>
      )
    },
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
  col.accessor("cedente_nome", {
    id: "cedente", header: "Cedente", size: 200,
    // MOTIVO: largura fixa + truncate (sem quebra). Nome do cedente pode ser
    // longo; max-w constante mantem a coluna estavel, tooltip mostra o full.
    cell: (info) => {
      const v = info.getValue<string | null>()
      return (
        <span
          className={cx("block max-w-[200px] truncate", tableTokens.cellText)}
          title={v ?? undefined}
        >
          {v ?? "—"}
        </span>
      )
    },
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

function exportarCsv(rows: LinhaConciliacaoBoleto[]) {
  const head = [
    "Status", "Data operacao", "Nro documento", "Nro no banco", "Produto", "Banco", "Cedente",
    "Venc BITFIN", "Venc banco", "Valor BITFIN", "Valor banco", "Dif valor", "Dif dias",
  ]
  const esc = (v: string | number | null | undefined) => {
    const s = v === null || v === undefined ? "" : String(v)
    return /[";\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const corpo = rows.map((r) =>
    [
      STATUS_META[r.status]?.label ?? r.status,  // label longo no CSV
      r.data_operacao ?? "",
      r.numero, r.nosso_numero ?? "", r.produto ?? "", r.banco ?? "", r.cedente_nome ?? "",
      r.venc_bitfin ?? "", r.venc_banco ?? "",
      r.valor_bitfin ?? "", r.valor_banco ?? "",
      r.diferenca_valor ?? "", r.diferenca_dias ?? "",
    ].map(esc).join(";"),
  )
  const csv = [head.join(";"), ...corpo].join("\n")
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = "conciliacao-boletos.csv"
  a.click()
  URL.revokeObjectURL(url)
}

export function ConciliacaoBoletoTable({
  linhas,
}: {
  linhas: LinhaConciliacaoBoleto[]
}) {
  // Busca por palavra mora DENTRO do card (acima da coluna Status), alimentando
  // o globalFilter do TanStack — separada dos chips globais da pagina.
  const [busca, setBusca] = React.useState("")

  return (
    <div className="flex flex-col overflow-hidden rounded border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950">
      <DataTable
        data={linhas}
        columns={COLUMNS}
        density="ultra"
        showColumnManager
        showDensityToggle
        showExport
        globalFilter={busca}
        onExport={(_format, rows) => exportarCsv(rows)}
        toolbarStart={
          <FilterSearch
            placeholder="Buscar número, produto, cedente…"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            onClear={() => setBusca("")}
          />
        }
      />
    </div>
  )
}
