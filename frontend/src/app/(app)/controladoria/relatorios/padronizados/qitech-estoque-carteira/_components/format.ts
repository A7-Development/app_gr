// Helpers de formatacao compartilhados entre CarteiraDashboard e
// SnapshotsLanding. Mantidos aqui porque sao identicos nos dois e
// nao justificam viver no _lib do parent (que e contrato com backend).

import type {
  Provenance,
  ProvenanceSourceType,
  TrustLevel,
} from "@/design-system/types/provenance"

import type { ProvenanceMetadata } from "../../../_lib/api"

export function brl(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—"
  const n = typeof value === "number" ? value : Number(value)
  if (Number.isNaN(n)) return "—"
  return n.toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })
}

export function brlMi(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—"
  const n = typeof value === "number" ? value : Number(value)
  if (Number.isNaN(n)) return "—"
  if (n >= 1_000_000) return `R$ ${(n / 1_000_000).toFixed(1)} mi`
  if (n >= 1_000) return `R$ ${(n / 1_000).toFixed(0)}k`
  return `R$ ${n.toFixed(0)}`
}

export function pct(
  value: number | null | undefined,
  fractionDigits = 1,
): string {
  if (value === null || value === undefined) return "—"
  if (Number.isNaN(value)) return "—"
  return `${value.toFixed(fractionDigits)}%`
}

export function formatDateBR(value: string | null | undefined): string {
  if (!value) return "—"
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleDateString("pt-BR", { timeZone: "UTC" })
}

export function formatDateTimeBR(value: string | null | undefined): string {
  if (!value) return "—"
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo" })
}

/** Tempo decorrido em formato compacto: "32s", "4min", "1h12min", "2d 4h". */
export function formatElapsed(fromISO: string): string {
  const from = new Date(fromISO).getTime()
  const now = Date.now()
  const seconds = Math.max(0, Math.floor((now - from) / 1000))
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}min`
  const hours = Math.floor(minutes / 60)
  const remMin = minutes % 60
  if (hours < 24) return remMin > 0 ? `${hours}h${remMin}min` : `${hours}h`
  const days = Math.floor(hours / 24)
  const remHours = hours % 24
  return remHours > 0 ? `${days}d ${remHours}h` : `${days}d`
}

export function mapProvenance(
  meta: ProvenanceMetadata | null | undefined,
): Provenance | null {
  if (!meta || !meta.last_ingested_at) return null
  const fullVersion = meta.adapter_version ?? ""
  const splitIdx = fullVersion.lastIndexOf("_v")
  const adapterName =
    splitIdx > 0
      ? fullVersion.slice(0, splitIdx).replace(/_adapter$/, "")
      : meta.source_type.split(":")[1] || meta.source_type
  const adapterVersion = splitIdx > 0 ? fullVersion.slice(splitIdx + 2) : "1.0.0"
  const trust: TrustLevel =
    meta.trust_level === "medium" || meta.trust_level === "low"
      ? meta.trust_level
      : "high"
  return {
    sourceType: meta.source_type as ProvenanceSourceType,
    adapterName,
    adapterVersion,
    ingestedAt: meta.last_ingested_at,
    trustLevel: trust,
  }
}
