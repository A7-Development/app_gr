// src/app/(app)/bi/operacoes4/_components/DailyTable.tsx
//
// L7 — Tabela narrativa diaria do mes corrente. 1 linha por DU com VOP,
// Receita, Yield, Δ vs paridade DU e flag de outlier (P5/P95 do MTD OU
// |Δ DU-par| > 50%).
//
// Consome `/bi/operacoes4/diaria` (PR3b backend). Tabela usa o pattern
// tabular do CompactSeriesTable mas mantemos a marcacao simples HTML
// porque os dados nao sao serie temporal multi-coluna — sao linhas
// independentes por DU.

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { RiAlertLine } from "@remixicon/react"

import { Card } from "@/components/tremor/Card"
import { cardTokens } from "@/design-system/tokens/card"
import { cx } from "@/lib/utils"
import { biOperacoes4 } from "@/lib/api-client"
import type { BIFilters } from "@/lib/api-client"

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 1,
})

function fmtDataPt(iso: string): string {
  const [, m, d] = iso.split("-").map(Number)
  if (!m || !d) return iso
  const mesAbrev = [
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez",
  ][m - 1]
  return `${String(d).padStart(2, "0")}/${mesAbrev}`
}

function fmtYield(v: number | null): string {
  if (v === null) return "—"
  return `${v.toFixed(2).replace(".", ",")}%`
}

function fmtDelta(v: number | null): string {
  if (v === null) return "—"
  const sign = v > 0 ? "+" : ""
  return `${sign}${v.toFixed(1).replace(".", ",")}%`
}

export function DailyTable({
  filters,
  onRowClick,
}: {
  filters: BIFilters
  /** Click na linha — recebe a data ISO YYYY-MM-DD do DU. */
  onRowClick?: (dataISO: string) => void
}) {
  const q = useQuery({
    queryKey: ["bi", "operacoes4", "diaria", filters],
    queryFn: () => biOperacoes4.diaria(filters),
  })

  const data = q.data?.data
  const loading = q.isLoading
  const error = q.isError ? "Falha ao carregar tabela diária." : null

  return (
    <Card className={cx(cardTokens.body)}>
      <div className="mb-3">
        <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
          Tabela narrativa diária
        </p>
        <p className="mt-1.5 text-xs text-gray-500 dark:text-gray-400">
          1 linha por DU. ⚠ marca dia fora da curva (P5/P95 do MTD ou
          |Δ paridade DU| &gt; 50%).
        </p>
      </div>

      {loading && (
        <div
          className="h-48 animate-pulse rounded bg-gray-100 dark:bg-gray-800"
          aria-busy="true"
        />
      )}
      {error && (
        <p className="py-6 text-center text-xs text-gray-500 dark:text-gray-400">
          {error}
        </p>
      )}
      {!loading && !error && data?.pontos.length === 0 && (
        <p className="py-6 text-center text-xs text-gray-500 dark:text-gray-400">
          Aguardando primeiro DU útil do mês.
        </p>
      )}
      {data && data.pontos.length > 0 && (
        <table className="w-full text-left text-[12px] tabular-nums">
          <thead>
            <tr className="border-b border-gray-200 text-[10.5px] uppercase tracking-wider text-gray-500 dark:border-gray-800 dark:text-gray-400">
              <th className="py-1.5 pr-2 font-medium">DU</th>
              <th className="py-1.5 pr-2 font-medium">Data</th>
              <th className="py-1.5 pr-2 text-right font-medium">VOP</th>
              <th className="py-1.5 pr-2 text-right font-medium">Δ paridade</th>
              <th className="py-1.5 pr-2 text-right font-medium">Receita</th>
              <th className="py-1.5 pr-2 text-right font-medium">Yield</th>
              <th className="py-1.5 pl-2 font-medium">Flag</th>
            </tr>
          </thead>
          <tbody>
            {data.pontos.map((p) => (
              <tr
                key={p.du}
                onClick={onRowClick ? () => onRowClick(p.data) : undefined}
                className={cx(
                  "border-b border-gray-100 last:border-b-0 dark:border-gray-900",
                  p.today && "bg-blue-50/40 dark:bg-blue-500/5",
                  onRowClick &&
                    "cursor-pointer transition-colors hover:bg-gray-50 dark:hover:bg-gray-900",
                )}
              >
                <td className="py-1.5 pr-2 text-gray-500 dark:text-gray-400">
                  {p.du}
                </td>
                <td className="py-1.5 pr-2 text-gray-900 dark:text-gray-100">
                  {fmtDataPt(p.data)}
                  {p.today && (
                    <span className="ml-1 text-[10px] uppercase tracking-wider text-blue-600 dark:text-blue-400">
                      hoje
                    </span>
                  )}
                </td>
                <td className="py-1.5 pr-2 text-right text-gray-900 dark:text-gray-100">
                  {fmtBRL.format(p.vop)}
                </td>
                <td
                  className={cx(
                    "py-1.5 pr-2 text-right",
                    p.delta_par_pct === null
                      ? "text-gray-400 dark:text-gray-600"
                      : p.delta_par_pct >= 0
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-red-600 dark:text-red-400",
                  )}
                >
                  {fmtDelta(p.delta_par_pct)}
                </td>
                <td className="py-1.5 pr-2 text-right text-gray-900 dark:text-gray-100">
                  {fmtBRL.format(p.receita)}
                </td>
                <td className="py-1.5 pr-2 text-right text-gray-900 dark:text-gray-100">
                  {fmtYield(p.yield_pct)}
                </td>
                <td className="py-1.5 pl-2">
                  {p.outlier && (
                    <span
                      className="inline-flex items-center gap-1 rounded bg-amber-50 px-1.5 py-0.5 text-[10.5px] font-medium text-amber-700 dark:bg-amber-500/10 dark:text-amber-300"
                      title="Dia fora da curva"
                    >
                      <RiAlertLine className="size-3" />
                      Outlier
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {data && (
        <p className="mt-3 text-[10.5px] text-gray-500 dark:text-gray-500">
          {data.du_disponivel
            ? `DU ${data.du_decorridos}/${data.du_totais_mes} · ${data.mes_label}`
            : `${data.mes_label} (calendário de dias úteis indisponível — fallback seg-sex)`}
        </p>
      )}
    </Card>
  )
}
