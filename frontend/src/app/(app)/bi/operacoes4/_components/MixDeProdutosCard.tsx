// L2 direita do redesign /bi/operacoes4 (handoff 2026-05-21).
//
// Mix de produtos · MTD — visual identico ao TabelaCedentesMtd (operacoes3):
// <Card p-0> + cardTokens.header + DataTable canonico density="compact".
//
// 5 colunas + 1 footer:
//   1. Produto         (nome completo)
//   2. Share           (barra navy uniforme + percentual)
//   3. VOP MTD         (valor cheio via CurrencyCell)
//   4. Δ MoM           (pontos percentuais de share, colorido)
//   5. Taxa média      (% — MOCK PR1 ate backend expor)
//
// Footer (linha totalizadora):
//   - Produto:   "Total"
//   - Share:     ─ (sempre 100%, redundante)
//   - VOP MTD:   Σ current_value
//   - Δ MoM:     ΔVOP% = (VOPmtd - VOPprior) / VOPprior * 100
//                (nao soma_pp, que seria 0 em qualquer mix fechado)
//   - Taxa média: weighted avg ponderado por VOP MTD
//
// Botao "Drivers vs mes ant." no header e stub disabled em PR1 — abre
// drawer real em PR2. Decisao Ricardo 2026-05-21.

"use client"

import * as React from "react"
import type { ColumnDef } from "@tanstack/react-table"
import { RiArrowRightUpLine } from "@remixicon/react"

import { Card } from "@/components/tremor/Card"
import { CurrencyCell, DataTable } from "@/design-system/components"
import { cardTokens } from "@/design-system/tokens/card"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"
import type { Operacoes2DumbbellSeriesData } from "@/lib/api-client"

import { MOCK_TAXA_MEDIA_POR_PRODUTO } from "./_mocks"

// ── Formatters ──────────────────────────────────────────────────────────────

const fmtPct1 = (v: number) => `${v.toFixed(1).replace(".", ",")}%`
const fmtPct2 = (v: number) => `${v.toFixed(2).replace(".", ",")}%`

function fmtDeltaPP(v: number): string {
  const sign = v >= 0 ? "+" : "−"
  return `${sign}${Math.abs(v).toFixed(2).replace(".", ",")} pp`
}

function fmtDeltaPct(v: number): string {
  const sign = v >= 0 ? "+" : "−"
  return `${sign}${fmtPct1(Math.abs(v))}`
}

// ── Cells ───────────────────────────────────────────────────────────────────

function DeltaPPCell({ pp }: { pp: number }) {
  return (
    <span className={cx(
      "font-medium",
      pp >= 0 ? tableTokens.cellNumberPositive : tableTokens.cellNumberNegative,
    )}>
      {fmtDeltaPP(pp)}
    </span>
  )
}

function DeltaPctCell({ pct }: { pct: number | null }) {
  if (pct == null) {
    return <span className={cx(tableTokens.cellMuted, "tabular-nums")}>—</span>
  }
  return (
    <span className={cx(
      "font-medium",
      pct >= 0 ? tableTokens.cellNumberPositive : tableTokens.cellNumberNegative,
    )}>
      {fmtDeltaPct(pct)}
    </span>
  )
}

function ShareCell({ share }: { share: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 min-w-[40px] flex-1 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-900">
        <div
          className="h-full rounded-full bg-[#1B2B4B]"
          style={{ width: `${Math.min(100, share)}%` }}
        />
      </div>
      <span className={cx("w-[36px] text-right", tableTokens.cellNumber)}>
        {fmtPct1(share)}
      </span>
    </div>
  )
}

// ── Row shape ───────────────────────────────────────────────────────────────

type Row = {
  member_id: string
  member_label: string
  current_value: number
  current_share_pct: number
  delta_share_pp: number
  taxa: number | null
}

// ── Componente ──────────────────────────────────────────────────────────────

