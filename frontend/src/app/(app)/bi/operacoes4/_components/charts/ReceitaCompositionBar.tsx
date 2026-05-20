// src/app/(app)/bi/operacoes4/_components/charts/ReceitaCompositionBar.tsx
//
// L3 esquerda — barra horizontal stacked 100% mostrando a composicao da
// receita MTD em 4 buckets. Renderizada em HTML puro (Tailwind + tokens)
// porque a primitiva e simples e nao justifica canvas ECharts. Tooltip
// inline (CSS `group-hover`) revela tipo + valor + share + delta.
//
// Cores: paleta canonica `tokens.colors.chart` — substitui o navy `#1B2B4B`
// do handoff original (decisao 2026-05-20 — CLAUDE.md §4.1 proibe brand em
// pagina autenticada). Quando o bucket carrega `flagAtypical`, aparece um
// dot amber discreto a direita do nome na legenda.
//
// Promove-se a design-system/components/ quando outra pagina consumir
// (CLAUDE.md §1, regra 4). Hoje vive aqui.

"use client"

import * as React from "react"

import { cx } from "@/lib/utils"
import { tokens } from "@/design-system/tokens"

export type ReceitaTipoLocal =
  | "desagio"
  | "tarifa_cessao"
  | "tarifas_operacionais"
  | "outras"

export interface ReceitaBucket {
  tipo: ReceitaTipoLocal
  label: string
  valor: number
  sharePct: number
  deltaPct: number | null
  flagAtypical?: boolean
}

export interface ReceitaCompositionBarProps {
  buckets: ReceitaBucket[]
  /** Altura da barra em px. Default 28. */
  height?: number
  /** Se true, esconde a legenda inline embaixo (so a barra). */
  hideLegend?: boolean
  /** Click numa linha da legenda (= drill por bucket). */
  onBucketClick?: (tipo: ReceitaTipoLocal) => void
  className?: string
}

// Paleta canonica — 4 primeiras cores de `tokens.colors.chart` cobrem os 4
// buckets. Ordem do enum (desagio dominante -> outras) ja casa com a ordem
// visual canonica de "principal -> periferico".
const BUCKET_COLOR: Record<ReceitaTipoLocal, string> = {
  desagio: tokens.colors.chart[0], // slate-500
  tarifa_cessao: tokens.colors.chart[1], // sky-500
  tarifas_operacionais: tokens.colors.chart[2], // teal-500
  outras: "#CBD5E1", // slate-300 — neutro pra placeholder "outras"
}

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 2,
})

function fmtPctSigned(v: number): string {
  const sign = v > 0 ? "+" : ""
  return `${sign}${v.toFixed(1).replace(".", ",")}%`
}

function fmtShare(v: number): string {
  return `${v.toFixed(1).replace(".", ",")}%`
}

export function ReceitaCompositionBar({
  buckets,
  height = 28,
  hideLegend = false,
  onBucketClick,
  className,
}: ReceitaCompositionBarProps) {
  // Soma pode nao bater 100% por arredondamento — normaliza visualmente
  // (cada flex-grow proporcional ao sharePct), nao re-escala valores.
  const total = buckets.reduce((acc, b) => acc + b.sharePct, 0) || 1

  return (
    <div className={cx("w-full", className)}>
      <div
        className="flex w-full overflow-hidden rounded"
        style={{ height }}
        role="img"
        aria-label="Composicao da receita MTD em 4 buckets"
      >
        {buckets.map((b) => {
          const widthPct = (b.sharePct / total) * 100
          if (widthPct <= 0) return null
          return (
            <div
              key={b.tipo}
              className="group relative"
              style={{
                width: `${widthPct}%`,
                background: BUCKET_COLOR[b.tipo],
              }}
              title={`${b.label}: ${fmtBRL.format(b.valor)} · ${fmtShare(b.sharePct)}`}
            >
              {/* Tooltip inline — revela no hover via group-hover */}
              <div
                className={cx(
                  "pointer-events-none absolute left-1/2 -top-2 z-10 -translate-x-1/2 -translate-y-full",
                  "rounded border bg-white px-2 py-1.5 text-[11px] shadow-lg",
                  "border-gray-200 dark:border-gray-800 dark:bg-gray-900",
                  "opacity-0 group-hover:opacity-100 transition-opacity",
                  "whitespace-nowrap",
                )}
              >
                <div className="font-medium text-gray-900 dark:text-gray-50">
                  {b.label}
                </div>
                <div className="mt-0.5 tabular-nums text-gray-600 dark:text-gray-300">
                  {fmtBRL.format(b.valor)} · {fmtShare(b.sharePct)}
                </div>
                {b.deltaPct !== null && (
                  <div
                    className={cx(
                      "mt-0.5 tabular-nums",
                      b.deltaPct >= 0
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-red-600 dark:text-red-400",
                    )}
                  >
                    {fmtPctSigned(b.deltaPct)} vs mês ant.
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {!hideLegend && (
        <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
          {buckets.map((b) => {
            const interactive = typeof onBucketClick === "function"
            const content = (
              <>
                <span
                  aria-hidden="true"
                  className="inline-block size-2 shrink-0 rounded-sm"
                  style={{ background: BUCKET_COLOR[b.tipo] }}
                />
                <span className="font-medium text-gray-900 dark:text-gray-100">
                  {b.label}
                </span>
                <span className="tabular-nums text-gray-500 dark:text-gray-400">
                  {fmtShare(b.sharePct)}
                </span>
                {b.flagAtypical && (
                  <span
                    aria-label="movimento atípico"
                    className="ml-0.5 inline-block size-1.5 rounded-full"
                    style={{ background: "#D97706" }}
                  />
                )}
              </>
            )
            return (
              <li key={b.tipo}>
                {interactive ? (
                  <button
                    type="button"
                    onClick={() => onBucketClick(b.tipo)}
                    className={cx(
                      "flex items-center gap-1.5 rounded px-1.5 py-0.5 text-[11px] text-gray-600 transition-colors",
                      "hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800",
                      "focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500",
                    )}
                  >
                    {content}
                  </button>
                ) : (
                  <span className="flex items-center gap-1.5 text-[11px] text-gray-600 dark:text-gray-300">
                    {content}
                  </span>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
