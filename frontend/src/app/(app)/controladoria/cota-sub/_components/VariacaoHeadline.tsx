"use client"

/**
 * VariacaoHeadline — o read de 10 segundos da variacao da Cota Sub (Fase 1).
 *
 * Substitui o MOCK_INSIGHTS (IA falsa) + o botao morto "Explicar variacao"
 * (monolito sem prompt ativo) por um headline 100% ESTRUTURADO, vindo de
 * `/controladoria/cota-sub/variacao/headline`. Zero LLM.
 *
 * Tres blocos, na ordem da leitura do controller:
 *   1. VEREDITO  — Δ cota + reconciliacao + nº de atencoes (glance de 5s).
 *   2. DRIVERS   — o que moveu, ranqueado por impacto LIMPO (giro separado do
 *                  resultado). Clicaveis: abrem a evidencia (drill) da linha.
 *   3. FLAGS     — o que vigiar, com R$. Empurra o sinal ate o usuario.
 *
 * O LLM (chat) entra so depois, sob demanda, pra investigar o que aqui aparece.
 */

import {
  RiAlertLine,
  RiArrowRightLine,
  RiCheckLine,
  RiErrorWarningLine,
  RiSearchLine,
} from "@remixicon/react"

import { cx } from "@/lib/utils"
import { Card } from "@/components/tremor/Card"
import type { CategoriaPatrimonialKey, VariacaoHeadlineResponse } from "@/lib/api-client"

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency", currency: "BRL", minimumFractionDigits: 2, maximumFractionDigits: 2,
})
const fmtSigned = (v: number) => (v >= 0 ? "+" : "−") + fmtBRL.format(Math.abs(v))

// Variacao percentual sobre o PL Sub de D-1 (a base pedida). null quando D-1 ~0.
function pctVsD1(delta: number, d1: number): number | null {
  return Math.abs(d1) < 1 ? null : (delta / d1) * 100
}
const fmtPctSigned = (v: number) =>
  (v >= 0 ? "+" : "−") +
  Math.abs(v).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) +
  "%"

// Tom de impacto na otica Sub: positivo aumentou a cota (verde), negativo reduziu
// (vermelho), giro/reclassificacao e neutro (cinza).
function toneClass(v: number, neutral = false): string {
  if (neutral) return "text-gray-500 dark:text-gray-400"
  return v >= 0
    ? "text-emerald-600 dark:text-emerald-400"
    : "text-red-600 dark:text-red-400"
}

const DRILLABLE = new Set<string>(["dc", "pdd", "cpr_pagar", "cpr_receber"])

export type VariacaoHeadlineProps = {
  data?:             VariacaoHeadlineResponse
  loading?:          boolean
  onDrillCategoria?: (key: CategoriaPatrimonialKey) => void
}

