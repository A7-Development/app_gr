"use client"

/**
 * PagamentosDiaPanel — Card listando pagamentos efetivados em D0.
 *
 * Mesmo padrao visual da BalanceTable (Card + header inline + DataTable
 * canonica). Le do endpoint GET /controladoria/cota-sub/variacoes-dia mas
 * exibe APENAS a zona `pagamentos` (saidas de caixa em D0 que casam com
 * provisoes previas do CPR).
 *
 * Apropriacoes, anomalias e conferencia foram retiradas — esse painel
 * tem foco unico: ver quais despesas/baixas sairam do caixa no dia.
 *
 * Backend: silver only (CLAUDE.md §13.2.1) via wh_movimento_caixa cruzado
 * com wh_cpr_movimento (D-1 vs D0) para classificar.
 */

import * as React from "react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import { cx } from "@/lib/utils"
import { Card } from "@/components/tremor/Card"
import { DataTable } from "@/design-system/components/DataTable"
import { tableTokens } from "@/design-system/tokens/table"
import type { VariacaoItem, VariacoesDiaResponse } from "@/lib/api-client"

// ─────────────────────────────────────────────────────────────────────────────
// Formatters
// ─────────────────────────────────────────────────────────────────────────────

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

function formatValor(v: number): string {
  if (v === 0) return "—"
  return fmtBRL.format(v)
}

/** ISO yyyy-MM-dd → "DD/MM/YY". */
function fmtDateShort(iso?: string): string {
  if (!iso) return ""
  const [y, m, d] = iso.split("-")
  if (!y || !m || !d) return iso
  return `${d}/${m}/${y.slice(2)}`
}

// ─────────────────────────────────────────────────────────────────────────────
// Cell renderers — mesmo padrao do BalanceTable / VariacoesDiaPanel
// ─────────────────────────────────────────────────────────────────────────────

function DescricaoCell({ value }: { value: string | null }) {
  if (!value) return null
  return (
    <span
      title={value}
      className={cx("block max-w-full truncate whitespace-nowrap", tableTokens.cellSecondary)}
    >
      {value}
    </span>
  )
}

function LabelCell({ value }: { value: string }) {
  return (
    <span
      title={value}
      className={cx("block max-w-full truncate whitespace-nowrap", tableTokens.cellText)}
    >
      {value}
    </span>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Colunas — Pagamentos
// ─────────────────────────────────────────────────────────────────────────────

const col = createColumnHelper<VariacaoItem>()

const COLUMNS: ColumnDef<VariacaoItem, unknown>[] = [
  col.accessor("label", {
    header: "Histórico",
    size: 320,
    cell: (info) => <LabelCell value={info.getValue<string>()} />,
  }) as ColumnDef<VariacaoItem, unknown>,
  col.accessor("descricao", {
    header: "Descrição",
    size: 360,
    cell: (info) => <DescricaoCell value={info.getValue<string | null>()} />,
  }) as ColumnDef<VariacaoItem, unknown>,
  col.accessor("valor", {
    header: "Saída",
    meta:   { align: "right" },
    size: 140,
    cell: (info) => (
      <div
        style={{ textAlign: "right" }}
        className={cx("font-medium", tableTokens.cellNumber)}
      >
        −{formatValor(info.getValue<number>())}
      </div>
    ),
  }) as ColumnDef<VariacaoItem, unknown>,
]

// ─────────────────────────────────────────────────────────────────────────────
// Componente
// ─────────────────────────────────────────────────────────────────────────────

export function PagamentosDiaPanel({
  variacoes,
  loading,
  error,
}: {
  variacoes: VariacoesDiaResponse | undefined
  loading?:  boolean
  error?:    Error | null
}) {
  if (loading) {
    return (
      <Card className="p-6 text-center text-sm text-gray-500 dark:text-gray-400">
        Carregando pagamentos do dia...
      </Card>
    )
  }
  if (error) {
    return (
      <Card className="border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">
        Erro ao carregar pagamentos: {error.message}
      </Card>
    )
  }
  if (!variacoes) return null

  const headerSub = variacoes.data ? fmtDateShort(variacoes.data) : ""
  const total = variacoes.pagamentos_total

  return (
    // Card Tremor com p-3 + gap-3 — mesmo padrao da BalanceTable.
    <Card className="flex flex-col gap-3 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-baseline gap-2">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
            Pagamentos do Dia
          </h3>
          {headerSub && (
            <span className="text-[11px] text-gray-500 dark:text-gray-400">
              {headerSub}
            </span>
          )}
        </div>
        <span className={cx(
          "text-sm font-semibold tabular-nums",
          "text-gray-700 dark:text-gray-300",
        )}>
          Total: −{formatValor(total)}
        </span>
      </div>

      <DataTable
        data={variacoes.pagamentos}
        columns={COLUMNS}
        density="compact"
        showColumnManager={false}
        showDensityToggle={false}
        showExport={false}
        virtualize={false}
        renderEmpty={() => (
          <div className="py-8 text-center text-sm text-gray-500 dark:text-gray-400">
            Nenhum pagamento efetivado no dia.
          </div>
        )}
      />
    </Card>
  )
}
