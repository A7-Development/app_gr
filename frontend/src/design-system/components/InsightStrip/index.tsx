// src/design-system/components/InsightStrip/index.tsx
//
// InsightStrip — barra slim (38px) de insight IA. Handoff bi-padrao A1b
// (2026-05-02). Usado entre a Toolbar unificada e o KpiStrip do
// DashboardBiPadrao.
//
// Anatomy (single line, h-[38px]):
//   [Sparkles] [ANALISE IA] | first.text (truncate) [+N analises] [X]
//
// Cor: violeta (semantica de IA — distinta do laranja `active-indicator`,
// que e funcional/filtro). Dismiss persistido em localStorage.
//
// API minima: passe `insights` (array com id+text). O primeiro renderiza
// inline; restantes ficam no Popover "+N analises".

"use client"

import * as React from "react"
import { RiSparkling2Line, RiCloseLine } from "@remixicon/react"
import { cx, focusRing } from "@/lib/utils"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/tremor/Popover"

export interface InsightStripItem {
  id:   string
  text: string
}

interface InsightStripProps {
  insights:    InsightStripItem[]
  /** Chave de localStorage para persistir dismissal. Default: "strata:insight-strip:dismissed". */
  storageKey?: string
  /** Callback opcional disparado quando o usuario fecha. */
  onDismiss?:  () => void
  className?:  string
}

const DEFAULT_STORAGE_KEY = "strata:insight-strip:dismissed"

export function InsightStrip({
  insights,
  storageKey = DEFAULT_STORAGE_KEY,
  onDismiss,
  className,
}: InsightStripProps) {
  const [dismissed, setDismissed] = React.useState<boolean>(false)

  React.useEffect(() => {
    if (typeof window === "undefined") return
    try {
      setDismissed(localStorage.getItem(storageKey) === "1")
    } catch {
      /* localStorage indisponivel — segue visivel */
    }
  }, [storageKey])

  if (dismissed || insights.length === 0) return null

  const [first, ...rest] = insights

  function handleDismiss() {
    setDismissed(true)
    try { localStorage.setItem(storageKey, "1") } catch { /* ignore */ }
    onDismiss?.()
  }

  return (
    <div
      className={cx(
        "flex h-[38px] items-center gap-2 rounded border px-3",
        "bg-violet-50 border-violet-100 dark:bg-violet-500/10 dark:border-violet-500/20",
        className,
      )}
      role="status"
      aria-label="Analise IA"
    >
      <RiSparkling2Line
        className="size-3.5 shrink-0 text-violet-600 dark:text-violet-400"
        aria-hidden="true"
      />
      <span className="shrink-0 text-[10px] font-semibold uppercase tracking-[0.06em] text-violet-600 dark:text-violet-400">
        Analise IA
      </span>
      <span
        aria-hidden="true"
        className="h-3.5 w-px shrink-0 bg-violet-200 dark:bg-violet-500/30"
      />
      <span className="min-w-0 flex-1 truncate text-xs text-gray-800 dark:text-gray-200">
        {first.text}
      </span>

      {rest.length > 0 && (
        <Popover>
          <PopoverTrigger asChild>
            <button
              type="button"
              className={cx(
                "shrink-0 rounded px-1.5 py-0.5 text-[11px] font-medium",
                "text-violet-700 hover:bg-violet-100 dark:text-violet-300 dark:hover:bg-violet-500/15",
                "transition-colors",
                focusRing,
              )}
            >
              +{rest.length} {rest.length === 1 ? "analise" : "analises"}
            </button>
          </PopoverTrigger>
          <PopoverContent align="end" sideOffset={6} className="w-80 p-2">
            <ul className="flex flex-col gap-1">
              {rest.map((ins) => (
                <li
                  key={ins.id}
                  className="rounded px-2 py-1.5 text-xs text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-900"
                >
                  {ins.text}
                </li>
              ))}
            </ul>
          </PopoverContent>
        </Popover>
      )}

      <button
        type="button"
        onClick={handleDismiss}
        aria-label="Fechar barra de insights"
        className={cx(
          "shrink-0 rounded text-violet-600 hover:text-violet-800 dark:text-violet-400 dark:hover:text-violet-200",
          "transition-colors",
          focusRing,
        )}
      >
        <RiCloseLine className="size-3.5" />
      </button>
    </div>
  )
}
