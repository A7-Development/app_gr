"use client"

/**
 * KpiBand — banda horizontal de N KPIs equivalentes em linha unica.
 *
 * Anatomia (2 linhas de texto por coluna, banda contínua):
 *
 *   ┌──────────────┬──────────────┬──────────────┬──────────────┐
 *   │ EYEBROW · MES│ EYEBROW · MES│ EYEBROW · MES│ EYEBROW · MES│
 *   │ R$ 22,47 mi  │ R$ 22,47 mi  │ R$ 22,47 mi  │ R$ 22,47 mi  │
 *   │ +6,95% sub   │ +6,95% sub   │ +6,95% sub   │ +6,95% sub   │
 *   └──────────────┴──────────────┴──────────────┴──────────────┘
 *                ↑              ↑              ↑
 *          divider parcial (top-3 bottom-3, w-px, gray-100)
 *
 * O divider entre colunas e PARCIAL — top e bottom recuados ~12px pra
 * comunicar separacao sem "rachar" a banda. Cor `gray-100` em light /
 * `gray-800` em dark (mais sutil que `border-l` padrao).
 *
 * O `value` e SEMPRE neutro (gray-900) — apenas o `delta` carrega cor.
 * Espelha a decisao Ricardo 2026-05-21 aplicada ao KpiHeadline.
 *
 * ── Quando usar ───────────────────────────────────────────────────────
 *   - N KPIs equivalentes (sem hierarquia entre eles) que precisam ser
 *     vistos juntos em vista panoramica. Ex.: VOP / Receita / Taxa / Prazo
 *     do mes corrente.
 *   - Densidade > KpiStrip (que e 3 linhas por card) mas N > 1, descartando
 *     KpiHeadline (que e 1 dominante + chips).
 *
 * ── Quando NAO usar ───────────────────────────────────────────────────
 *   - 1 KPI dominante + outros viram diagnostico → use KpiHeadline.
 *   - 5+ KPIs com sparkline, intensity bars → use KpiStrip + KpiCard.
 *   - Pergunta dominante ("o que mudou hoje?") → use KpiHeadline.
 *
 * ── Responsivo ────────────────────────────────────────────────────────
 *   Mobile: empilha em coluna unica (flex-col), sem divider.
 *   md+:    banda horizontal com divider parcial entre colunas.
 */

import * as React from "react"

import { cx } from "@/lib/utils"
import { Card } from "@/components/tremor/Card"

export type KpiBandTone = "positive" | "negative" | "neutral"

const TONE_CLASS: Record<KpiBandTone, string> = {
  positive: "text-emerald-600 dark:text-emerald-400",
  negative: "text-red-600 dark:text-red-400",
  neutral:  "text-gray-500 dark:text-gray-400",
}

export type KpiBandItem = {
  /** Eyebrow uppercase (ex.: "MÊS CORRENTE · OPERAÇÕES · MAI/26"). */
  eyebrow: string
  /** Numero/string principal (ex.: "R$ 22,47 mi"). Renderiza neutro/preto. */
  value: string
  /**
   * Delta inline opcional renderizado depois do value, antes do `sub`.
   * Tone colore APENAS o delta (value continua neutro).
   */
  delta?: {
    value: string
    tone?: KpiBandTone
  }
  /** Texto secundario apos delta. Sempre gray. Ex.: "VOP-DU vs mês ant." */
  sub?: string
}

export interface KpiBandProps {
  items: KpiBandItem[]
  loading?: boolean
  className?: string
}

export function KpiBand({ items, loading = false, className }: KpiBandProps) {
  if (loading) {
    return (
      <Card className={cx("px-0 py-3", className)}>
        <div className="flex flex-col md:flex-row">
          {Array.from({ length: items.length || 4 }).map((_, i) => (
            <div key={i} className="flex-1 px-5 py-2 md:py-1">
              <div className="h-3 w-32 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
              <div className="mt-2 h-6 w-44 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
            </div>
          ))}
        </div>
      </Card>
    )
  }

  return (
    <Card className={cx("px-0 py-3", className)}>
      <div className="flex flex-col md:flex-row">
        {items.map((item, idx) => (
          <div
            key={`${item.eyebrow}-${idx}`}
            className="relative flex-1 px-5 py-2 md:py-1"
          >
            {/* Divider parcial — recua top/bottom pra nao "rachar" a banda.
                Hidden em mobile (cards empilhados). */}
            {idx > 0 && (
              <span
                aria-hidden
                className="absolute bottom-3 left-0 top-3 hidden w-px bg-gray-100 md:block dark:bg-gray-800"
              />
            )}

            <p className="text-[10px] font-medium uppercase tracking-[0.05em] leading-tight text-gray-500 dark:text-gray-400">
              {item.eyebrow}
            </p>

            <div className="mt-1 flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
              <span className="text-[22px] font-semibold leading-tight tabular-nums tracking-tight text-gray-900 dark:text-gray-50">
                {item.value}
              </span>
              {item.delta && (
                <span
                  className={cx(
                    "text-[12px] font-medium tabular-nums",
                    TONE_CLASS[item.delta.tone ?? "neutral"],
                  )}
                >
                  {item.delta.value}
                </span>
              )}
              {item.sub && (
                <span className="text-[12px] text-gray-500 dark:text-gray-400">
                  {item.sub}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}
