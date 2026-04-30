// src/design-system/components/AIQuotaIndicator/index.tsx
//
// AIQuotaIndicator — saldo mensal de creditos de IA do tenant.
// Use no rodape da sidebar (variant="compact") ou dentro do header
// do <AIPanel /> (variant="strip").
//
// Dependencias: usa apenas tokens da paleta gray + amber + red (paleta
// canonica §4 + uso de amber permitido durante modo iteracao §STATUS).

"use client"

import * as React from "react"
import { RiSparkling2Line, RiAlertLine } from "@remixicon/react"

import { cx } from "@/lib/utils"
import type { AIQuota } from "@/lib/api-client"

export type AIQuotaIndicatorProps = {
  quota: AIQuota | undefined
  loading?: boolean
  variant?: "compact" | "strip"
  className?: string
}

function pct(quota: AIQuota): number {
  const total = quota.granted + quota.carryover + quota.topup
  if (total <= 0) return 100
  return Math.min(100, Math.round((quota.consumed / total) * 100))
}

function tone(usagePct: number): "ok" | "warn" | "danger" {
  if (usagePct >= 90) return "danger"
  if (usagePct >= 75) return "warn"
  return "ok"
}

const TONE_CLASSES: Record<
  "ok" | "warn" | "danger",
  { fill: string; text: string; icon: string }
> = {
  ok: {
    fill: "bg-violet-500 dark:bg-violet-400",
    text: "text-gray-700 dark:text-gray-300",
    icon: "text-violet-500 dark:text-violet-400",
  },
  warn: {
    fill: "bg-amber-500 dark:bg-amber-400",
    text: "text-amber-700 dark:text-amber-400",
    icon: "text-amber-500 dark:text-amber-400",
  },
  danger: {
    fill: "bg-red-500 dark:bg-red-400",
    text: "text-red-700 dark:text-red-400",
    icon: "text-red-600 dark:text-red-400",
  },
}

export function AIQuotaIndicator({
  quota,
  loading,
  variant = "compact",
  className,
}: AIQuotaIndicatorProps) {
  if (loading || !quota) {
    return (
      <div
        className={cx(
          "flex items-center gap-2 rounded px-2.5 py-1.5",
          "bg-gray-50 dark:bg-gray-900",
          "text-[11px] text-gray-500 dark:text-gray-400",
          className,
        )}
        aria-label="Saldo IA carregando"
      >
        <RiSparkling2Line className="size-3 animate-pulse" aria-hidden="true" />
        <span>Saldo IA…</span>
      </div>
    )
  }

  const usage = pct(quota)
  const t = tone(usage)
  const classes = TONE_CLASSES[t]
  const totalAvailable = quota.granted + quota.carryover + quota.topup

  if (variant === "strip") {
    return (
      <div
        className={cx(
          "flex flex-col gap-1 rounded border px-2.5 py-2",
          "border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900",
          className,
        )}
      >
        <div className="flex items-center justify-between text-[10px]">
          <span className="font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
            Saldo IA
          </span>
          <span className={cx("font-mono tabular-nums", classes.text)}>
            {quota.remaining.toLocaleString("pt-BR")} / {totalAvailable.toLocaleString("pt-BR")}
          </span>
        </div>
        <div className="h-1 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-800">
          <div
            className={cx("h-full transition-all", classes.fill)}
            style={{ width: `${usage}%` }}
            aria-hidden="true"
          />
        </div>
        {t !== "ok" && (
          <div className={cx("flex items-center gap-1 text-[10px]", classes.text)}>
            <RiAlertLine className="size-3" aria-hidden="true" />
            <span>
              {t === "danger"
                ? "Saldo critico — top-up recomendado."
                : "Atencao: saldo abaixo de 25%."}
            </span>
          </div>
        )}
      </div>
    )
  }

  // compact (default): 1 linha
  return (
    <div
      className={cx(
        "inline-flex items-center gap-2 rounded px-2.5 py-1",
        "border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
        "text-[11px]",
        className,
      )}
      title={`Saldo IA: ${quota.remaining.toLocaleString("pt-BR")} de ${totalAvailable.toLocaleString("pt-BR")} creditos (${quota.period_yyyymm})`}
    >
      <RiSparkling2Line className={cx("size-3 shrink-0", classes.icon)} aria-hidden="true" />
      <span className={cx("font-mono tabular-nums", classes.text)}>
        {quota.remaining.toLocaleString("pt-BR")}
      </span>
      <span className="text-gray-500 dark:text-gray-400">creditos IA</span>
    </div>
  )
}
