// src/app/(app)/credito/workflows/[id]/editor/_lib/validate.ts
//
// Validacao do graph com mensagens em DOMAIN LANGUAGE — o usuario nao
// deve ler "node X has missing required config field Y". Ele le "A etapa
// _Analise financeira_ esta sem o campo obrigatorio _Agente_."
//
// Roda em tempo real no editor (ao mudar nodes/edges/configs) e antes de
// salvar. Cada erro carrega `nodeId` ou `edgeId` para alimentar halo
// visual no canvas + chip persistente no header.
//
// Niveis:
//   - "error":   bloqueia publicacao
//   - "warning": nao bloqueia, mas merece atencao

import type { Edge, Node } from "@xyflow/react"

import type { NodeTypeMeta } from "@/lib/credito-client"

import type { StrataNodeData } from "../_components/StrataNode"

import { ETAPA_LABEL, getEtapaLabel } from "./glossary"

export type ValidationError = {
  level: "error" | "warning"
  nodeId?: string
  edgeId?: string
  /** Mensagem amigavel para o usuario final. */
  message: string
}

export function validateGraph(
  nodes: Node[],
  edges: Edge[],
  nodeTypes: NodeTypeMeta[],
): ValidationError[] {
  const errors: ValidationError[] = []
  const metaByType = new Map(nodeTypes.map((nt) => [nt.type, nt]))
  const nodeIds = new Set(nodes.map((n) => n.id))

  // Helper para usar label amigavel da etapa.
  const labelOf = (nodeId: string): string => {
    const n = nodes.find((nd) => nd.id === nodeId)
    if (!n) return nodeId
    const data = n.data as unknown as StrataNodeData
    return data.label || getEtapaLabel(data.nodeType, data.config ?? {})
  }

  // 1. Pelo menos uma etapa.
  if (nodes.length === 0) {
    errors.push({
      level: "error",
      message: "Fluxo vazio. Arraste uma etapa da palette pra comecar.",
    })
    return errors
  }

  // 2. Conexoes referenciam etapas existentes.
  for (const e of edges) {
    if (!nodeIds.has(e.source)) {
      errors.push({
        level: "error",
        edgeId: e.id,
        message: `Conexao orfa: a etapa "${e.source}" nao existe mais. Apague esta conexao.`,
      })
    }
    if (!nodeIds.has(e.target)) {
      errors.push({
        level: "error",
        edgeId: e.id,
        message: `Conexao orfa: a etapa "${e.target}" nao existe mais. Apague esta conexao.`,
      })
    }
  }

  // 2b. Raiz orfa (2026-06-12, pos DC-2026-0038): node sem seta de ENTRADA
  // que nao seja o Inicio e raiz do grafo — o motor executa raizes
  // imediatamente, entao um checkpoint solto vira "estacao fantasma"
  // rodando na frente de tudo. ERRO bloqueador: conecte ou apague.
  const targets = new Set(edges.map((e) => e.target))
  for (const n of nodes) {
    const data = n.data as unknown as StrataNodeData
    if (data.nodeType === "trigger") continue
    if (!targets.has(n.id)) {
      errors.push({
        level: "error",
        nodeId: n.id,
        message: `A etapa "${labelOf(n.id)}" nao esta conectada ao fluxo (sem seta de entrada) — ela rodaria ANTES de tudo. Conecte-a ou apague.`,
      })
    }
  }

  // 2c. Origem fixa sem fonte de identidade (pos-mortem DC-2026-0039):
  // cadastral_enrichment / official_document_fetch leem o CNPJ da
  // empresa-alvo, que e materializada por um formulario com campo de key
  // `cnpj`. Sem esse formulario no fluxo, eles rodam vazios (found=false).
  {
    const hasIdentity = nodes.some((n) => {
      const d = n.data as unknown as StrataNodeData
      if (d.nodeType !== "human_input") return false
      const fields = (d.config ?? {}).fields
      return (
        Array.isArray(fields) &&
        fields.some((f) => {
          const ref = f as { key?: unknown; name?: unknown }
          const ident = ref?.key ?? ref?.name
          return (
            typeof ident === "string" &&
            ["cnpj", "target_cnpj"].includes(ident.toLowerCase())
          )
        })
      )
    })
    if (!hasIdentity) {
      for (const n of nodes) {
        const d = n.data as unknown as StrataNodeData
        if (
          d.nodeType === "cadastral_enrichment" ||
          d.nodeType === "official_document_fetch"
        ) {
          errors.push({
            level: "warning",
            nodeId: n.id,
            message: `A etapa "${labelOf(n.id)}" consulta o CNPJ da empresa-alvo, mas nenhum formulario do fluxo tem um campo chamado "cnpj" pra preenche-la — a consulta vai rodar vazia. Adicione/renomeie o campo no formulario de identificacao.`,
          })
        }
      }
    }
  }

  // 3. Configs obrigatorias preenchidas + checagens por tipo de etapa.
  for (const n of nodes) {
    const data = n.data as unknown as StrataNodeData
    const meta = metaByType.get(data.nodeType)
    const etapaName = labelOf(n.id)
    const friendlyType = ETAPA_LABEL[data.nodeType] ?? data.nodeType

    if (!meta) {
      errors.push({
        level: "error",
        nodeId: n.id,
        message: `A etapa "${etapaName}" usa um tipo desconhecido (${data.nodeType}). Esta etapa nao vai executar.`,
      })
      continue
    }

    if (!meta.available) {
      errors.push({
        level: "warning",
        nodeId: n.id,
        message: `A etapa "${etapaName}" e do tipo "${friendlyType}" que esta marcado como em breve — nao vai executar quando o fluxo rodar.`,
      })
    }

    // Per-type checks.
    const config = data.config ?? {}

    if (data.nodeType === "specialist_agent") {
      const agent = config.agent as string | undefined
      if (!agent) {
        errors.push({
          level: "error",
          nodeId: n.id,
          message: `A etapa "${etapaName}" precisa ter um agente IA selecionado.`,
        })
      }
    }

    if (data.nodeType === "human_input") {
      const fields = Array.isArray(config.fields) ? (config.fields as unknown[]) : []
      if (fields.length === 0) {
        errors.push({
          level: "warning",
          nodeId: n.id,
          message: `A etapa "${etapaName}" nao tem nenhum campo no formulario. Adicione campos pra coletar dados.`,
        })
      }
    }

    if (data.nodeType === "document_request") {
      const required = Array.isArray(config.required) ? (config.required as unknown[]) : []
      const optional = Array.isArray(config.optional) ? (config.optional as unknown[]) : []
      if (required.length + optional.length === 0) {
        errors.push({
          level: "warning",
          nodeId: n.id,
          message: `A etapa "${etapaName}" nao pede nenhum documento. Selecione pelo menos um.`,
        })
      }
    }

    if (data.nodeType === "conditional_branch") {
      const expr = config.expression as string | undefined
      if (!expr || expr.trim() === "") {
        errors.push({
          level: "error",
          nodeId: n.id,
          message: `A etapa "${etapaName}" precisa ter uma condicao. Configure o "Se [campo] [operador] [valor]".`,
        })
      }
    }

    if (data.nodeType === "bureau_query") {
      const adapter = config.adapter as string | undefined
      const entityRef = config.entity_ref as string | undefined
      if (!adapter) {
        errors.push({
          level: "error",
          nodeId: n.id,
          message: `A etapa "${etapaName}" precisa ter um bureau selecionado.`,
        })
      }
      // Adapters wired no backend exigem entity_ref. Lista espelha
      // _WIRED_ADAPTERS em backend/app/agentic/playbooks/nodes/bureau_query.py.
      const wiredAdapters = ["serasa_pj", "bigdatacorp"]
      if (adapter && wiredAdapters.includes(adapter)) {
        if (!entityRef || entityRef.trim() === "") {
          errors.push({
            level: "error",
            nodeId: n.id,
            message: `A etapa "${etapaName}" precisa do CNPJ — ligue na variavel da Identificacao (ex.: {{node.identificacao.output.cnpj}}) ou digite um valor.`,
          })
        }
      } else if (adapter) {
        // Adapter selecionado mas nao wired ainda.
        errors.push({
          level: "warning",
          nodeId: n.id,
          message: `A etapa "${etapaName}" usa o bureau "${adapter}" que ainda nao foi ligado — nao vai executar quando o fluxo rodar.`,
        })
      }
    }

    // Required configs do schema.
    for (const field of meta.config_schema ?? []) {
      if (!field.required) continue
      const v = config[field.key]
      const empty =
        v === undefined ||
        v === null ||
        (typeof v === "string" && v.trim() === "") ||
        (Array.isArray(v) && v.length === 0)
      if (empty) {
        errors.push({
          level: "error",
          nodeId: n.id,
          message: `A etapa "${etapaName}" esta sem o campo obrigatorio "${field.label}".`,
        })
      }
    }
  }

  // 4. Detector de ciclo.
  if (hasCycle(nodes, edges)) {
    errors.push({
      level: "error",
      message: "O fluxo tem um ciclo (uma etapa volta para uma anterior). Fluxos precisam seguir uma direcao unica.",
    })
  }

  // 5. Etapas orfas — conectividade.
  const incoming = new Map<string, number>()
  const outgoing = new Map<string, number>()
  for (const n of nodes) {
    incoming.set(n.id, 0)
    outgoing.set(n.id, 0)
  }
  for (const e of edges) {
    if (incoming.has(e.target)) incoming.set(e.target, incoming.get(e.target)! + 1)
    if (outgoing.has(e.source)) outgoing.set(e.source, outgoing.get(e.source)! + 1)
  }
  for (const n of nodes) {
    const data = n.data as unknown as StrataNodeData
    const isStart = data.nodeType === "trigger"
    const isEnd = data.nodeType === "output_generator" || data.nodeType === "notification"
    const incomingCount = incoming.get(n.id) ?? 0
    const outgoingCount = outgoing.get(n.id) ?? 0

    // Etapa sem entrada (que nao seja inicio).
    if (!isStart && incomingCount === 0) {
      errors.push({
        level: "warning",
        nodeId: n.id,
        message: `A etapa "${labelOf(n.id)}" nao tem nenhuma conexao chegando — ela nunca vai executar.`,
      })
    }

    // Etapa sem saida (que nao seja final).
    if (!isEnd && outgoingCount === 0) {
      errors.push({
        level: "warning",
        nodeId: n.id,
        message: `A etapa "${labelOf(n.id)}" nao tem nenhuma conexao saindo — o fluxo termina aqui sem gerar saida.`,
      })
    }
  }

  // 6. Soft warnings — estrutura do fluxo.
  const types = new Set(nodes.map((n) => (n.data as unknown as StrataNodeData).nodeType))
  if (!types.has("trigger")) {
    errors.push({
      level: "warning",
      message: "O fluxo nao tem etapa de Inicio. Adicione uma etapa Inicio pra definir como o fluxo dispara.",
    })
  }
  if (!types.has("output_generator")) {
    errors.push({
      level: "warning",
      message: "O fluxo nao gera nenhuma saida final (PDF/JSON). Adicione uma etapa Gerar saida no final.",
    })
  }

  return errors
}

