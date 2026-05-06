"use client"

import type { Provenance } from "@/lib/api-client"
import { Tooltip } from "@/components/tremor/Tooltip"

function formatDateTime(iso: string | null): string {
  if (!iso) return "(n/d)"
  try {
    return new Date(iso).toLocaleString("pt-BR", {
      dateStyle: "short",
      timeStyle: "short",
    })
  } catch {
    return iso
  }
}

function formatRelative(iso: string | null): string {
  if (!iso) return ""
  const ts = new Date(iso).getTime()
  if (Number.isNaN(ts)) return ""
  const diffMs = Date.now() - ts
  const diffMin = Math.round(diffMs / 60_000)
  if (diffMin < 1) return "agora"
  if (diffMin < 60) return `ha ${diffMin} min`
  const diffH = Math.round(diffMin / 60)
  if (diffH < 24) return `ha ${diffH} h`
  const diffD = Math.round(diffH / 24)
  return `ha ${diffD} d`
}

const trustCopy: Record<string, string> = {
  high: "Alta confianca",
  medium: "Media confianca",
  low: "Baixa confianca",
}

const trustDot: Record<string, string> = {
  high: "bg-emerald-500",
  medium: "bg-amber-500",
  low: "bg-red-500",
}

/**
 * Rodape de proveniencia (CLAUDE.md §14.5).
 *
 * Linha unica compacta com dois eixos temporais:
 * - **sync** (`last_sync_at`): pipeline alive — quando o adapter rodou.
 * - **dados ate** (`last_source_updated_at`): timestamp max dos registros
 *   filtrados na origem.
 *
 * Detalhes (versao do adapter, datas absolutas) ficam em tooltip para nao
 * ocupar espaco vertical.
 */
export function ProvenanceFooter({
  provenance,
  className = "",
}: {
  provenance: Provenance | undefined
  className?: string
}) {
  if (!provenance) return null
  const trust = trustCopy[provenance.trust_level] ?? provenance.trust_level
  const dot = trustDot[provenance.trust_level] ?? "bg-gray-400"
  const syncRel = formatRelative(provenance.last_sync_at)
  const syncAbs = formatDateTime(provenance.last_sync_at)
  const dataAbs = formatDateTime(provenance.last_source_updated_at)
  const tooltipContent = `Sincronizado em ${syncAbs} · Adapter ${provenance.ingested_by_version}`

  return (
    <Tooltip content={tooltipContent} side="top">
      <div
        className={`mt-4 flex flex-wrap items-center gap-x-2 gap-y-1 border-t border-gray-200 px-6 pt-2 text-[11px] text-gray-500 dark:border-gray-800 dark:text-gray-500 ${className}`}
      >
        <span aria-hidden="true" className={`size-1.5 shrink-0 rounded-full ${dot}`} />
        <span className="font-medium text-gray-700 dark:text-gray-300">
          {provenance.source_type}
        </span>
        <span className="text-gray-300 dark:text-gray-700">·</span>
        <code className="font-mono text-gray-600 dark:text-gray-400">
          {provenance.source_ids.join(", ")}
        </code>
        <span className="text-gray-300 dark:text-gray-700">·</span>
        <span>{provenance.row_count.toLocaleString("pt-BR")} linhas</span>
        <span className="text-gray-300 dark:text-gray-700">·</span>
        <span>sync {syncRel || syncAbs}</span>
        <span className="text-gray-300 dark:text-gray-700">·</span>
        <span>dados ate {dataAbs}</span>
        <span className="text-gray-300 dark:text-gray-700">·</span>
        <span>{trust}</span>
      </div>
    </Tooltip>
  )
}
