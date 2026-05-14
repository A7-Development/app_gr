"use client"

/**
 * ReconStatusCard — strip horizontal abaixo do BridgeCard.
 *
 *   [icon] [headline + sublinha Δ Real · Δ Esperado · residuo]   .......   [stats ΔAtivo / ΔPassivo / ΔPL / ΔCotas Sr+Mez]
 *
 * Tom (ok/warn/error) deriva da tolerancia |residuo| / |pl_sub_d1|:
 *   <= 0,1pp -> ok      (icon emerald, "Balancete conciliado")
 *   <= 1pp   -> warn    (icon amber,   "Residuo proximo do limite")
 *   > 1pp    -> error   (icon red,     "Residuo acima da tolerancia")
 *
 * Stats: ΔAtivo / ΔPassivo / ΔPL vem dos nodes nivel-1 do balancete
 * (grupo=1, 4, 6). ΔCotas Sr+Mez vem direto de `reconciliacao`.
 */

import * as React from "react"
import {
  RiAlertLine,
  RiCheckboxCircleLine,
  RiErrorWarningLine,
} from "@remixicon/react"
import type { ComponentType } from "react"

import { cx } from "@/lib/utils"
import type { CosifNode, Reconciliacao } from "@/lib/api-client"

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency", currency: "BRL",
  minimumFractionDigits: 2, maximumFractionDigits: 2,
})

const fmtBRLk = (v: number) => {
  const abs = Math.abs(v)
  const sign = v < 0 ? "−" : v > 0 ? "+" : ""
  if (abs >= 1_000_000) return `${sign}R$ ${(abs / 1_000_000).toFixed(2).replace(".", ",")}M`
  if (abs >= 1_000)     return `${sign}R$ ${(abs / 1_000).toFixed(1).replace(".", ",")}k`
  return `${sign}R$ ${abs.toFixed(0)}`
}

type Tone = "ok" | "warn" | "error"

const TONE_META: Record<Tone, {
  icon:     ComponentType<{ className?: string }>
  iconCls:  string
  bgCls:    string
  headline: string
}> = {
  ok: {
    icon:     RiCheckboxCircleLine,
    iconCls:  "text-emerald-600 dark:text-emerald-400",
    bgCls:    "bg-emerald-50 dark:bg-emerald-500/10",
    headline: "Balancete conciliado — todas as fontes batem",
  },
  warn: {
    icon:     RiAlertLine,
    iconCls:  "text-amber-600 dark:text-amber-400",
    bgCls:    "bg-amber-50 dark:bg-amber-500/10",
    headline: "Resíduo próximo do limite de tolerância",
  },
  error: {
    icon:     RiErrorWarningLine,
    iconCls:  "text-red-600 dark:text-red-400",
    bgCls:    "bg-red-50 dark:bg-red-500/10",
    headline: "Resíduo acima da tolerância — investigar",
  },
}

export type ReconStatusCardProps = {
  reconciliacao?: Reconciliacao
  nodes?:         CosifNode[]
}

export function ReconStatusCard({ reconciliacao, nodes }: ReconStatusCardProps) {
  if (!reconciliacao) {
    return (
      <section className="rounded border border-gray-200 bg-white px-4 py-3 dark:border-gray-800 dark:bg-gray-950">
        <p className="text-[12px] text-gray-500 dark:text-gray-400">
          Reconciliação indisponível para esta data.
        </p>
      </section>
    )
  }

  const tone = computeTone(reconciliacao)
  const meta = TONE_META[tone]
  const Icon = meta.icon

  const deltaAtivo   = sumLevel1(nodes, 1)
  const deltaPassivo = sumLevel1(nodes, 4)
  const deltaPL      = reconciliacao.delta_pl_total
  const deltaCotas   = reconciliacao.delta_cotas_sr + reconciliacao.delta_cotas_mez

  return (
    <section
      className={cx(
        "flex flex-wrap items-center gap-x-5 gap-y-3 rounded border px-4 py-3",
        "border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
      )}
    >
      <div className="flex items-center gap-3">
        <span
          className={cx(
            "inline-flex size-8 shrink-0 items-center justify-center rounded",
            meta.bgCls,
          )}
        >
          <Icon className={cx("size-4", meta.iconCls)} aria-hidden="true" />
        </span>
        <div>
          <div className="text-[13px] font-semibold text-gray-900 dark:text-gray-50">
            {meta.headline}
          </div>
          <div className="text-[11.5px] text-gray-500 dark:text-gray-400">
            Δ Real {fmtBRLSigned(reconciliacao.delta_pl_cota_sub_real)} · Δ Esperado{" "}
            {fmtBRLSigned(reconciliacao.delta_pl_cota_sub_esperado)} · resíduo{" "}
            <span className={cx(
              "tabular-nums",
              tone === "ok"   && "text-emerald-700 dark:text-emerald-400",
              tone === "warn" && "text-amber-700 dark:text-amber-400",
              tone === "error" && "text-red-700 dark:text-red-400",
            )}>
              {fmtBRLSigned(reconciliacao.residuo)}
            </span>
          </div>
        </div>
      </div>

      <div className="ml-auto flex flex-wrap items-center gap-x-5 gap-y-2">
        <Stat label="ΔAtivo"        value={deltaAtivo} />
        <Stat label="ΔPassivo"      value={deltaPassivo} />
        <Stat label="ΔPL"           value={deltaPL} />
        <Stat label="ΔCotas Sr/Mez" value={deltaCotas} />
      </div>
    </section>
  )
}

function Stat({ label, value }: { label: string; value: number }) {
  const cls =
    value > 0 ? "text-emerald-700 dark:text-emerald-400"
    : value < 0 ? "text-rose-700 dark:text-rose-400"
    : "text-gray-600 dark:text-gray-400"
  return (
    <div className="text-right">
      <div className="text-[10px] font-medium uppercase tracking-[0.04em] text-gray-500 dark:text-gray-400">
        {label}
      </div>
      <div className={cx("text-[12px] font-semibold tabular-nums", cls)}>
        {fmtBRLk(value)}
      </div>
    </div>
  )
}

function fmtBRLSigned(v: number): string {
  return `${v > 0 ? "+" : ""}${fmtBRL.format(v)}`
}

function computeTone(r: Reconciliacao): Tone {
  if (!r.pl_cota_sub_d1) return "ok"
  const pp = Math.abs(r.residuo) / Math.abs(r.pl_cota_sub_d1)
  if (pp <= 0.001) return "ok"
  if (pp <= 0.01)  return "warn"
  return "error"
}

/** Soma deltas de nodes nivel 1 de um grupo COSIF (1=Ativo, 4=Passivo, 6=PL, 8=Despesa). */
function sumLevel1(nodes: CosifNode[] | undefined, grupo: number): number {
  if (!nodes) return 0
  return nodes
    .filter((n) => n.nivel === 1 && n.grupo === grupo)
    .reduce((acc, n) => acc + n.delta, 0)
}
