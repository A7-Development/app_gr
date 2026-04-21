"use client"

import { RiDatabase2Line, RiShieldCheckLine } from "@remixicon/react"

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

const trustCopy: Record<string, string> = {
  high: "Alta confianca",
  medium: "Media confianca",
  low: "Baixa confianca",
}

/**
 * Rodape de proveniencia (CLAUDE.md 14.6).
 * Exibido em todo dashboard BI — dado sem origem nao passa em compliance.
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

  return (
    <div
      className={`mt-6 flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-gray-200 pt-3 text-xs text-gray-500 dark:border-gray-800 dark:text-gray-500 ${className}`}
    >
      <span className="inline-flex items-center gap-1.5">
        <RiDatabase2Line className="size-3.5" aria-hidden="true" />
        Fonte:{" "}
        <code className="font-mono text-[11px]">{provenance.source_type}</code>
        {" · "}
        <code className="font-mono text-[11px]">
          {provenance.source_ids.join(", ")}
        </code>
      </span>
      <span>
        {provenance.row_count.toLocaleString("pt-BR")} linhas consideradas
      </span>
      <span>Ingerido em {formatDateTime(provenance.last_ingested_at)}</span>
      <span>
        Atualizacao na origem:{" "}
        {formatDateTime(provenance.last_source_updated_at)}
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
  )
}
