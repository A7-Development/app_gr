// src/design-system/types/provenance.ts
//
// Tipo canonico de proveniencia de dado para o frontend.
// Espelha o mixin `Auditable` do backend (CLAUDE.md §14.1) — todo card / KPI /
// chart / tabela que mostre dado real recebe um Provenance e renderiza o
// OriginDot correspondente. Mock = passar `undefined` — nada renderiza.

/**
 * Tipo da fonte. Espelha o enum `source_type` do backend (CLAUDE.md §14.1).
 * - `erp:<vendor>`     — ERP transacional ingerido via adapter (ex.: erp:bitfin)
 * - `admin:<vendor>`   — admin API (ex.: admin:qitech)
 * - `bureau:<vendor>`  — bureau pago (ex.: bureau:serasa_pj, bureau:serasa_pf)
 * - `public:<vendor>`  — fonte publica federada via postgres_fdw (ex.: public:cvm)
 * - `self_declared`    — declarado pelo proprio tenant (ex.: nota interna)
 * - `peer_declared`    — declarado por contraparte
 * - `internal_note`    — anotacao manual do operador
 * - `derived`          — calculado pelo proprio GR a partir de outras fontes
 */
export type ProvenanceSourceType =
  | `erp:${string}`
  | `admin:${string}`
  | `bureau:${string}`
  | `public:${string}`
  | "self_declared"
  | "peer_declared"
  | "internal_note"
  | "derived"

/**
 * Nivel de confianca da fonte. Espelha `trust_level` do mixin Auditable.
 * Padrao por sourceType (override no adapter):
 *   public:* / erp:* / admin:* / bureau:* → "high"
 *   derived                                → "high" se inputs forem high
 *   peer_declared                          → "medium"
 *   self_declared / internal_note          → "low"
 */
export type TrustLevel = "high" | "medium" | "low"

export type Provenance = {
  /** Tipo da fonte. Combina com adapterName para formar a identidade completa. */
  sourceType: ProvenanceSourceType
  /** Nome curto do adapter (ex.: "bitfin", "qitech", "cvm_fidc"). */
  adapterName: string
  /** Versao semver do adapter que ingeriu este dado (ex.: "1.0.0"). */
  adapterVersion: string
  /** ISO 8601 — quando o dado foi sincronizado para o warehouse. */
  ingestedAt: string
  /** Nivel de confianca. Default herda do sourceType. */
  trustLevel: TrustLevel
}

// ────────────────────────────────────────────────────────────────────────────
// Helpers
// ────────────────────────────────────────────────────────────────────────────

/** Identidade curta para exibicao: "bitfin@1.0.0". */
export function formatAdapterId(p: Provenance): string {
  return `${p.adapterName}@${p.adapterVersion}`
}

/** Label humanizado para a fonte (sem o vendor cru com prefixo). */
export function formatSourceLabel(p: Provenance): string {
  const map: Record<string, string> = {
    self_declared: "Declarado pelo tenant",
    peer_declared: "Declarado por contraparte",
    internal_note: "Nota interna",
    derived: "Calculado",
  }
  if (map[p.sourceType]) return map[p.sourceType]
  // erp:bitfin → "Bitfin", bureau:serasa_pj → "Serasa PJ"
  const [, vendor] = p.sourceType.split(":")
  if (!vendor) return p.adapterName
  return vendor
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ")
}

/** Tooltip estruturado: 4 linhas. */
export function formatProvenanceTooltip(p: Provenance): string {
  const lines = [
    `Fonte: ${formatSourceLabel(p)}`,
    `Adapter: ${formatAdapterId(p)}`,
    `Sincronizado: ${formatRelative(p.ingestedAt)}`,
    `Confianca: ${formatTrust(p.trustLevel)}`,
  ]
  return lines.join("\n")
}

function formatRelative(iso: string): string {
  const ts = new Date(iso).getTime()
  if (Number.isNaN(ts)) return iso
  const diffMs = Date.now() - ts
  const diffMin = Math.round(diffMs / 60_000)
  if (diffMin < 1) return "agora"
  if (diffMin < 60) return `ha ${diffMin} min`
  const diffH = Math.round(diffMin / 60)
  if (diffH < 24) return `ha ${diffH} h`
  const diffD = Math.round(diffH / 24)
  return `ha ${diffD} d`
}

function formatTrust(t: TrustLevel): string {
  return t === "high" ? "Alta" : t === "medium" ? "Media" : "Baixa"
}

/** Cor Tailwind do dot pelo trust level. */
export const TRUST_DOT_COLOR: Record<TrustLevel, string> = {
  high: "bg-emerald-500 hover:bg-emerald-600 dark:bg-emerald-500 dark:hover:bg-emerald-400",
  medium: "bg-amber-500 hover:bg-amber-600 dark:bg-amber-500 dark:hover:bg-amber-400",
  low: "bg-red-500 hover:bg-red-600 dark:bg-red-500 dark:hover:bg-red-400",
}

/** Deduplica por adapter+versao, mantem o ingestedAt mais recente. */
export function dedupeProvenances(items: Provenance[]): Provenance[] {
  const map = new Map<string, Provenance>()
  for (const p of items) {
    const key = formatAdapterId(p)
    const prev = map.get(key)
    if (!prev || new Date(p.ingestedAt) > new Date(prev.ingestedAt)) {
      map.set(key, p)
    }
  }
  return Array.from(map.values())
}
