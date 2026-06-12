// src/app/(app)/credito/workflows/[id]/editor/_lib/esteira-preview.ts
//
// Prévia da esteira (F4, 2026-06-12): deriva do GRAFO do editor como ele
// vira as ESTAÇÕES que o analista vê no modo foco. Responde a pergunta
// "ramos em paralelo aparecem como no timeline do dossiê?" — paralelo é
// execução do MOTOR; a esteira do analista é sequencial por decisão de
// produto (condução sequencial, 2026-06-10).
//
// Replica client-side a lógica de buildEstacoes do modo foco
// (frontend/src/app/(foco)/credito/dossies/[id]/page.tsx) sobre nodes/edges
// do React Flow — interim até o backend declarar "§ gera seção" no graph.
// Se a lógica de lá mudar, esta cópia precisa acompanhar (comentário espelho
// existe lá).
//
// Funções puras — testáveis, sem React.

import type { Edge, Node } from "@xyflow/react"

export type PreviewMember = {
  id: string
  label: string
  nodeType: string
}

export type PreviewEstacao = {
  label: string
  members: PreviewMember[]
  temGate: boolean
  /** Profundidade do primeiro membro (distância do trigger) — estações com a
   *  mesma profundidade vêm de ramos paralelos do grafo. */
  depth: number
  /** Outras estações que executam em paralelo no motor. */
  paralelaCom: string[]
}

export type PreviewWarning = { nodeId: string; label: string; motivo: string }

export type EsteiraPreview = {
  estacoes: PreviewEstacao[]
  /** Nodes de bastidor (não viram estação — só trilha). */
  trilha: PreviewMember[]
  warnings: PreviewWarning[]
}

// ── Espelhos do modo foco ───────────────────────────────────────────────────

const TRILHA_TYPES = new Set([
  "trigger",
  "notification",
  "output_generator",
  "http_request",
  "conditional_branch",
  "consolidator",
])

const AGENT_STATION_AFFINITY: Record<string, string> = {
  revenue_analyst: "document_request",
  cadastral_analyst: "cadastral_enrichment",
  social_contract_analyst: "document_request",
}

const AGENT_STATION_LABEL: Record<string, string> = {
  revenue_analyst: "Faturamento",
  cadastral_analyst: "Cadastral",
  social_contract_analyst: "Contrato social",
}

type FlowNodeData = {
  label?: string
  nodeType?: string
  config?: Record<string, unknown>
}

type Ordered = {
  id: string
  label: string
  nodeType: string
  config: Record<string, unknown>
  depth: number
}

/** Ordenação topológica (Kahn) com profundidade = maior distância da raiz.
 *  Estável: empates seguem a ordem de inserção no grafo. */
function topoOrder(nodes: Node[], edges: Edge[]): Ordered[] {
  const byId = new Map(nodes.map((n) => [n.id, n]))
  const indeg = new Map<string, number>(nodes.map((n) => [n.id, 0]))
  const out = new Map<string, string[]>()
  for (const e of edges) {
    if (!byId.has(e.source) || !byId.has(e.target)) continue
    out.set(e.source, [...(out.get(e.source) ?? []), e.target])
    indeg.set(e.target, (indeg.get(e.target) ?? 0) + 1)
  }
  const depth = new Map<string, number>()
  const queue = nodes.filter((n) => (indeg.get(n.id) ?? 0) === 0).map((n) => n.id)
  for (const id of queue) depth.set(id, 0)
  const result: string[] = []
  while (queue.length) {
    const id = queue.shift() as string
    result.push(id)
    for (const next of out.get(id) ?? []) {
      depth.set(next, Math.max(depth.get(next) ?? 0, (depth.get(id) ?? 0) + 1))
      indeg.set(next, (indeg.get(next) ?? 1) - 1)
      if ((indeg.get(next) ?? 0) === 0) queue.push(next)
    }
  }
  // Ciclo (indeg restante) — anexa no fim pra não sumir node da prévia.
  for (const n of nodes) if (!result.includes(n.id)) result.push(n.id)

  return result.map((id) => {
    const n = byId.get(id) as Node
    const d = (n.data ?? {}) as FlowNodeData
    return {
      id,
      label: d.label || id,
      nodeType: d.nodeType ?? "",
      config: d.config ?? {},
      depth: depth.get(id) ?? 0,
    }
  })
}

