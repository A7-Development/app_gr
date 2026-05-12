"use client"

/**
 * ResiduoAlertCard — Z4 da pagina Cota Sub.
 *
 * Sintetiza saude da reconciliacao + cobertura COSIF:
 *
 *   verde  : residuo <= 0,1pp E sem pendentes (0 rows pendentes)
 *   ambar  : residuo entre 0,1pp e 1pp, OU pendentes < 5% do total
 *   vermelho: residuo > 1pp OU pendentes >= 5%
 *
 * Quando ambar/vermelho, lista top-N pendentes ordenados por |valor|
 * com sugestao de override no /admin/cosif (link futuro).
 */

import * as React from "react"
import {
  RiAlertLine,
  RiCheckboxCircleLine,
  RiErrorWarningLine,
} from "@remixicon/react"

import { cx } from "@/lib/utils"
import { Card } from "@/components/tremor/Card"
import type { Cobertura, Reconciliacao } from "@/lib/api-client"

// Tolerancia alinhada com ReconciliacaoWaterfallCard
const TOL_PP_OK    = 0.001  // 0,1pp
const TOL_PP_AMBER = 0.01   // 1pp
const PENDENTE_PCT_AMBER = 0.0  // qualquer pendente vira ambar
const PENDENTE_PCT_RED   = 0.05 // pendente >= 5% vira vermelho

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency", currency: "BRL",
  minimumFractionDigits: 2, maximumFractionDigits: 2,
})

const fmtBRLCompact = new Intl.NumberFormat("pt-BR", {
  style: "currency", currency: "BRL",
  notation: "compact", maximumFractionDigits: 2,
})

const fmtPct = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2, maximumFractionDigits: 2,
})

type Tone = "green" | "amber" | "red"

function classifyTone(
  residuoPp: number,
  pendentesPct: number,
): Tone {
  if (residuoPp > TOL_PP_AMBER || pendentesPct >= PENDENTE_PCT_RED) return "red"
  if (residuoPp > TOL_PP_OK || pendentesPct > PENDENTE_PCT_AMBER) return "amber"
  return "green"
}

const TONE_STYLES: Record<Tone, { card: string; icon: React.ElementType; iconCls: string; label: string }> = {
  green: {
    card:    "border-emerald-200 bg-emerald-50/60 dark:border-emerald-900/40 dark:bg-emerald-500/5",
    icon:    RiCheckboxCircleLine,
    iconCls: "text-emerald-600 dark:text-emerald-400",
    label:   "Balancete conciliado",
  },
  amber: {
    card:    "border-amber-200 bg-amber-50/60 dark:border-amber-900/40 dark:bg-amber-500/5",
    icon:    RiAlertLine,
    iconCls: "text-amber-600 dark:text-amber-400",
    label:   "Atencao — verificar pendentes",
  },
  red: {
    card:    "border-red-200 bg-red-50/60 dark:border-red-900/40 dark:bg-red-500/5",
    icon:    RiErrorWarningLine,
    iconCls: "text-red-600 dark:text-red-400",
    label:   "Reconciliacao com divergencia",
  },
}

export type ResiduoAlertCardProps = {
  reconciliacao?: Reconciliacao
  cobertura?:     Cobertura
  /** Limite de pendentes listados. */
  topN?:          number
}

export function ResiduoAlertCard({
  reconciliacao,
  cobertura,
  topN = 5,
}: ResiduoAlertCardProps) {
  if (!reconciliacao || !cobertura) {
    return (
      <Card className="flex flex-col gap-2 p-3">
        <div className="h-4 w-32 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
        <div className="h-3 w-64 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
      </Card>
    )
  }

  const residuoPp =
    reconciliacao.pl_cota_sub_d1 !== 0
      ? Math.abs(reconciliacao.residuo) / Math.abs(reconciliacao.pl_cota_sub_d1)
      : 0

  const pendentesCount = cobertura.rows_por_source.pendente ?? 0
  const pendentesPct = cobertura.total_rows > 0
    ? pendentesCount / cobertura.total_rows
    : 0

  const tone = classifyTone(residuoPp, pendentesPct)
  const styles = TONE_STYLES[tone]
  const Icon = styles.icon

  return (
    <Card className={cx("flex flex-col gap-3 p-4 border", styles.card)}>
      <div className="flex items-start gap-3">
        <Icon className={cx("size-5 shrink-0", styles.iconCls)} />
        <div className="flex flex-col gap-1">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
            {styles.label}
          </h3>
          <p className="text-xs text-gray-600 dark:text-gray-400">
            Residuo: <strong>{fmtBRL.format(reconciliacao.residuo)}</strong>
            {" "}({fmtPct.format(residuoPp * 100)} pp do PL Sub) ·
            {" "}Cobertura: <strong>{fmtPct.format((1 - pendentesPct) * 100)}%</strong>
            {" "}({pendentesCount} rows pendentes de {cobertura.total_rows})
          </p>
        </div>
      </div>

      {tone !== "green" && cobertura.top_pendentes.length > 0 && (
        <div className="rounded border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950">
          <div className="border-b border-gray-200 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:border-gray-800 dark:text-gray-400">
            Top {Math.min(topN, cobertura.top_pendentes.length)} pendentes por |valor|
          </div>
          <ul className="divide-y divide-gray-100 dark:divide-gray-800">
            {cobertura.top_pendentes.slice(0, topN).map((p, i) => (
              <li
                key={`${p.silver_origin}:${p.identificador}:${i}`}
                className="flex items-center justify-between gap-3 px-3 py-1.5 text-xs"
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium text-gray-900 dark:text-gray-50">
                    {p.identificador || "(sem identificador)"}
                  </div>
                  <div className="truncate font-mono text-[10px] text-gray-500 dark:text-gray-400">
                    {p.silver_origin}
                  </div>
                </div>
                <span className="shrink-0 font-mono tabular-nums text-gray-700 dark:text-gray-300">
                  {fmtBRLCompact.format(p.valor)}
                </span>
              </li>
            ))}
          </ul>
          <div className="border-t border-gray-200 px-3 py-1.5 text-[11px] text-gray-500 dark:border-gray-800 dark:text-gray-400">
            Crie overrides em <span className="font-mono">/admin/controladoria/cosif</span> para classificar.
          </div>
        </div>
      )}
    </Card>
  )
}