export function VariacaoHeadline({ data, loading, onDrillCategoria }: VariacaoHeadlineProps) {
  if (loading) {
    return (
      <Card className="animate-pulse">
        <div className="h-6 w-64 rounded bg-gray-200 dark:bg-gray-800" />
        <div className="mt-4 space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-5 w-full rounded bg-gray-100 dark:bg-gray-900" />
          ))}
        </div>
      </Card>
    )
  }
  if (!data) return null

  const max = Math.max(
    1,
    ...data.drivers.filter((d) => d.key !== "giro_reclassificacao").map((d) => Math.abs(d.impacto_pl_sub)),
  )

  return (
    <Card className="flex flex-col gap-4">
      {/* ── 1. VEREDITO ─────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <span className="text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Variação da Cota Sub
        </span>
        <span className={cx("text-2xl font-semibold tabular-nums", toneClass(data.cota_sub_delta))}>
          {fmtSigned(data.cota_sub_delta)}
        </span>
        {(() => {
          const pct = pctVsD1(data.cota_sub_delta, data.cota_sub_d1)
          return pct === null ? null : (
            <span
              className={cx("text-base font-medium tabular-nums", toneClass(data.cota_sub_delta))}
              title="Variação sobre o PL da Cota Sub do dia anterior (D-1)"
            >
              {fmtPctSigned(pct)}
            </span>
          )
        })()}
        <span className="flex items-center gap-1 text-[13px] text-gray-500 dark:text-gray-400">
          {data.reconciliacao_ok ? (
            <RiCheckLine className="size-4 text-emerald-500" aria-hidden />
          ) : (
            <RiErrorWarningLine className="size-4 text-red-500" aria-hidden />
          )}
          {data.reconciliacao_ok
            ? "fecha com o MEC"
            : `não fecha (${fmtBRL.format(data.reconciliacao_residuo)})`}
        </span>
        {data.n_atencao > 0 && (
          <span className="flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[12px] font-medium text-amber-700 dark:bg-amber-950/40 dark:text-amber-400">
            <RiAlertLine className="size-3.5" aria-hidden />
            {data.n_atencao} {data.n_atencao === 1 ? "atenção" : "atenções"}
          </span>
        )}
      </div>

      {/* ── 2. DRIVERS ──────────────────────────────────────────────── */}
      <div className="flex flex-col gap-1.5">
        <span className="text-[11px] font-medium uppercase tracking-wide text-gray-400 dark:text-gray-500">
          O que moveu a cota
        </span>
        {data.drivers.map((d) => {
          const neutral = d.key === "giro_reclassificacao"
          const drillable = !!d.drill_key && DRILLABLE.has(d.drill_key) && !!onDrillCategoria
          const pct = Math.round((Math.abs(d.impacto_pl_sub) / max) * 100)
          return (
            <button
              key={d.key}
              type="button"
              disabled={!drillable}
              onClick={
                drillable
                  ? () => onDrillCategoria!(d.drill_key as CategoriaPatrimonialKey)
                  : undefined
              }
              className={cx(
                "group flex items-center gap-3 rounded px-2 py-1.5 text-left",
                drillable
                  ? "cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-900/50"
                  : "cursor-default",
              )}
            >
              {d.severidade === "atencao" ? (
                <RiAlertLine className="size-4 shrink-0 text-amber-500" aria-hidden />
              ) : (
                <span className="size-4 shrink-0" />
              )}
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-3">
                  <span className={cx(
                    "truncate text-[13px]",
                    neutral ? "text-gray-500 dark:text-gray-400" : "font-medium text-gray-900 dark:text-gray-100",
                  )}>
                    {d.label}
                  </span>
                  <span className={cx("shrink-0 text-[13px] font-semibold tabular-nums", toneClass(d.impacto_pl_sub, neutral))}>
                    {fmtSigned(d.impacto_pl_sub)}
                  </span>
                </div>
                <div className="mt-0.5 flex items-center gap-2">
                  <div className="h-1 flex-1 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-900">
                    <div
                      className={cx("h-full rounded-full", neutral ? "bg-gray-300 dark:bg-gray-700" : d.impacto_pl_sub >= 0 ? "bg-emerald-400/70" : "bg-red-400/70")}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="truncate text-[11px] text-gray-500 dark:text-gray-400">{d.detalhe}</span>
                  {drillable && (
                    <RiArrowRightLine className="size-3.5 shrink-0 text-gray-300 transition-colors group-hover:text-blue-500 dark:text-gray-600" aria-hidden />
                  )}
                </div>
              </div>
            </button>
          )
        })}
      </div>

      {/* ── 3. FLAGS ────────────────────────────────────────────────── */}
      {data.flags.length > 0 && (
        <div className="flex flex-col gap-1.5 border-t border-gray-100 pt-3 dark:border-gray-900">
          <span className="text-[11px] font-medium uppercase tracking-wide text-amber-600 dark:text-amber-500">
            ⚠ Atenção
          </span>
          {data.flags.map((f, i) => {
            const drillable = !!f.drill_key && DRILLABLE.has(f.drill_key) && !!onDrillCategoria
            return (
              <button
                key={i}
                type="button"
                disabled={!drillable}
                onClick={
                  drillable
                    ? () => onDrillCategoria!(f.drill_key as CategoriaPatrimonialKey)
                    : undefined
                }
                className={cx(
                  "flex items-start gap-2 rounded px-2 py-1.5 text-left",
                  drillable ? "cursor-pointer hover:bg-amber-50/60 dark:hover:bg-amber-950/20" : "cursor-default",
                )}
              >
                <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-amber-500" aria-hidden />
                <span className="flex-1 text-[13px] text-gray-700 dark:text-gray-300">
                  {f.descricao}
                  <span className="ml-1 font-semibold tabular-nums text-gray-900 dark:text-gray-100">
                    {fmtBRL.format(Math.abs(f.valor))}
                  </span>
                </span>
                {f.investigavel && (
                  <span className="flex shrink-0 items-center gap-1 text-[11px] font-medium text-blue-600 dark:text-blue-400">
                    <RiSearchLine className="size-3.5" aria-hidden />
                    investigar
                  </span>
                )}
              </button>
            )
          })}
        </div>
      )}
    </Card>
  )
}