function hasCycle(nodes: Node[], edges: Edge[]): boolean {
  const adj = new Map<string, string[]>()
  for (const n of nodes) adj.set(n.id, [])
  for (const e of edges) {
    if (adj.has(e.source)) adj.get(e.source)!.push(e.target)
  }
  const WHITE = 0, GRAY = 1, BLACK = 2
  const color = new Map<string, number>()
  for (const n of nodes) color.set(n.id, WHITE)

  function dfs(u: string): boolean {
    color.set(u, GRAY)
    for (const v of adj.get(u) ?? []) {
      const c = color.get(v) ?? WHITE
      if (c === GRAY) return true
      if (c === WHITE && dfs(v)) return true
    }
    color.set(u, BLACK)
    return false
  }

  for (const n of nodes) {
    if (color.get(n.id) === WHITE && dfs(n.id)) return true
  }
  return false
}

// ─── Helpers para o caller ──────────────────────────────────────────────

/** So erros bloqueadores. */
export function blockingErrors(errors: ValidationError[]): ValidationError[] {
  return errors.filter((e) => e.level === "error")
}

/** Mapa nodeId → status da etapa, pra alimentar halo visual no canvas. */
export function statusByNode(
  errors: ValidationError[],
): Map<string, { status: "error" | "warning"; message: string }> {
  const map = new Map<string, { status: "error" | "warning"; message: string }>()
  for (const e of errors) {
    if (!e.nodeId) continue
    const existing = map.get(e.nodeId)
    // Erro tem prioridade sobre warning.
    if (existing?.status === "error") continue
    map.set(e.nodeId, {
      status: e.level === "error" ? "error" : "warning",
      message: e.message,
    })
  }
  return map
}

/** Sumario amigavel para o badge no header. */
export function summarize(errors: ValidationError[]): {
  total: number
  errors: number
  warnings: number
  blocking: boolean
} {
  let errs = 0
  let warns = 0
  for (const e of errors) {
    if (e.level === "error") errs++
    else warns++
  }
  return {
    total: errors.length,
    errors: errs,
    warnings: warns,
    blocking: errs > 0,
  }
}
