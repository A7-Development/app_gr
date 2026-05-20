// src/app/(app)/bi/operacoes4/_components/ReceitasSection.tsx
//
// L3 da pagina /bi/operacoes4 — composicao da receita MTD em 4 buckets
// (esquerda) + yield efetivo por DU (direita). Consome o endpoint
// `/bi/operacoes4/lens-receitas` via `biOperacoes4.lensReceitas`.
//
// REGIME CAIXA (wh_operacao). Multa/mora/cobranca/aditivo nao aparecem
// (sao pos-cessao). IOF e passthrough — nao entra no yield nem na
// composicao. Ver CLAUDE.md banner operacoes4 + handoff SPEC.

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"

import { Card } from "@/components/tremor/Card"
import { cardTokens } from "@/design-system/tokens/card"
import { cx } from "@/lib/utils"
import {
  biOperacoes4,
  type Operacoes4LensReceitasData,
  type Operacoes4ReceitaTipo,
} from "@/lib/api-client"
import type { BIFilters } from "@/lib/api-client"

import {
  ReceitaCompositionBar,
  type ReceitaBucket,
} from "./charts/ReceitaCompositionBar"
import { YieldChart } from "./charts/YieldChart"

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 2,
})

function fmtPctSigned(v: number | null): string {
  if (v === null) return "—"
  const sign = v > 0 ? "+" : ""
  return `${sign}${v.toFixed(1).replace(".", ",")}%`
}

function fmtPpSigned(v: number | null): string {
  if (v === null) return "—"
  const sign = v > 0 ? "+" : ""
  return `${sign}${v.toFixed(2).replace(".", ",")} pp`
}

function toNumber(v: string | number): number {
  return typeof v === "string" ? Number(v) : v
}

const TIPO_LABEL: Record<Operacoes4ReceitaTipo, string> = {
  desagio: "Deságio",
  tarifa_cessao: "Tarifa de cessão",
  tarifas_operacionais: "Tarifas operacionais",
  outras: "Outras",
}

function toBuckets(data: Operacoes4LensReceitasData): ReceitaBucket[] {
  return data.composicao.map((c) => ({
    tipo: c.tipo,
    label: TIPO_LABEL[c.tipo],
    valor: toNumber(c.valor),
    sharePct: c.share_pct,
    deltaPct: c.delta_pct,
    flagAtypical: c.flag_atypical,
  }))
}

