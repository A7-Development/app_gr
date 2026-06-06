"use client"

/**
 * CotaSubStatusBand — banda de KPI do topo da aba "Resumo do dia" (Z1).
 *
 * Spec do handoff (card de KPI): banda horizontal de KPIs
 *   PL SUB · DD/MM  |  VARIAÇÃO DO DIA  |  VARIAÇÃO %
 * + indicadores de status à direita (status pills): reports + reconciliacao
 *   MEC ("fecha com o MEC") + resumo de atenções do dia.
 *
 * O status dos reports é uma STATUS PILL no canto direito (decisão Ricardo
 * 2026-06-06), ao lado da pill do MEC — NÃO um tile de KPI na banda (reports
 * é status, não métrica). Cotistas fica de fora ate haver fonte real no
 * dominio cota-sub (§14: nada inventado).
 *
 * Dado: `resumo` (VariacaoResumoResponse) + `reportEntries` (readiness QiTech).
 * Tudo oficial/estruturado, zero LLM.
 */

import * as React from "react"

import { cx } from "@/lib/utils"
import type { VariacaoResumoResponse } from "@/lib/api-client"
import type { CoverageStripEntry } from "@/design-system/components"

const fmtCompact = new Intl.NumberFormat("pt-BR", {
  style: "currency", currency: "BRL", notation: "compact", maximumFractionDigits: 2,
})
const fmtSignedCompact = (v: number) => `${v >= 0 ? "+" : "−"}${fmtCompact.format(Math.abs(v))}`
const fmtPct = (v: number) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(2).replace(".", ",")}%`

function fmtDateBr(iso?: string): string {
  if (!iso) return ""
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  return m ? `${m[3]}/${m[2]}/${m[1]}` : iso
}

function toneText(v: number): string {
  return v > 0
    ? "text-emerald-700 dark:text-emerald-400"
    : v < 0
      ? "text-rose-700 dark:text-rose-400"
      : "text-gray-500 dark:text-gray-400"
}

export type CotaSubStatusBandProps = {
  resumo?:       VariacaoResumoResponse
  reportEntries: CoverageStripEntry[]
  dataD0:        string  // ISO
  loading?:      boolean
}

export function CotaSubStatusBand({ resumo, reportEntries, dataD0, loading }: CotaSubStatusBandProps) {
  const variacaoPct =
    resumo && resumo.pl_sub_mec_d1 ? (resumo.cota_delta / resumo.pl_sub_mec_d1) * 100 : null

  // Reports — saude do dia. Prontos = ready|may_change; "pode mudar" = may_change.
  const total = reportEntries.length
  const prontos = reportEntries.filter((e) => e.health === "ready" || e.health === "may_change").length
  const podeMudar = reportEntries.filter((e) => e.health === "may_change").length
  const reportsProntos = total > 0 && prontos === total

  const fecha = resumo?.reconciliacao.fecha
  const nAtencoes = resumo?.atencoes.length ?? 0

  if (loading) {
    return (
      <section className="flex flex-wrap items-center gap-x-8 gap-y-2 rounded border border-gray-200 bg-white px-4 py-3 dark:border-gray-800 dark:bg-gray-950">
        {[0, 1, 2].map((i) => (
          <div key={i}>
            <div className="h-3 w-20 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
            <div className="mt-1.5 h-6 w-24 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
          </div>
        ))}
      </section>
    )
  }
  if (!resumo) return null

  return (
    <section className="flex flex-wrap items-center gap-x-8 gap-y-3 rounded border border-gray-200 bg-white px-4 py-3 dark:border-gray-800 dark:bg-gray-950">
      {/* PL SUB — headline em BRL compacto (R$ X,XXM) */}
      <Col label={`PL Sub · ${fmtDateBr(dataD0)}`}>
        <span className="text-[23px] font-bold leading-none tracking-[-0.025em] tabular-nums text-gray-900 dark:text-gray-50">
          {fmtCompact.format(resumo.pl_sub_mec_d0)}
        </span>
      </Col>

      <Col label="Variação do dia" divider>
        <span className={cx("text-[17px] font-semibold leading-none tabular-nums", toneText(resumo.cota_delta))}>
          {fmtSignedCompact(resumo.cota_delta)}
        </span>
      </Col>

      <Col label="Variação %" divider>
        <span className={cx("text-[17px] font-semibold leading-none tabular-nums", variacaoPct != null ? toneText(variacaoPct) : "")}>
          {variacaoPct != null ? fmtPct(variacaoPct) : "—"}
        </span>
      </Col>

      {/* Indicadores à direita: reports + reconciliacao MEC (status pills) + atenções */}
      <div className="ml-auto flex flex-col items-end gap-1.5">
        <div className="flex flex-wrap items-center justify-end gap-2">
          {/* MEC — fecha / resíduo */}
          <span className={cx(
            "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-semibold",
            fecha
              ? "border-emerald-100 bg-emerald-50 text-emerald-700 dark:border-emerald-900/40 dark:bg-emerald-500/10 dark:text-emerald-300"
              : "border-amber-100 bg-amber-50 text-amber-700 dark:border-amber-900/40 dark:bg-amber-500/10 dark:text-amber-300",
          )}>
            <span className={cx("size-1.5 rounded-full", fecha ? "bg-emerald-500" : "bg-amber-500")} aria-hidden="true" />
            {fecha ? "fecha com o MEC" : "resíduo vs MEC"}
          </span>

          {/* REPORTS — status pill (não é KPI) */}
          <span className={cx(
            "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-semibold tabular-nums",
            reportsProntos
              ? "border-emerald-100 bg-emerald-50 text-emerald-700 dark:border-emerald-900/40 dark:bg-emerald-500/10 dark:text-emerald-300"
              : "border-amber-100 bg-amber-50 text-amber-700 dark:border-amber-900/40 dark:bg-amber-500/10 dark:text-amber-300",
          )}>
            <span className={cx("size-1.5 rounded-full", reportsProntos ? "bg-emerald-500" : "bg-amber-500")} aria-hidden="true" />
            {prontos}/{total} reports · {fmtDateBr(dataD0)}
          </span>

          {podeMudar > 0 && (
            <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-500/10 dark:text-amber-400">
              {podeMudar} pode mudar
            </span>
          )}
        </div>
        <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-gray-500 dark:text-gray-400">
          <span className={cx("size-1.5 rounded-full", nAtencoes === 0 ? "bg-gray-300 dark:bg-gray-600" : "bg-amber-500")} aria-hidden="true" />
          {nAtencoes === 0
            ? "Nenhuma atenção no dia — variação dentro da rotina"
            : `${nAtencoes} ${nAtencoes === 1 ? "atenção" : "atenções"} no dia`}
        </span>
      </div>
    </section>
  )
}

function Col({ label, divider, children }: { label: string; divider?: boolean; children: React.ReactNode }) {
  return (
    <div className={cx(divider && "border-l border-gray-200 pl-8 dark:border-gray-800")}>
      <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-500 dark:text-gray-400">
        {label}
      </div>
      <div className="mt-0.5">{children}</div>
    </div>
  )
}