export function MixDeProdutosCard({
  mix,
}: {
  mix: Operacoes2DumbbellSeriesData
}) {
  // Ordena por current_value desc — ranking visual.
  const rows = React.useMemo<Row[]>(() => {
    return [...mix.points]
      .sort((a, b) => b.current_value - a.current_value)
      .map((p) => ({
        member_id: p.member_id,
        member_label: p.member_label,
        current_value: p.current_value,
        current_share_pct: p.current_share_pct,
        delta_share_pp: p.delta_share_pp,
        taxa: MOCK_TAXA_MEDIA_POR_PRODUTO[p.member_id] ?? null,
      }))
  }, [mix.points])

  // Totais agregados — calculados a partir do mix.points (nao do rows
  // filtrado, pra preservar agregado completo mesmo com filtros locais).
  const totals = React.useMemo(() => {
    let totalVop = 0
    let totalPriorVop = 0
    let taxaWeighted = 0
    let taxaWeight = 0
    for (const p of mix.points) {
      totalVop += p.current_value
      totalPriorVop += p.prior_value
      const taxa = MOCK_TAXA_MEDIA_POR_PRODUTO[p.member_id]
      if (taxa != null) {
        taxaWeighted += p.current_value * taxa
        taxaWeight += p.current_value
      }
    }
    return {
      totalVop,
      totalDeltaPct:
        totalPriorVop > 0
          ? ((totalVop - totalPriorVop) / totalPriorVop) * 100
          : null,
      taxaPonderada: taxaWeight > 0 ? taxaWeighted / taxaWeight : null,
    }
  }, [mix.points])

  const columns = React.useMemo<ColumnDef<Row, unknown>[]>(
    () => [
      {
        accessorKey: "member_label",
        header: "Produto",
        size: 200,
        cell: ({ row }) => (
          <div
            className={cx(tableTokens.cellText, "truncate")}
            title={row.original.member_label}
          >
            {row.original.member_label}
          </div>
        ),
      },
      {
        accessorKey: "current_share_pct",
        header: "Share",
        size: 150,
        cell: ({ row }) => <ShareCell share={row.original.current_share_pct} />,
      },
      {
        accessorKey: "current_value",
        header: () => <div className="text-right">VOP MTD</div>,
        size: 120,
        cell: ({ row }) => <CurrencyCell value={row.original.current_value} />,
      },
      {
        accessorKey: "delta_share_pp",
        header: () => <div className="text-right">Δ MoM</div>,
        size: 100,
        cell: ({ row }) => (
          <div className="text-right">
            <DeltaPPCell pp={row.original.delta_share_pp} />
          </div>
        ),
      },
      {
        accessorKey: "taxa",
        header: () => <div className="text-right">Taxa média</div>,
        size: 100,
        cell: ({ row }) => (
          <div className={cx(tableTokens.cellNumber, "text-right")}>
            {row.original.taxa != null ? fmtPct2(row.original.taxa) : "—"}
          </div>
        ),
      },
    ],
    [],
  )

  return (
    <Card className="flex flex-col p-0">
      <div
        className={cx(
          cardTokens.header,
          "flex items-start justify-between gap-3",
        )}
      >
        <div className="flex flex-col min-w-0">
          <h3 className={cardTokens.headerTitle}>Mix de produtos · MTD</h3>
          <p className={cx(cardTokens.headerSubtitle, "mt-0.5")}>
            Ranking por VOP MTD. Δ MoM e taxa média ponderada por produto.
          </p>
        </div>
        {/* Stub PR1: botao desabilitado. Wire em PR2 abrira DrillDrivers drawer. */}
        <button
          type="button"
          disabled
          title="Em breve — drill em PR2"
          className="inline-flex shrink-0 items-center gap-1 rounded-full border border-gray-200 bg-gray-50 px-2.5 py-0.5 text-[10.5px] font-medium uppercase tracking-wider text-gray-400 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-600"
        >
          <RiArrowRightUpLine className="size-3" aria-hidden />
          Drivers vs mês ant.
        </button>
      </div>

      <div className={cardTokens.body}>
        <DataTable
          data={rows}
          columns={columns}
          density="compact"
          showDensityToggle={false}
          showColumnManager={false}
          renderFooter={() => (
            <tr className="border-t-2 border-gray-200 bg-gray-50/40 font-semibold dark:border-gray-700 dark:bg-gray-900/30">
              <td className="px-3 py-2">
                <span className={cx(tableTokens.cellStrong)}>Total</span>
              </td>
              <td className="px-3 py-2">
                <span className={cx(tableTokens.cellMuted, "tabular-nums")}>
                  100,0%
                </span>
              </td>
              <td className="px-3 py-2 text-right">
                <CurrencyCell value={totals.totalVop} />
              </td>
              <td className="px-3 py-2 text-right">
                <DeltaPctCell pct={totals.totalDeltaPct} />
              </td>
              <td className="px-3 py-2 text-right">
                <span className={cx(tableTokens.cellNumber)}>
                  {totals.taxaPonderada != null
                    ? fmtPct2(totals.taxaPonderada)
                    : "—"}
                </span>
              </td>
            </tr>
          )}
        />
      </div>
    </Card>
  )
}