export function ReceitasSection({
  filters,
  onBucketClick,
}: {
  filters: BIFilters
  /** Click numa linha da composicao (= drill por bucket). */
  onBucketClick?: (tipo: Operacoes4ReceitaTipo) => void
}) {
  const q = useQuery({
    queryKey: ["bi", "operacoes4", "lens-receitas", filters],
    queryFn: () => biOperacoes4.lensReceitas(filters),
  })

  const data = q.data?.data
  const loading = q.isLoading
  const error = q.isError ? "Falha ao carregar receitas." : null

  return (
    <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      {/* L3 esquerda — Composicao */}
      <Card className={cx(cardTokens.body)}>
        <div className="mb-3">
          <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
            Composição da receita · MTD
          </p>
          {data ? (
            <p className="mt-1 flex flex-wrap items-baseline gap-x-2 tabular-nums">
              <span className="text-[20px] font-semibold leading-none tracking-tight text-gray-900 dark:text-gray-50">
                {fmtBRL.format(toNumber(data.total_mtd))}
              </span>
              {data.delta_pct !== null && (
                <span
                  className={cx(
                    "text-xs font-medium",
                    data.delta_pct >= 0
                      ? "text-emerald-600 dark:text-emerald-400"
                      : "text-red-600 dark:text-red-400",
                  )}
                >
                  {fmtPctSigned(data.delta_pct)}
                </span>
              )}
              <span className="text-[11px] text-gray-500 dark:text-gray-400">
                vs mesmo DU mês ant. ·{" "}
                {fmtBRL.format(toNumber(data.total_parity))}
              </span>
            </p>
          ) : (
            <p className="mt-1 text-[20px] font-semibold leading-none text-gray-300 dark:text-gray-700">
              {loading ? "…" : error ? "—" : "—"}
            </p>
          )}
          <p className="mt-1.5 text-xs text-gray-500 dark:text-gray-400">
            4 buckets em regime caixa. Multa, mora, cobrança e aditivo são
            eventos pós-cessão e não aparecem aqui.
          </p>
        </div>

        {loading && (
          <div
            className="h-7 animate-pulse rounded bg-gray-100 dark:bg-gray-800"
            aria-busy="true"
          />
        )}
        {error && (
          <div className="flex flex-col items-center gap-2 py-6">
            <p className="text-xs text-gray-500 dark:text-gray-400">{error}</p>
            <button
              type="button"
              onClick={() => q.refetch()}
              className="rounded border border-gray-200 px-2.5 py-1 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-900"
            >
              Tentar novamente
            </button>
          </div>
        )}
        {data && toNumber(data.total_mtd) === 0 && !loading && (
          <div className="flex flex-col items-center gap-1.5 py-2">
            <div
              aria-hidden="true"
              className="h-7 w-full rounded bg-gray-100 dark:bg-gray-800"
            />
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Sem receita registrada no MTD.
            </p>
          </div>
        )}
        {data && toNumber(data.total_mtd) > 0 && (
          <ReceitaCompositionBar
            buckets={toBuckets(data)}
            onBucketClick={onBucketClick}
          />
        )}
      </Card>

      {/* L3 direita — Yield efetivo */}
      <Card className={cx(cardTokens.body)}>
        <div className="mb-3">
          <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
            Yield efetivo · receita / VOP
          </p>
          {data ? (
            <p className="mt-1 flex flex-wrap items-baseline gap-x-2 tabular-nums">
              <span className="text-[20px] font-semibold leading-none tracking-tight text-gray-900 dark:text-gray-50">
                {data.yield_wavg.toFixed(2).replace(".", ",")}% wavg
              </span>
              <span
                className={cx(
                  "text-xs font-medium",
                  (data.yield_delta_pp ?? 0) >= 0
                    ? "text-emerald-600 dark:text-emerald-400"
                    : "text-red-600 dark:text-red-400",
                )}
              >
                {fmtPpSigned(data.yield_delta_pp)}
              </span>
              <span className="text-[11px] text-gray-500 dark:text-gray-400">
                vs paridade DU ({data.yield_parity_wavg.toFixed(2).replace(".", ",")}
                %)
              </span>
            </p>
          ) : (
            <p className="mt-1 text-[20px] font-semibold leading-none text-gray-300 dark:text-gray-700">
              {loading ? "…" : error ? "—" : "—"}
            </p>
          )}
          <p className="mt-1.5 text-xs text-gray-500 dark:text-gray-400">
            Linha sólida = MTD por DU. Tracejada cinza = mesmos DUs do mês
            anterior.
          </p>
        </div>

        {data && data.yield_du.length === 0 && !loading && !error ? (
          <div
            className="flex flex-col items-center justify-center gap-1.5 rounded bg-gray-50 py-10 dark:bg-gray-900/40"
            style={{ minHeight: 200 }}
          >
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Sem yield apurado no MTD.
            </p>
            <p className="text-[10.5px] text-gray-400 dark:text-gray-600">
              Aguardando primeiros dias com operações efetivadas.
            </p>
          </div>
        ) : (
          <YieldChart
            data={
              data?.yield_du.map((p) => ({
                du: p.du,
                yieldPct: p.yield_pct,
                yieldParityPct: p.yield_parity_pct,
                today: p.today,
              })) ?? []
            }
            loading={loading}
            error={error ?? undefined}
            onRetry={() => q.refetch()}
          />
        )}

        {data && (data.movers.cresceu || data.movers.caiu) && (
          <div className="mt-3 flex flex-wrap gap-2">
            {data.movers.cresceu && (
              <MoverPill
                label="Cresceu mais"
                tipo={TIPO_LABEL[data.movers.cresceu.tipo]}
                delta={data.movers.cresceu.delta_pct}
                tone="pos"
              />
            )}
            {data.movers.caiu && (
              <MoverPill
                label="Caiu mais"
                tipo={TIPO_LABEL[data.movers.caiu.tipo]}
                delta={data.movers.caiu.delta_pct}
                tone="neg"
              />
            )}
          </div>
        )}
      </Card>
    </section>
  )
}

function MoverPill({
  label,
  tipo,
  delta,
  tone,
}: {
  label: string
  tipo: string
  delta: number
  tone: "pos" | "neg"
}) {
  const toneClass =
    tone === "pos"
      ? "text-emerald-600 dark:text-emerald-400"
      : "text-red-600 dark:text-red-400"
  return (
    <div className="flex min-w-[180px] flex-1 flex-col gap-0.5 rounded border border-gray-200 bg-gray-50 px-2.5 py-2 dark:border-gray-800 dark:bg-gray-900">
      <span className="text-[10.5px] uppercase tracking-wider text-gray-500 dark:text-gray-400">
        {label}
      </span>
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-[12px] font-medium text-gray-900 dark:text-gray-100">
          {tipo}
        </span>
        <span className={cx("tabular-nums text-[12px] font-semibold", toneClass)}>
          {fmtPctSigned(delta)}
        </span>
      </div>
    </div>
  )
}
