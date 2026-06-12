// src/app/(app)/credito/workflows/[id]/editor/_lib/lineage.ts
//
// Linhagem de dados (F3, 2026-06-12): ao selecionar um node, responder em um
// clique "QUEM ME ALIMENTA / QUEM EU ALIMENTO" — sem abrir inspector.
//
// Alimenta = referencia de DADO ({{node.X.output.Y}} em config/input_bindings
// /entity_ref/expression) ou condicao de edge. Pais diretos por edge sem
// referencia de dado sao fluxo de CONTROLE (ordem), nao linhagem — ficam fora
// do destaque pra nao diluir o sinal.
//
// Funções puras — testáveis, sem React.

import type { Edge, Node } from "@xyflow/react"

const REF_RE = /\{\{\s*node\.([^.}]+)\.output\.([^}\s]+)\s*\}\}/g

/** Extrai todas as refs {{node.X.output.Y}} de um valor serializado. */
function refsOf(value: unknown): Array<{ nodeId: string; varName: string }> {
  const out: Array<{ nodeId: string; varName: string }> = []
  const s = JSON.stringify(value ?? "")
  let m: RegExpExecArray | null
  const re = new RegExp(REF_RE.source, "g")
  while ((m = re.exec(s)) !== null) {
    out.push({ nodeId: m[1], varName: m[2] })
  }
  return out
}

export type LineageRole = "feeder" | "consumer" | "dim"

export type Lineage = {
  /** nodeId → variáveis que ele envia pro node selecionado. */
  feeders: Map<string, string[]>
  /** nodeId → variáveis do selecionado que ele consome. */
  consumers: Map<string, string[]>
  /** Papel por node (pra glow/dim no canvas). */
  roleOf: (nodeId: string) => LineageRole | undefined
}

export function computeLineage(
  selectedId: string,
  nodes: Node[],
  edges: Edge[],
): Lineage {
  const feeders = new Map<string, string[]>()
  const consumers = new Map<string, string[]>()

  const add = (map: Map<string, string[]>, nodeId: string, varName: string) => {
    if (nodeId === selectedId) return
    map.set(nodeId, Array.from(new Set([...(map.get(nodeId) ?? []), varName])))
  }

  const selected = nodes.find((n) => n.id === selectedId)
  const selConfig = (selected?.data as { config?: unknown } | undefined)?.config

  // Quem me alimenta: refs no MEU config…
  for (const r of refsOf(selConfig)) add(feeders, r.nodeId, r.varName)
  // …e nas condições das edges que CHEGAM em mim.
  for (const e of edges) {
    if (e.target !== selectedId) continue
    const cond = (e.data as { condition?: string | null } | undefined)?.condition
    for (const r of refsOf(cond)) add(feeders, r.nodeId, r.varName)
  }

  // Quem me consome: refs a node.<selectedId>.output.* nos configs dos outros…
  for (const n of nodes) {
    if (n.id === selectedId) continue
    const cfg = (n.data as { config?: unknown } | undefined)?.config
    for (const r of refsOf(cfg)) {
      if (r.nodeId === selectedId) add(consumers, n.id, r.varName)
    }
  }
  // …e nas condições de edges (o ALVO da edge é quem decide com meu dado).
  for (const e of edges) {
    const cond = (e.data as { condition?: string | null } | undefined)?.condition
    for (const r of refsOf(cond)) {
      if (r.nodeId === selectedId && e.target !== selectedId) {
        add(consumers, e.target, r.varName)
      }
    }
  }

  // Fio INVISIVEL via dossie (empresa-alvo): nodes de origem fixa
  // (cadastral/documento oficial) leem o CNPJ que o formulario de
  // identificacao (human_input com campo cnpj) gravou na empresa-alvo.
  // Sem isto, a linhagem nao mostrava a ligacao — exatamente a confusao
  // apontada pelo Ricardo (2026-06-12).
  const FIXED_ORIGIN = new Set(["cadastral_enrichment", "official_document_fetch"])
  const isIdentitySource = (n: Node): boolean => {
    const d = n.data as { nodeType?: string; config?: { fields?: unknown } } | undefined
    if (d?.nodeType !== "human_input") return false
    const fields = d.config?.fields
    return (
      Array.isArray(fields) &&
      fields.some((f) => {
        const name = (f as { name?: unknown })?.name
        return (
          typeof name === "string" &&
          ["cnpj", "target_cnpj"].includes(name.toLowerCase())
        )
      })
    )
  }
  const selType = (selected?.data as { nodeType?: string } | undefined)?.nodeType
  if (selType && FIXED_ORIGIN.has(selType)) {
    for (const n of nodes) {
      if (isIdentitySource(n)) add(feeders, n.id, "cnpj (empresa-alvo)")
    }
  }
  if (selected && isIdentitySource(selected)) {
    for (const n of nodes) {
      const t = (n.data as { nodeType?: string } | undefined)?.nodeType
      if (t && FIXED_ORIGIN.has(t)) add(consumers, n.id, "cnpj (empresa-alvo)")
    }
  }

  return {
    feeders,
    consumers,
    roleOf: (nodeId: string) => {
      if (nodeId === selectedId) return undefined
      if (feeders.has(nodeId)) return "feeder"
      if (consumers.has(nodeId)) return "consumer"
      return "dim"
    },
  }
}