function agentOf(step: Ordered): string | null {
  const a = step.config.agent
  return typeof a === "string" && a ? a : null
}

export function deriveEsteiraPreview(nodes: Node[], edges: Edge[]): EsteiraPreview {
  const ordered = topoOrder(nodes, edges)
  const estacoes: Array<PreviewEstacao & { _ids: Set<string> }> = []
  const trilha: PreviewMember[] = []
  const warnings: PreviewWarning[] = []

  const anchorFor = (step: Ordered): (typeof estacoes)[number] | null => {
    if (step.nodeType === "deterministic_check") {
      return estacoes[estacoes.length - 1] ?? null
    }
    if (step.nodeType === "document_extractor") {
      for (let i = estacoes.length - 1; i >= 0; i--) {
        if (estacoes[i].members.some((m) => m.nodeType === "document_request")) {
          return estacoes[i]
        }
      }
      warnings.push({
        nodeId: step.id,
        label: step.label,
        motivo:
          "Extrai documentos mas não há etapa 'Pedir documentos' antes — vai virar estação solta.",
      })
      return null
    }
    if (step.nodeType === "specialist_agent") {
      const agent = agentOf(step)
      const affinity = agent ? AGENT_STATION_AFFINITY[agent] : undefined
      if (affinity) {
        for (let i = estacoes.length - 1; i >= 0; i--) {
          if (estacoes[i].members.some((m) => m.nodeType === affinity)) {
            return estacoes[i]
          }
        }
        warnings.push({
          nodeId: step.id,
          label: step.label,
          motivo:
            "Este agente costuma fundir na estação da sua fonte de dados, que não existe no fluxo — vai virar estação própria.",
        })
      }
      return null
    }
    if (step.nodeType === "human_review") {
      const target = step.config.review_of
      if (typeof target === "string" && target) {
        for (const e of estacoes) {
          if (e._ids.has(target) || e.members.some((m) => m.id === target)) return e
        }
        return null
      }
      for (const e of estacoes) {
        if (e.members.some((m) => m.id && agentOfMember(m, ordered) === "opinion_writer"))
          return e
      }
      return null
    }
    return null
  }

  const agentOfMember = (m: PreviewMember, all: Ordered[]): string | null => {
    const o = all.find((x) => x.id === m.id)
    return o ? agentOf(o) : null
  }

  for (const step of ordered) {
    if (TRILHA_TYPES.has(step.nodeType)) {
      trilha.push({ id: step.id, label: step.label, nodeType: step.nodeType })
      continue
    }
    const member: PreviewMember = {
      id: step.id,
      label: step.label,
      nodeType: step.nodeType,
    }
    const host = anchorFor(step)
    if (host) {
      host.members.push(member)
      host._ids.add(step.id)
      if (step.nodeType === "human_review") host.temGate = true
      const agent = agentOf(step)
      if (step.nodeType === "specialist_agent" && agent && AGENT_STATION_LABEL[agent]) {
        host.label = AGENT_STATION_LABEL[agent]
      }
      continue
    }
    estacoes.push({
      label:
        agentOf(step) === "opinion_writer" || step.nodeType === "human_review"
          ? "Parecer"
          : step.label,
      members: [member],
      temGate: step.nodeType === "human_review",
      depth: step.depth,
      paralelaCom: [],
      _ids: new Set([step.id]),
    })
  }

  // Paralelismo: estações cujo primeiro membro está na MESMA profundidade do
  // grafo nascem de ramos paralelos — o motor executa junto, a esteira mostra
  // uma depois da outra.
  for (const a of estacoes) {
    for (const b of estacoes) {
      if (a !== b && a.depth === b.depth) a.paralelaCom.push(b.label)
    }
  }

  return {
    estacoes: estacoes.map(({ _ids, ...rest }) => {
      void _ids
      return rest
    }),
    trilha,
    warnings,
  }
}
