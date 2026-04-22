"use client"

import { RiDatabase2Line, RiPulseLine, RiShieldCheckLine } from "@remixicon/react"

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

/**
 * Rodape de proveniencia (CLAUDE.md 14.6).
 *
 * Exibe DOIS eixos temporais claramente distintos:
 * - **Pipeline** (`last_sync_at`): quando o sistema recebeu dado pela ultima
 *   vez, independente de filtros. Vem do `decision_log` (ou proxy para
 *   fontes publicas). Responde "o pipeline esta vivo?".
 * - **Dados** (`last_source_updated_at`): quando o dado mais recente DENTRO
 *   do set filtrado foi atualizado na origem. Responde "ate quando vai o
 *   que estou olhando?".
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
  const syncRel = formatRelative(provenance.last_sync_at)

  return (
    <div
      className={`mt-6 flex flex-col gap-1.5 border-t border-gray-200 pt-3 text-xs text-gray-500 dark:border-gray-800 dark:text-gray-500 ${className}`}
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <span className="inline-flex items-center gap-1.5">
          <RiPulseLine className="size-3.5 text-gray-500" aria-hidden="true" />
          <span className="font-medium text-gray-700 dark:text-gray-300">
            Pipeline
          </span>
          <span>
            sincronizado em {formatDateTime(provenance.last_sync_at)}
            {syncRel ? ` (${syncRel})` : ""}
          </span>
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <span className="inline-flex items-center gap-1.5">
          <RiDatabase2Line className="size-3.5 text-gray-500" aria-hidden="true" />
          <span className="font-medium text-gray-700 dark:text-gray-300">
            Dados
          </span>
          <span>
            {provenance.row_count.toLocaleString("pt-BR")} linhas · mais recente em{" "}
            {formatDateTime(provenance.last_source_updated_at)}
          </span>
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-gray-400 dark:text-gray-600">
        <span>
          Fonte:{" "}
          <code className="font-mono">{provenance.source_type}</code>
          {" · "}
          <code className="font-mono">
            {provenance.source_ids.join(", ")}
          </code>
        </span>
        <Tooltip
          content={`Versao do adapter: ${provenance.ingested_by_version}`}
          side="top"
        >
          <span className="inline-flex items-center gap-1.5">
            <RiShieldCheckLine className="size-3.5" aria-hidden="true" />
            {trust}
          </span>
        </Tooltip>
      </div>
    </div>
  )
}
