"use client"

/**
 * NaoReconhecidosPanel — detector de itens nao reconhecidos (2026-05-27, pos-VCNC).
 *
 * Cada driver da pagina classifica/filtra suas fontes por heuristica. Quando a
 * QiTech publica um valor NOVO num campo de classificacao, o item vaza pro
 * residuo (vaza_residuo), entra num driver indevidamente (entra_indevido) ou e
 * exposto pra auditoria (vigia). A VCNC (nota comercial vencida) ficou +44k
 * invisivel por 93 dias antes de ser pega no olho — este painel torna o miss
 * barulhento no dia 1.
 *
 * Estados:
 *   - vaza_residuo / entra_indevido presente -> vermelho (bug: algo saiu/entrou errado)
 *   - so vigia                               -> info (informacional, conferir)
 *   - vazio                                  -> verde compacto (tudo classificado)
 */

import * as React from "react"
import {
  RiCheckboxCircleLine,
  RiErrorWarningLine,
  RiEyeLine,
} from "@remixicon/react"

import { cx } from "@/lib/utils"
import { Card } from "@/components/tremor/Card"
import { Badge } from "@/components/tremor/Badge"
import type { ItemNaoReconhecido, NaoReconhecidoModo } from "@/lib/api-client"

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency", currency: "BRL",
  minimumFractionDigits: 2, maximumFractionDigits: 2,
})

const MODO_LABEL: Record<NaoReconhecidoModo, string> = {
  vaza_residuo:  "Vaza p/ resíduo",
  entra_indevido: "Entra indevido",
  vigia:         "Vigília",
}

const MODO_BADGE: Record<NaoReconhecidoModo, "error" | "warning" | "neutral"> = {
  vaza_residuo:  "error",
  entra_indevido: "warning",
  vigia:         "neutral",
}

type Tone = "green" | "info" | "red"

const TONE_STYLES: Record<Tone, { card: string; icon: React.ElementType; iconCls: string; label: string }> = {
  green: {
    card:    "border-emerald-200 bg-emerald-50/60 dark:border-emerald-900/40 dark:bg-emerald-500/5",
    icon:    RiCheckboxCircleLine,
    iconCls: "text-emerald-600 dark:text-emerald-400",
    label:   "Todas as fontes classificadas",
  },
  info: {
    card:    "border-gray-200 bg-gray-50/60 dark:border-gray-800 dark:bg-gray-900/40",
    icon:    RiEyeLine,
    iconCls: "text-blue-600 dark:text-blue-400",
    label:   "Itens em vigília",
  },
  red: {
    card:    "border-red-200 bg-red-50/60 dark:border-red-900/40 dark:bg-red-500/5",
    icon:    RiErrorWarningLine,
    iconCls: "text-red-600 dark:text-red-400",
    label:   "Itens não reconhecidos vazando da decomposição",
  },
}

export type NaoReconhecidosPanelProps = {
  itens?:   ItemNaoReconhecido[]
  loading?: boolean
}

export function NaoReconhecidosPanel({ itens, loading }: NaoReconhecidosPanelProps) {
  if (loading || itens === undefined) {
    return (
      <Card className="flex flex-col gap-2 p-3">
        <div className="h-4 w-40 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
        <div className="h-3 w-64 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
      </Card>
    )
  }

  const temBug = itens.some((i) => i.modo === "vaza_residuo" || i.modo === "entra_indevido")
  const somaVaza = itens
    .filter((i) => i.modo === "vaza_residuo")
    .reduce((acc, i) => acc + Math.abs(i.valor_d0), 0)

  const tone: Tone = temBug ? "red" : itens.length > 0 ? "info" : "green"
  const styles = TONE_STYLES[tone]
  const Icon = styles.icon

  // Estado verde: confirmacao compacta de 1 linha (detector rodou, nada vazou).
  if (tone === "green") {
    return (
      <Card className={cx("flex items-center gap-2.5 p-3 border", styles.card)}>
        <Icon className={cx("size-4 shrink-0", styles.iconCls)} />
        <span className="text-xs text-gray-700 dark:text-gray-300">
          {styles.label} — nenhum valor caiu fora da decomposição.
        </span>
      </Card>
    )
  }

  return (
    <Card className={cx("flex flex-col gap-3 p-4 border", styles.card)}>
      <div className="flex items-start gap-3">
        <Icon className={cx("size-5 shrink-0", styles.iconCls)} />
        <div className="flex flex-col gap-1">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
            {styles.label}
          </h3>
          <p className="text-xs text-gray-600 dark:text-gray-400">
            {temBug ? (
              <>
                <strong>{itens.filter((i) => i.modo !== "vigia").length}</strong> item(ns)
                {" "}com impacto no modelo
                {somaVaza > 0.005 && (
                  <> · Σ vazando p/ resíduo: <strong>{fmtBRL.format(somaVaza)}</strong></>
                )}
                . Adicione regra/override para reclassificar.
              </>
            ) : (
              <>
                <strong>{itens.length}</strong> item(ns) em vigília — reconhecidos hoje,
                {" "}mas em campo heurístico. Conferir se a contraparte está capturada.
              </>
            )}
          </p>
        </div>
      </div>

      <div className="rounded border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950">
        <ul className="divide-y divide-gray-100 dark:divide-gray-800">
          {itens.map((i, idx) => (
            <li
              key={`${i.fonte}:${i.identificador}:${idx}`}
              className="flex items-start justify-between gap-3 px-3 py-2 text-xs"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <Badge variant={MODO_BADGE[i.modo]} className="shrink-0">
                    {MODO_LABEL[i.modo]}
                  </Badge>
                  <span className="truncate font-medium text-gray-900 dark:text-gray-50">
                    {i.label}
                  </span>
                </div>
                <div className="mt-0.5 truncate font-mono text-[10px] text-gray-500 dark:text-gray-400">
                  {i.fonte} · {i.campo} → {i.driver_afetado}
                </div>
                <div className="mt-0.5 text-[11px] text-gray-500 dark:text-gray-400">
                  {i.motivo}
                </div>
              </div>
              <span className="shrink-0 pt-0.5 text-right font-mono tabular-nums text-gray-700 dark:text-gray-300">
                {fmtBRL.format(i.valor_d0)}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </Card>
  )
}
