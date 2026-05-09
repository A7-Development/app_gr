// src/design-system/components/ConcentracaoDeltaCard/index.tsx
//
// Card de Concentracao para a Aba Mes Corrente da operacoes2.
//
// Mostra HHI delta + top-3 share + lista compacta de gainers/losers de share
// entre o periodo anterior e o atual. Diferente dos outros cards de
// decomposicao, este nao tem chart — eh um card de stats + lista.

"use client"

import * as React from "react"
import { RiArrowUpLine, RiArrowDownLine } from "@remixicon/react"

import { Card } from "@/components/tremor/Card"
import { cardTokens } from "@/design-system/tokens/card"
import { cx } from "@/lib/utils"
import type {
  Operacoes2ConcentracaoDeltaData,
  Operacoes2ConcentracaoMovement,
} from "@/lib/api-client"

const fmtPct1 = (v: number) => `${v.toFixed(1).replace(".", ",")}%`
const fmtPctSigned = (v: number) =>
  `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(1).replace(".", ",")}pp`
const fmtHhi = (v: number) => v.toFixed(0)

function MovementRow({
  movement,
  direction,
}: {
  movement: Operacoes2ConcentracaoMovement
  direction: "up" | "down"
}) {
  const Icon = direction === "up" ? RiArrowUpLine : RiArrowDownLine
  const colorClass =
    direction === "up"
      ? "text-emerald-600 dark:text-emerald-400"
      : "text-red-600 dark:text-red-400"
  return (
    <li className="flex items-center justify-between gap-3 py-1">
      <div className="flex min-w-0 items-center gap-2">
        <Icon className={cx("size-3.5 shrink-0", colorClass)} aria-hidden="true" />
        <span className="truncate text-xs text-gray-700 dark:text-gray-300">
          {movement.member_label}
        </span>
      </div>
      <div className="flex shrink-0 items-baseline gap-2">
        <span className="text-[11px] text-gray-500 dark:text-gray-500">
          {fmtPct1(movement.prior_share_pct)} → {fmtPct1(movement.current_share_pct)}
        </span>
        <span className={cx("text-xs font-medium tabular-nums", colorClass)}>
          {fmtPctSigned(movement.delta_share_pp)}
        </span>
      </div>
    </li>
  )
}

export interface ConcentracaoDeltaCardProps {
  data: Operacoes2ConcentracaoDeltaData
  title?: string
  caption?: string
  footer?: React.ReactNode
  actions?: React.ReactNode
  className?: string
}

export function ConcentracaoDeltaCard({
  data,
  title = "Concentração",
  caption,
  footer,
  actions,
  className,
}: ConcentracaoDeltaCardProps) {
  const autoCaption =
    caption ??
    `${data.dimension_label} · ${data.prior_anchor_label} → ${data.current_anchor_label}`

  const top3DeltaPositive = data.delta_top_3_pp >= 0
  const hhiDeltaPositive = data.delta_hhi >= 0

  return (
    <Card className={cx("p-0", className)}>
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className={cardTokens.header + " w-full"}>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className={cardTokens.headerTitle}>{title}</h3>
              <p className={cx(cardTokens.headerSubtitle, "mt-0.5")}>
                {autoCaption}
              </p>
            </div>
            {actions && (
              <div className="flex shrink-0 items-center gap-2">{actions}</div>
            )}
          </div>
        </div>
      </div>

      {/* Stats grid: HHI + Top-3 share */}
      <div className={cx(cardTokens.body, "grid grid-cols-2 gap-4")}>
        <div>
          <p className="text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-500">
            HHI
          </p>
          <p className="mt-1 text-2xl font-semibold tabular-nums text-gray-900 dark:text-gray-50">
            {fmtHhi(data.hhi_current)}
          </p>
          <p
            className={cx(
              "mt-0.5 text-xs tabular-nums",
              hhiDeltaPositive
                ? "text-red-600 dark:text-red-400"
                : "text-emerald-600 dark:text-emerald-400",
            )}
            title="HHI subindo = mais concentrado"
          >
            {data.delta_hhi >= 0 ? "+" : "−"}
            {Math.abs(data.delta_hhi).toFixed(0)} vs {data.prior_anchor_label}
          </p>
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-500">
            Top-3 share
          </p>
          <p className="mt-1 text-2xl font-semibold tabular-nums text-gray-900 dark:text-gray-50">
            {fmtPct1(data.top_3_share_current)}
          </p>
          <p
            className={cx(
              "mt-0.5 text-xs tabular-nums",
              top3DeltaPositive
                ? "text-red-600 dark:text-red-400"
                : "text-emerald-600 dark:text-emerald-400",
            )}
          >
            {fmtPctSigned(data.delta_top_3_pp)} vs {data.prior_anchor_label}
          </p>
        </div>
      </div>

      {/* Movements list */}
      <div className={cx(cardTokens.body, "border-t border-gray-100 dark:border-gray-900 pt-3")}>
        {data.movements_gainers.length === 0 && data.movements_losers.length === 0 ? (
          <p className="py-4 text-center text-xs text-gray-400 dark:text-gray-600">
            Sem movimentos relevantes de share entre os períodos.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-3">
            {data.movements_gainers.length > 0 && (
              <div>
                <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-500">
                  Ganharam share
                </p>
                <ul className="divide-y divide-gray-100 dark:divide-gray-900">
                  {data.movements_gainers.map((m) => (
                    <MovementRow
                      key={`gain-${m.member_id}`}
                      movement={m}
                      direction="up"
                    />
                  ))}
                </ul>
              </div>
            )}
            {data.movements_losers.length > 0 && (
              <div>
                <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-500">
                  Perderam share
                </p>
                <ul className="divide-y divide-gray-100 dark:divide-gray-900">
                  {data.movements_losers.map((m) => (
                    <MovementRow
                      key={`loss-${m.member_id}`}
                      movement={m}
                      direction="down"
                    />
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>

      {footer && <div className={cardTokens.footer}>{footer}</div>}
    </Card>
  )
}
