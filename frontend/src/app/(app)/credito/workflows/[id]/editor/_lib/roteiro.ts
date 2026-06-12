// src/app/(app)/credito/workflows/[id]/editor/_lib/roteiro.ts
//
// Modo Roteiro (F6, 2026-06-12): o MESMO fluxo como narrativa numerada em
// português, lendo de cima pra baixo. Usuário padrão lê e valida no Roteiro;
// power user constrói no canvas. Gerado do grafo — documentação viva do
// playbook, sempre em dia.
//
// Funções puras — testáveis, sem React.

import type { Edge, Node } from "@xyflow/react"

import type { AgentMeta } from "@/lib/credito-client"

import { nodeContract } from "./contract"
import { friendlyCondition } from "./edge-label"
import { topoOrder, type Ordered } from "./esteira-preview"
import { AGENT_FRIENDLY_LABEL, ETAPA_LABEL } from "./glossary"

export type RoteiroItem = {
  nodeId: string
  /** Título do passo (nome dado pelo usuário ou label amigável do tipo). */
  titulo: string
  /** Tipo amigável ("Consultar bureau", "Análise IA"...). */
  tipoLabel: string
  nodeType: string
  /** Frase do que o passo faz (do contrato F1). */
  faz: string
  /** Condições de ENTRADA: "se score ≥ 700 (vindo de Decisão X)". */
  condicoesEntrada: string[]
}

export type RoteiroGrupo = {
  /** Número sequencial do grupo (1, 2, 3...). */
  numero: number
  /** true = 2+ passos rodando AO MESMO TEMPO (ramos paralelos do motor). */
  paralelo: boolean
  itens: RoteiroItem[]
}

function tituloDe(step: Ordered): string {
  if (step.nodeType === "specialist_agent") {
    const agent = String(step.config.agent ?? "")
    if (agent && AGENT_FRIENDLY_LABEL[agent]) return AGENT_FRIENDLY_LABEL[agent]
  }
  return step.label
}

export function buildRoteiro(
  nodes: Node[],
  edges: Edge[],
  agentCatalog: AgentMeta[] = [],
): RoteiroGrupo[] {
  const ordered = topoOrder(nodes, edges)
  const byId = new Map(ordered.map((o) => [o.id, o]))

  // Agrupa por profundidade — passos na mesma profundidade vêm de ramos
  // paralelos e rodam juntos no motor.
  const byDepth = new Map<number, Ordered[]>()
  for (const step of ordered) {
    byDepth.set(step.depth, [...(byDepth.get(step.depth) ?? []), step])
  }

  const grupos: RoteiroGrupo[] = []
  const depths = Array.from(byDepth.keys()).sort((a, b) => a - b)
  let numero = 0

  for (const d of depths) {
    const steps = byDepth.get(d) ?? []
    numero += 1
    grupos.push({
      numero,
      paralelo: steps.length > 1,
      itens: steps.map((step) => {
        const contract = nodeContract(step.nodeType, step.config, agentCatalog)
        const condicoesEntrada = edges
          .filter((e) => e.target === step.id)
          .map((e) => {
            const cond = (e.data as { condition?: string | null } | undefined)
              ?.condition
            if (!cond) return null
            const origem = byId.get(e.source)
            return `${friendlyCondition(cond)}${origem ? ` (decidido em "${origem.label}")` : ""}`
          })
          .filter((c): c is string => Boolean(c))
        return {
          nodeId: step.id,
          titulo: tituloDe(step),
          tipoLabel: ETAPA_LABEL[step.nodeType] ?? step.nodeType,
          nodeType: step.nodeType,
          faz: contract.faz,
          condicoesEntrada,
        }
      }),
    })
  }

  return grupos
}
