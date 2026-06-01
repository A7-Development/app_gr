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

      {/* ── 2. A EQUACAO DO BALANCO (Ativo − Passivo = Sub) ──────────────
          Sem abstracao: a cota e o ativo menos o passivo. O giro ja netou no
          total do Ativo. O detalhe de cada linha (e o giro do DC) vive no
          balancete (40%) e no drill — nao aqui. */}
      <div className="flex flex-col gap-1.5">
        <span className="text-[11px] font-medium uppercase tracking-wide text-gray-400 dark:text-gray-500">
          Como a cota se formou
        </span>
        <div className="flex items-center justify-between px-1 text-[13px]">
          <span className="flex items-center gap-2 text-gray-600 dark:text-gray-300">
            <span className="size-1.5 rounded-full bg-gray-400 dark:bg-gray-500" aria-hidden />
            Ativo
          </span>
          <span className="font-medium tabular-nums text-gray-900 dark:text-gray-100">
            {fmtSigned(data.delta_ativo)}
          </span>
        </div>
        <div className="flex items-center justify-between px-1 text-[13px]">
          <span className="flex items-center gap-2 text-gray-600 dark:text-gray-300">
            <span className="size-1.5 rounded-full bg-gray-400 dark:bg-gray-500" aria-hidden />
            − Passivo
            <span className="text-[11px] text-gray-400 dark:text-gray-500">(Contas a Pagar + Cotas Sr/Mez)</span>
          </span>
          <span className="font-medium tabular-nums text-gray-900 dark:text-gray-100">
            {fmtSigned(data.delta_passivo)}
          </span>
        </div>
        <div className="mt-0.5 flex items-center justify-between border-t border-gray-200 px-1 pt-1.5 dark:border-gray-800">
          <span className="text-[13px] font-semibold text-gray-900 dark:text-gray-100">= Variação da Sub</span>
          <span className={cx("text-[15px] font-semibold tabular-nums", toneClass(data.cota_sub_delta))}>
            {fmtSigned(data.cota_sub_delta)}
          </span>
        </div>
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
