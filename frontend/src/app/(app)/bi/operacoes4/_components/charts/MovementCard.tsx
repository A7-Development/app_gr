// src/app/(app)/bi/operacoes4/_components/charts/MovementCard.tsx
//
// L5 lateral — card compacto para movimentos do mes:
//   - eyebrow uppercase (ex.: "NOVOS NO MÊS")
//   - count grande (ex.: "8")
//   - lista de ate 3 itens (label primario + valor + delta opcional)
//   - caption opcional ao final (ex.: "+5 cedentes não exibidos")
//
// Usado em 3x na coluna direita da L5 (Novos / Sumidos / Top Movers).
// Composicao stack vertical (flex-1) gerenciada pelo caller — este
// componente nao define altura.

"use client"

import * as React from "react"

import { Card } from "@/components/tremor/Card"
import { cx } from "@/lib/utils"
import { cardTokens } from "@/design-system/tokens/card"

export interface MovementItem {
  primaryLabel: string
  valueLabel: string
  /** Delta opcional (ex.: "+18%"). */
  deltaLabel?: string
  /** Tom da cor do delta. Default: "neu" (cinza). */
  tone?: "pos" | "neg" | "neu"
}

export interface MovementCardProps {
  eyebrow: string
  count: number
  items: MovementItem[]
  /** Texto pequeno no final do card (ex.: "+5 ocultos"). */
  caption?: string
  /** Callback opcional quando o card e clicado (PR4 drill). */
  onClick?: () => void
  className?: string
}

function toneClass(tone: MovementItem["tone"] = "neu"): string {
  switch (tone) {
    case "pos":
      return "text-emerald-600 dark:text-emerald-400"
    case "neg":
      return "text-red-600 dark:text-red-400"
    default:
      return "text-gray-600 dark:text-gray-300"
  }
}

export function MovementCard({
  eyebrow,
  count,
  items,
  caption,
  onClick,
  className,
}: MovementCardProps) {
  const interactive = typeof onClick === "function"
  return (
    <Card
      asChild={interactive}
      className={cx(
        cardTokens.body,
        "flex flex-col gap-2",
        interactive &&
          "cursor-pointer transition-colors hover:border-blue-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500",
        className,
      )}
    >
      {interactive ? (
        <button
          type="button"
          onClick={onClick}
          className="w-full text-left"
        >
          <MovementCardInner
            eyebrow={eyebrow}
            count={count}
            items={items}
            caption={caption}
          />
        </button>
      ) : (
        <MovementCardInner
          eyebrow={eyebrow}
          count={count}
          items={items}
          caption={caption}
        />
      )}
    </Card>
  )
}

function MovementCardInner({
  eyebrow,
  count,
  items,
  caption,
}: {
  eyebrow: string
  count: number
  items: MovementItem[]
  caption?: string
}) {
  return (
    <>
      <div>
        <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
          {eyebrow}
        </p>
        <p className="mt-1 text-2xl font-semibold leading-none tabular-nums text-gray-900 dark:text-gray-50">
          {count.toLocaleString("pt-BR")}
        </p>
      </div>

      {items.length === 0 ? (
        <p className="mt-1 text-[11px] italic text-gray-400 dark:text-gray-600">
          Nenhum cedente nesta categoria.
        </p>
      ) : (
        <ul className="mt-1 flex flex-col gap-1.5">
          {items.slice(0, 3).map((it, idx) => (
            <li
              key={`${it.primaryLabel}-${idx}`}
              className="flex items-center justify-between gap-2 text-[12px]"
            >
              <span className="truncate text-gray-900 dark:text-gray-100">
                {it.primaryLabel}
              </span>
              <span className="flex shrink-0 items-baseline gap-1.5 tabular-nums">
                <span className={cx("font-medium", toneClass(it.tone))}>
                  {it.valueLabel}
                </span>
                {it.deltaLabel && (
                  <span
                    className={cx("text-[10.5px]", toneClass(it.tone))}
                  >
                    {it.deltaLabel}
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}

      {caption && (
        <p className="mt-auto pt-1 text-[10.5px] text-gray-500 dark:text-gray-400">
          {caption}
        </p>
      )}
    </>
  )
}
