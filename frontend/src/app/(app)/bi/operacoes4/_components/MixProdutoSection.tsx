// src/app/(app)/bi/operacoes4/_components/MixProdutoSection.tsx
//
// L4 — Mix de produtos 75/25. Consome `/bi/operacoes2/aba2-produtos-pricing`
// (ja existente). Esquerda (col-9): lista ranqueada de produtos com VOP MTD
// + delta MoM + taxa media. Direita (col-3): mini-tabela de taxa por
// produto + flag visual quando a taxa MTD cresce > 0,10pp vs MoM.
//
// Sem chart de waterfall novo — preferimos a lista tabular porque a
// granularidade do ranking (siglas reais) responde melhor "quem ta movendo
// o ponteiro" do que o waterfall agregado.

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"

import { Card } from "@/components/tremor/Card"
import { cardTokens } from "@/design-system/tokens/card"
import { tokens } from "@/design-system/tokens"
import { cx } from "@/lib/utils"
import { biOperacoes2 } from "@/lib/api-client"
import type {
  BIFilters,
  Operacoes2RankingProdutoLinha,
} from "@/lib/api-client"

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 1,
})

const fmtPct1 = (v: number) => `${v.toFixed(1).replace(".", ",")}%`
const fmtPp2 = (v: number) =>
  `${v > 0 ? "+" : ""}${v.toFixed(2).replace(".", ",")} pp`

// Cor por produto: rotacao na escala canonica de chart (zero hex literal
// solto — todas vem de tokens.colors.chart).
function colorForIndex(idx: number): string {
  return tokens.colors.chart[idx % tokens.colors.chart.length]
}

export function MixProdutoSection({ filters }: { filters: BIFilters }) {
  const q = useQuery({
    queryKey: ["bi", "operacoes4", "produtos-pricing", filters],
    queryFn: () => biOperacoes2.abaProdutosPricing(filters),
  })

  const ranking = q.data?.data.ranking ?? []
  const loading = q.isLoading
  const error = q.isError ? "Falha ao carregar mix de produtos." : null

  const totalVop = ranking.reduce((s, r) => s + r.vop, 0) || 1

  return (
    <section className="grid grid-cols-1 gap-4 xl:grid-cols-4">
      {/* L4 esquerda — Ranking (col-3 de 4) */}
      <Card className={cx(cardTokens.body, "xl:col-span-3")}>
        <div className="mb-3">
          <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
            Mix de produtos · MTD
          </p>
          <p className="mt-1.5 text-xs text-gray-500 dark:text-gray-400">
            Ranking por VOP MTD. Delta MoM e taxa média ponderada por produto.
          </p>
        </div>

        {loading && (
          <div
            className="h-32 animate-pulse rounded bg-gray-100 dark:bg-gray-800"
            aria-busy="true"
          />
        )}
        {error && (
          <p className="py-6 text-center text-xs text-gray-500 dark:text-gray-400">
            {error}
          </p>
        )}
        {!loading && !error && ranking.length === 0 && (
          <p className="py-6 text-center text-xs text-gray-500 dark:text-gray-400">
            Sem operações no MTD.
          </p>
        )}
        {ranking.length > 0 && (
          <ProdutoRanking ranking={ranking} totalVop={totalVop} />
        )}
      </Card>

      {/* L4 direita — Taxa por produto (col-1 de 4) */}
      <Card className={cx(cardTokens.body)}>
        <div className="mb-3">
          <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
            Taxa por produto
          </p>
          <p className="mt-1.5 text-xs text-gray-500 dark:text-gray-400">
            Média ponderada. ⚠ marca alta &gt; 0,10 pp.
          </p>
        </div>
        {ranking.length > 0 ? (
          <ul className="flex flex-col gap-1.5">
            {ranking.slice(0, 8).map((r, idx) => {
              const flag = (r.delta_mom_pp ?? 0) > 0.1
              return (
                <li
                  key={r.sigla}
                  className="flex items-center justify-between gap-2 text-[12px]"
                >
                  <span className="flex items-center gap-1.5">
                    <span
                      aria-hidden="true"
                      className="inline-block size-2 shrink-0 rounded-sm"
                      style={{ background: colorForIndex(idx) }}
                    />
                    <span className="font-medium text-gray-900 dark:text-gray-100">
                      {r.sigla}
                    </span>
                  </span>
                  <span className="flex items-baseline gap-1.5 tabular-nums">
                    <span className="text-gray-900 dark:text-gray-100">
                      {fmtPct1(r.taxa_media)}
                    </span>
                    {r.delta_mom_pp !== null && (
                      <span
                        className={cx(
                          "text-[10.5px]",
                          r.delta_mom_pp >= 0
                            ? "text-emerald-600 dark:text-emerald-400"
                            : "text-red-600 dark:text-red-400",
                        )}
                      >
                        {fmtPp2(r.delta_mom_pp)}
                      </span>
                    )}
                    {flag && (
                      <span
                        aria-label="alta acima de 0,1 pp"
                        className="inline-block size-1.5 rounded-full"
                        style={{ background: "#D97706" }}
                      />
                    )}
                  </span>
                </li>
              )
            })}
          </ul>
        ) : (
          <p className="py-6 text-center text-xs text-gray-500 dark:text-gray-400">
            —
          </p>
        )}
      </Card>
    </section>
  )
}

function ProdutoRanking({
  ranking,
  totalVop,
}: {
  ranking: Operacoes2RankingProdutoLinha[]
  totalVop: number
}) {
  return (
    <table className="w-full text-left text-[12px] tabular-nums">
      <thead>
        <tr className="border-b border-gray-200 text-[10.5px] uppercase tracking-wider text-gray-500 dark:border-gray-800 dark:text-gray-400">
          <th className="py-1.5 pr-2 font-medium">Produto</th>
          <th className="py-1.5 pr-2 text-right font-medium">VOP MTD</th>
          <th className="py-1.5 pr-2 text-right font-medium">Share</th>
          <th className="py-1.5 pr-2 text-right font-medium">Δ MoM</th>
          <th className="py-1.5 text-right font-medium">N ops</th>
        </tr>
      </thead>
      <tbody>
        {ranking.map((r, idx) => (
          <tr
            key={r.sigla}
            className="border-b border-gray-100 last:border-b-0 dark:border-gray-900"
          >
            <td className="py-1.5 pr-2">
              <span className="flex items-center gap-1.5">
                <span
                  aria-hidden="true"
                  className="inline-block size-2 shrink-0 rounded-sm"
                  style={{ background: colorForIndex(idx) }}
                />
                <span className="font-medium text-gray-900 dark:text-gray-100">
                  {r.sigla}
                </span>
                {r.nome && (
                  <span className="truncate text-gray-500 dark:text-gray-400">
                    {r.nome}
                  </span>
                )}
              </span>
            </td>
            <td className="py-1.5 pr-2 text-right text-gray-900 dark:text-gray-100">
              {fmtBRL.format(r.vop)}
            </td>
            <td className="py-1.5 pr-2 text-right text-gray-500 dark:text-gray-400">
              {((r.vop / totalVop) * 100).toFixed(1).replace(".", ",")}%
            </td>
            <td
              className={cx(
                "py-1.5 pr-2 text-right",
                (r.delta_mom_pp ?? 0) >= 0
                  ? "text-emerald-600 dark:text-emerald-400"
                  : "text-red-600 dark:text-red-400",
              )}
            >
              {r.delta_mom_pp !== null ? fmtPp2(r.delta_mom_pp) : "—"}
            </td>
            <td className="py-1.5 text-right text-gray-500 dark:text-gray-400">
              {r.n_operacoes}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
