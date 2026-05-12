"use client"

import { RiAlertLine } from "@remixicon/react"
import Link from "next/link"

import { Tooltip } from "@/components/tremor/Tooltip"
import { useSyncHealthSummary } from "@/lib/hooks/system"

/**
 * Badge mostrado no header sticky do app shell quando ha endpoints com
 * `last_sync_status='erro'`. Click navega pra `/integracoes/sync`.
 *
 * Quando nada esta falhando, renderiza null (zero ruido visual).
 */
export function SyncHealthBadge() {
  const { data } = useSyncHealthSummary()

  if (!data || data.failing_count === 0) {
    return null
  }

  const label =
    data.failing_count === 1
      ? "1 sync falhando"
      : `${data.failing_count} syncs falhando`

  const tooltipContent = data.failing
    .slice(0, 6)
    .map((f) => `${f.source_label} · ${f.endpoint_label}`)
    .join("\n")

  return (
    <Tooltip
      content={
        data.failing.length > 6
          ? `${tooltipContent}\n…e mais ${data.failing.length - 6}`
          : tooltipContent
      }
      side="bottom"
    >
      <Link
        href="/integracoes/sync"
        className="inline-flex items-center gap-1.5 rounded-md bg-red-50 px-2 py-1 text-xs font-medium text-red-900 ring-1 ring-inset ring-red-600/20 transition-colors hover:bg-red-100 dark:bg-red-400/10 dark:text-red-400 dark:ring-red-400/20 dark:hover:bg-red-400/20"
        aria-label={`${label}. Clique para ver detalhes.`}
      >
        <RiAlertLine className="size-3.5" aria-hidden />
        <span>{label}</span>
      </Link>
    </Tooltip>
  )
}
