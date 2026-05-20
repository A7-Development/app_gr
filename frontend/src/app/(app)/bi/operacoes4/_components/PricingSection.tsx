// src/app/(app)/bi/operacoes4/_components/PricingSection.tsx
//
// L6 — Pricing 50/50. Histograma de Taxas + Histograma de Prazos.
// Consome `/bi/operacoes2/aba2-produtos-pricing` ja existente — os buckets
// la sao por produto; aqui agregamos client-side somando VOP por
// bucket_label (independente de produto).
//
// Paridade DU NAO esta no payload atual — backend so retorna MTD. Renderiza
// `parity: 0` nos buckets ate o backend expor a paridade. Followup
// registrado no SPEC.

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"

import { Card } from "@/components/tremor/Card"
import { cardTokens } from "@/design-system/tokens/card"
import { cx } from "@/lib/utils"
import { biOperacoes2 } from "@/lib/api-client"
import type {
  BIFilters,
  Operacoes2HistogramaProdutoBucket,
} from "@/lib/api-client"

import {
  HistogramWithParity,
  type HistogramBucket,
} from "./charts/HistogramWithParity"

const TAIL_TAXA_LABELS = new Set([">3,5", ">3.5", "3,5+"])
const TAIL_PRAZO_LABELS = new Set([">90", "90+"])

function aggregateBuckets(
  raw: Operacoes2HistogramaProdutoBucket[],
  tailLabels: Set<string>,
): HistogramBucket[] {
  // Ordena por bucket_lower e agrega por bucket_label.
  const map = new Map<
    string,
    { lower: number; vop: number }
  >()
  for (const b of raw) {
    const cur = map.get(b.bucket_label)
    if (cur) {
      cur.vop += b.vop
    } else {
      map.set(b.bucket_label, { lower: b.bucket_lower, vop: b.vop })
    }
  }
  const ordered = Array.from(map.entries()).sort(
    ([, a], [, b]) => a.lower - b.lower,
  )
  // Converte VOP em milhoes pra escala visual razoavel.
  return ordered.map(([label, { vop }]) => ({
    label,
    atual: vop / 1_000_000,
    parity: 0,
    tailFlag: tailLabels.has(label),
  }))
}

export function PricingSection({ filters }: { filters: BIFilters }) {
  const q = useQuery({
    queryKey: ["bi", "operacoes4", "pricing", filters],
    queryFn: () => biOperacoes2.abaProdutosPricing(filters),
  })

  const data = q.data?.data
  const loading = q.isLoading
  const error = q.isError ? "Falha ao carregar histogramas." : null

  const taxasData = React.useMemo(
    () =>
      data
        ? aggregateBuckets(data.histograma_taxas.buckets, TAIL_TAXA_LABELS)
        : [],
    [data],
  )
  const prazosData = React.useMemo(
    () =>
      data
        ? aggregateBuckets(data.histograma_prazos.buckets, TAIL_PRAZO_LABELS)
        : [],
    [data],
  )

  const taxasEmpty =
    !loading &&
    !error &&
    data !== undefined &&
    taxasData.reduce((s, b) => s + b.atual, 0) === 0
  const prazosEmpty =
    !loading &&
    !error &&
    data !== undefined &&
    prazosData.reduce((s, b) => s + b.atual, 0) === 0

  return (
    <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      {/* L6 esquerda — Taxas */}
      <Card className={cx(cardTokens.body)}>
        <div className="mb-3">
          <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
            Distribuição de taxas · MTD
          </p>
          {data && (
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Média ponderada:{" "}
              <span className="font-medium tabular-nums text-gray-900 dark:text-gray-100">
                {data.histograma_taxas.media_ponderada
                  .toFixed(2)
                  .replace(".", ",")}
                %
              </span>{" "}
              · Mediana:{" "}
              <span className="tabular-nums">
                {data.histograma_taxas.mediana.toFixed(2).replace(".", ",")}%
              </span>
            </p>
          )}
        </div>
        {taxasEmpty ? (
          <EmptyHistogram message="Sem operações no MTD." />
        ) : (
          <HistogramWithParity
            data={taxasData}
            xAxisLabel="Taxa (% a.m.)"
            valueSuffix=" M"
            loading={loading}
            error={error ?? undefined}
            onRetry={() => q.refetch()}
          />
        )}
      </Card>

      {/* L6 direita — Prazos */}
      <Card className={cx(cardTokens.body)}>
        <div className="mb-3">
          <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
            Distribuição de prazos · MTD
          </p>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            Buckets de 15 dias. Cauda &gt;90 dias destacada quando &gt; 0.
          </p>
        </div>
        {prazosEmpty ? (
          <EmptyHistogram message="Sem operações no MTD." />
        ) : (
          <HistogramWithParity
            data={prazosData}
            xAxisLabel="Prazo (dias)"
            valueSuffix=" M"
            loading={loading}
            error={error ?? undefined}
            onRetry={() => q.refetch()}
          />
        )}
      </Card>
    </section>
  )
}

function EmptyHistogram({ message }: { message: string }) {
  return (
    <div
      className="flex flex-col items-center justify-center gap-1 rounded bg-gray-50 py-10 dark:bg-gray-900/40"
      style={{ minHeight: 220 }}
    >
      <p className="text-xs text-gray-500 dark:text-gray-400">{message}</p>
      <p className="text-[10.5px] text-gray-400 dark:text-gray-600">
        Aguardando primeiros dias com operações.
      </p>
    </div>
  )
}
