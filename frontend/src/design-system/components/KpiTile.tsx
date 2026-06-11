// src/design-system/components/KpiTile.tsx
//
// KpiTile — card de KPI CANONICO Strata (decisao Ricardo 2026-06-12).
//
// Referencia visual: header do "VARIAÇÃO DIÁRIA DA COTA" da cota-sub
// (EvolucaoDiariaCard/EChartsCard `headerKpi`) — a anatomia nasceu la e a
// operacoes4 herdou ("header KPI 3 linhas"):
//
//   EYEBROW   11px · medium · UPPERCASE · tracking 0.05em · gray-500
//   VALOR     20px · semibold · tabular-nums · gray-900 (+ delta inline)
//   CAPTION   11px · gray-500 · CURTA (2-4 palavras: "vs mês anterior")
//
// QUANDO USAR:
//   - KPI que NAO tem grafico dono na pagina -> KpiTile (cards individuais
//     em grid, ex.: `grid gap-4 sm:grid-cols-2 xl:grid-cols-5`).
//   - KPI cujo numero E de um grafico da pagina -> `headerKpi` do
//     EChartsCard/EvolucaoDiariaCard (MESMA anatomia, dentro do card do
//     chart). Nunca duplicar o numero nos dois lugares.
//
// QUANDO NAO USAR:
//   - Series/sparklines no proprio KPI -> isso e um chart, use EChartsCard.
//   - "Metricas Complementares" densas -> KpiCard variant="compact" (handoff).
//   - Caption longa/explicativa -> a explicacao pertence ao `info` do
//     PageHeader; caption do tile e contexto telegrafico.

import * as React from "react"
import { RiArrowDownLine, RiArrowUpLine } from "@remixicon/react"

import { cx } from "@/lib/utils"
import { Card } from "@/components/tremor/Card"

export type KpiTileDelta = {
  /** Valor numerico do delta (sinal define a seta quando `direction` ausente). */
  value: number
  /** Sufixo apos o numero (ex.: "%", " p.p."). */
  suffix?: string
  /** Forca a direcao da seta (default: sinal de `value`). */
  direction?: "up" | "down"
  /**
   * Semantica de cor: `true` = verde, `false` = vermelho.
   * Default: subir e bom (`direction === "up"`). Para metricas onde subir e
   * RUIM (inadimplencia, custo), passe `good` explicitamente.
   */
  good?: boolean
  /** Casas decimais (default 0..2 conforme valor). */
  fractionDigits?: number
}

export type KpiTileProps = {
  /** Eyebrow do tile (renderiza em UPPERCASE — passe pt-BR normal). */
  label: string
  /** Numero principal PRE-FORMATADO (ex.: "R$ 1,2 mi", "3,2%", "32 d"). */
  value: string
  /** Delta opcional, inline ao lado do valor. */
  delta?: KpiTileDelta
  /** Texto curto apos o delta (ex.: "vs mês anterior", "MTD"). */
  deltaSub?: string
  /** Caption da 3a linha — contexto telegrafico (2-4 palavras). */
  caption?: string
  className?: string
}

export function KpiTile({
  label,
  value,
  delta,
  deltaSub,
  caption,
  className,
}: KpiTileProps) {
  const dir = delta?.direction ?? (delta && delta.value >= 0 ? "up" : "down")
  const good = delta?.good ?? dir === "up"
  const ArrowIcon = dir === "up" ? RiArrowUpLine : RiArrowDownLine
  const deltaColor = good
    ? "text-emerald-600 dark:text-emerald-400"
    : "text-red-600 dark:text-red-400"

  return (
    <Card className={cx("px-4 py-3", className)}>
      <p className="truncate text-[11px] font-medium uppercase leading-tight tracking-[0.05em] text-gray-500 dark:text-gray-400">
        {label}
      </p>
      <p className="mt-1 flex flex-wrap items-baseline gap-x-2 tabular-nums">
        <span className="text-[20px] font-semibold leading-none tracking-tight text-gray-900 dark:text-gray-50">
          {value}
        </span>
        {delta && (
          <span
            className={cx(
              "inline-flex items-baseline whitespace-nowrap text-xs font-medium",
              deltaColor,
            )}
          >
            <ArrowIcon
              className="mr-0.5 inline size-3 shrink-0 align-[-0.125em]"
              aria-hidden="true"
            />
            {Math.abs(delta.value).toLocaleString("pt-BR", {
              minimumFractionDigits: delta.fractionDigits ?? 0,
              maximumFractionDigits: delta.fractionDigits ?? 2,
            })}
            {delta.suffix ?? ""}
          </span>
        )}
        {deltaSub && (
          <span className="text-[11px] text-gray-500 dark:text-gray-400">
            {deltaSub}
          </span>
        )}
      </p>
      {caption && (
        <p className="mt-1 truncate text-[11px] text-gray-500 dark:text-gray-400">
          {caption}
        </p>
      )}
    </Card>
  )
}
