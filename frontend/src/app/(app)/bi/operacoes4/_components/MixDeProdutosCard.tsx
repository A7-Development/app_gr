// L2 direita do redesign /bi/operacoes4 (handoff 2026-05-21).
//
// Mix de produtos · MTD — 5 colunas:
//   1. Produto         (nome completo, sem dot colorido)
//   2. Share           (barra navy uniforme + percentual)
//   3. VOP MTD         (valor cheio sem abreviação)
//   4. Δ MoM           (delta em pp, colorido)
//   5. Taxa média      (% — MOCK PR1 ate backend expor)
//
// Botao "Drivers vs mes ant." no header e stub disabled em PR1 — abre
// drawer real em PR2. Decisao Ricardo 2026-05-21.

"use client"

import * as React from "react"
import { RiArrowRightUpLine } from "@remixicon/react"

import { Card } from "@/components/tremor/Card"
import { cardTokens } from "@/design-system/tokens/card"
import { cx } from "@/lib/utils"
import type { Operacoes2DumbbellSeriesData } from "@/lib/api-client"

import { MOCK_TAXA_MEDIA_POR_PRODUTO } from "./_mocks"

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
})

function fmtDeltaPP(v: number): string {
  const sign = v >= 0 ? "+" : "−"
  return `${sign}${Math.abs(v).toFixed(2).replace(".", ",")} pp`
}

function fmtPct(v: number): string {
  return `${v.toFixed(2).replace(".", ",")}%`
}

export function MixDeProdutosCard({
  mix,
}: {
  mix: Operacoes2DumbbellSeriesData
}) {
  // Ordena por current_value desc — ranking visual.
  const rows = React.useMemo(
    () => [...mix.points].sort((a, b) => b.current_value - a.current_value),
    [mix.points],
  )

  return (
    <Card className={cardTokens.body}>
      <header className="flex items-start justify-between gap-3 pb-3">
        <div className="min-w-0">
          <div className="text-[10.5px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
            Mix de produtos · MTD
          </div>
          <p className="mt-1 text-[12px] text-gray-500 dark:text-gray-400">
            Ranking por VOP MTD. Δ MoM e taxa média ponderada por produto.
          </p>
        </div>
        {/* Stub PR1: botao desabilitado. Wire em PR2 abrirá DrillDrivers drawer. */}
        <button
          type="button"
          disabled
          title="Em breve — drill em PR2"
          className="inline-flex shrink-0 items-center gap-1 rounded-full border border-gray-200 bg-gray-50 px-2.5 py-0.5 text-[10.5px] font-medium uppercase tracking-wider text-gray-400 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-600"
        >
          <RiArrowRightUpLine className="size-3" aria-hidden />
          Drivers vs mês ant.
        </button>
      </header>

      <div className="overflow-x-auto">
        <table className="w-full table-auto text-[12px]">
          <thead>
            <tr className="border-b border-gray-100 text-[10px] uppercase tracking-wider text-gray-500 dark:border-gray-900 dark:text-gray-400">
              <th className="py-1.5 pr-3 text-left font-medium">Produto</th>
              <th className="py-1.5 pr-3 text-left font-medium">Share</th>
              <th className="py-1.5 pr-3 text-right font-medium">VOP MTD</th>
              <th className="py-1.5 pr-3 text-right font-medium">Δ MoM</th>
              <th className="py-1.5 text-right font-medium">Taxa média</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const share = p.current_share_pct
              const deltaPP = p.delta_share_pp
              // MOCK_PR3: taxa media ponderada por produto — backend ainda nao expoe.
              const taxa = MOCK_TAXA_MEDIA_POR_PRODUTO[p.member_id]
              return (
                <tr
                  key={p.member_id}
                  className="border-b border-gray-50 last:border-b-0 dark:border-gray-900/60"
                >
                  <td className="py-1.5 pr-3 font-medium text-gray-900 dark:text-gray-100">
                    {p.member_label}
                  </td>
                  <td className="py-1.5 pr-3">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 min-w-[40px] flex-1 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-900">
                        <div
                          className="h-full rounded-full bg-[#1B2B4B]"
                          style={{ width: `${Math.min(100, share)}%` }}
                        />
                      </div>
                      <span className="w-[34px] text-right tabular-nums text-gray-700 dark:text-gray-300">
                        {share.toFixed(1).replace(".", ",")}%
                      </span>
                    </div>
                  </td>
                  <td className="py-1.5 pr-3 text-right tabular-nums text-gray-900 dark:text-gray-100">
                    {fmtBRL.format(p.current_value)}
                  </td>
                  <td
                    className={cx(
                      "py-1.5 pr-3 text-right tabular-nums",
                      deltaPP >= 0
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-red-600 dark:text-red-400",
                    )}
                  >
                    {fmtDeltaPP(deltaPP)}
                  </td>
                  <td className="py-1.5 text-right tabular-nums text-gray-900 dark:text-gray-100">
                    {taxa != null ? fmtPct(taxa) : "—"}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
