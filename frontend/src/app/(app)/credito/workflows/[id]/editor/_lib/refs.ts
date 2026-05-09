// src/app/(app)/credito/workflows/[id]/editor/_lib/refs.ts
//
// Computa "outputs disponiveis" para uma etapa — base do ConditionBuilder
// e ReferencePicker. O usuario nao digita {{node.X.output.field}}; ele
// escolhe campo num dropdown e nos geramos a sintaxe de template.
//
// Algoritmo:
//   1. Para uma etapa-alvo T, encontra todas as etapas upstream
//      (transitivamente alcancaveis seguindo edges reversos).
//   2. Para cada etapa upstream, descobre que campos ela produz no output:
//      - human_input: campos de config.fields[]
//      - specialist_agent: campos do output_schema do agente (mapa hardcoded)
//      - document_extractor: campos comuns + extras do template (runtime)
//      - bureau_query: campos comuns por bureau (mapa hardcoded)
//      - trigger: campos do trigger_data (mapa hardcoded com pleito padrao)
//      - outros: vazio (usuario pode usar referencia manual)
//   3. Adiciona o trigger como sempre-disponivel.
//
// O mapa hardcoded e MVP. Em fase 2, pode vir do backend (cada NodeTypeMeta
// expoe seu output_schema) ou via inspecao do Pydantic schema dos agentes.

import type { Edge, Node } from "@xyflow/react"

import type { StrataNodeData } from "../_components/StrataNode"

import { getEtapaLabel } from "./glossary"

export type FieldType = "string" | "number" | "boolean" | "date" | "list" | "unknown"

export type AvailableField = {
  /** Chave (acessor): cnpj, razao_social, summary... */
  key: string
  /** Nome amigavel: "CNPJ", "Razao social", "Resumo executivo". */
  label: string
  /** Tipo (controla operadores no ConditionBuilder). */
  type: FieldType
}

export type AvailableSource = {
  /** "trigger" ou node.id. */
  sourceId: string
  /** "Inicio do fluxo" ou label da etapa. */
  sourceLabel: string
  /** Campos exposes no output. */
  fields: AvailableField[]
}

// ─── Mapa hardcoded de output por tipo de etapa ──────────────────────────
//
// MVP — em Phase 2 vem do backend ou de inspecao do schema Pydantic.

/** Campos expostos pelo trigger_data de um dossie. Espelha o
 *  trigger_data construido em
 *  `backend/app/modules/credito/services/dossier.py::create_dossier`.
 *  `cnpj` e `target_cnpj` sao aliases — ambos resolvem pro mesmo valor. */
const TRIGGER_FIELDS: AvailableField[] = [
  { key: "cnpj",          label: "CNPJ",                type: "string" },
  { key: "target_cnpj",   label: "CNPJ (alvo)",         type: "string" },
  { key: "target_name",   label: "Razao social (alvo)", type: "string" },
  { key: "dossier_id",    label: "ID do dossie",        type: "string" },
]

/** Outputs por agente especialista (espelha output_schemas.py). */
/** Public lookup: campos do output schema de um specialist agent.
 *  Reutilizado pelo AgentHoverCard (palette tooltip) para mostrar o que
 *  cada agente produz. Retorna [] quando o agente nao tem mapping. */
export function getAgentOutputFields(agentName: string): AvailableField[] {
  return AGENT_OUTPUT_FIELDS[agentName] ?? []
}

const AGENT_OUTPUT_FIELDS: Record<string, AvailableField[]> = {
  social_contract_analyst: [
    { key: "summary",                              label: "Resumo executivo",              type: "string"  },
    { key: "qsa_changes_recent",                   label: "Houve troca recente de QSA",    type: "boolean" },
    { key: "qsa_changes_detail",                   label: "Detalhe da troca de QSA",       type: "string"  },
    { key: "object_compatible_with_operation",     label: "Objeto compativel com operacao",type: "boolean" },
    { key: "object_compatibility_rationale",       label: "Justificativa do objeto",       type: "string"  },
    { key: "red_flags",                            label: "Red flags identificados",       type: "list"    },
    { key: "checklist_results",                    label: "Resultados do checklist",       type: "list"    },
  ],
  financial_analyst: [
    { key: "summary",            label: "Resumo executivo",       type: "string" },
    { key: "revenue_trend",      label: "Tendencia de receita",   type: "string" },
    { key: "seasonality_detected", label: "Sazonalidade detectada",type: "boolean" },
    { key: "seasonality_pattern", label: "Padrao de sazonalidade",type: "string" },
    { key: "indicators",         label: "Indicadores financeiros",type: "list"   },
    { key: "red_flags",          label: "Red flags",              type: "list"   },
    { key: "checklist_results",  label: "Resultados do checklist",type: "list"   },
  ],
  indebtedness_analyst: [
    { key: "summary",                  label: "Resumo executivo",       type: "string"  },
    { key: "total_debt_brl",           label: "Divida total (R$)",      type: "number"  },
    { key: "concentration_top_bank",   label: "Concentracao no maior banco (%)",type: "number" },
    { key: "ratings_distribution",     label: "Distribuicao por rating",type: "list"    },
    { key: "red_flags",                label: "Red flags",              type: "list"    },
    { key: "checklist_results",        label: "Resultados do checklist",type: "list"    },
  ],
  legal_analyst: [
    { key: "summary",                label: "Resumo executivo",       type: "string"  },
    { key: "high_risk_processes",    label: "Processos de alto risco (qtd)", type: "number" },
    { key: "total_processes",        label: "Total de processos",     type: "number"  },
    { key: "red_flags",              label: "Red flags",              type: "list"    },
    { key: "checklist_results",      label: "Resultados do checklist",type: "list"    },
  ],
  partner_analyst: [
    { key: "summary",                label: "Resumo executivo",       type: "string"  },
    { key: "partners_count",         label: "Quantidade de socios",   type: "number"  },
    { key: "high_risk_partners",     label: "Socios de alto risco (qtd)",type: "number" },
    { key: "red_flags",              label: "Red flags",              type: "list"    },
    { key: "checklist_results",      label: "Resultados do checklist",type: "list"    },
  ],
  commercial_visit_analyst: [
    { key: "summary",                label: "Resumo executivo",       type: "string"  },
    { key: "consistency",            label: "Consistencia com declaracoes",type: "string" },
    { key: "red_flags",              label: "Red flags",              type: "list"    },
    { key: "checklist_results",      label: "Resultados do checklist",type: "list"    },
  ],
  cross_reference_analyst: [
    { key: "summary",                label: "Resumo executivo",       type: "string"  },
    { key: "inconsistencies_count",  label: "Inconsistencias detectadas (qtd)",type: "number" },
    { key: "confidence_level",       label: "Nivel de confianca",     type: "string"  },
    { key: "red_flags",              label: "Red flags",              type: "list"    },
  ],
  opinion_writer: [
    { key: "executive_summary",      label: "Sumario executivo",      type: "string"  },
    { key: "recommendation",         label: "Recomendacao",           type: "string"  },
    { key: "strengths",              label: "Pontos fortes",          type: "list"    },
    { key: "concerns",               label: "Preocupacoes",           type: "list"    },
    { key: "conditions",             label: "Condicoes",              type: "list"    },
  ],
  document_extractor: [
    { key: "extracted_data",         label: "Dados extraidos",        type: "list"    },
    { key: "confidence_overall",     label: "Confianca geral (0-1)",  type: "number"  },
  ],
  pleito_extractor: [
    { key: "produto",                label: "Produto",                type: "string"  },
    { key: "volume_brl",             label: "Volume (R$)",            type: "number"  },
    { key: "taxa_estimada",          label: "Taxa estimada (% am)",   type: "number"  },
    { key: "prazo_dias",             label: "Prazo (dias)",           type: "number"  },
  ],
}

/** Bureaus tem outputs comuns. Map por adapter. Espelha o output real
 *  retornado pelo BureauQueryNode (`backend/app/shared/workflow/nodes/
 *  bureau_query.py`). Para Serasa PJ os scores detalhados ficam no
 *  warehouse silver — etapas downstream leem via `consulta_id`. */
const BUREAU_OUTPUT_FIELDS: Record<string, AvailableField[]> = {
  serasa_pj: [
    { key: "consulta_id",             label: "ID da consulta",                  type: "string"  },
    { key: "cnpj",                    label: "CNPJ consultado",                 type: "string"  },
    { key: "actual_report_returned",  label: "Relatorio retornado",             type: "string"  },
    { key: "reciprocity_downgrade",   label: "Houve downgrade de reciprocidade",type: "boolean" },
    { key: "latency_ms",              label: "Latencia (ms)",                   type: "number"  },
    { key: "counts.socios",           label: "Socios identificados (qtd)",      type: "number"  },
    { key: "counts.restricoes",       label: "Restricoes (qtd)",                type: "number"  },
    { key: "counts.participacoes",    label: "Participacoes (qtd)",             type: "number"  },
    { key: "counts.enderecos",        label: "Enderecos (qtd)",                 type: "number"  },
    { key: "counts.consultas_total_12m",        label: "Consultas Serasa (12 meses)",     type: "number"  },
    { key: "counts.consultas_listadas_detalhe", label: "Consultas listadas em detalhe",   type: "number"  },
    { key: "counts.predecessores",    label: "Empresas predecessoras (qtd)",    type: "number"  },
    { key: "counts.business_references", label: "Referencias comerciais (qtd)", type: "number"  },
  ],
  serasa_pf: [
    // Adapter ainda nao wired — fica disponivel quando ligar.
    { key: "consulta_id",        label: "ID da consulta",   type: "string" },
    { key: "cpf",                label: "CPF consultado",   type: "string" },
  ],
  bigdatacorp: [
    { key: "consulta_id",        label: "ID da consulta",        type: "string" },
    { key: "score_credito",      label: "Score de credito",      type: "number" },
    { key: "ativo_estimado",     label: "Ativo estimado (R$)",   type: "number" },
    { key: "funcionarios",       label: "Funcionarios (qtd)",    type: "number" },
  ],
  infosimples: [
    { key: "consulta_id",        label: "ID da consulta",        type: "string" },
    { key: "situacao_cadastral", label: "Situacao cadastral",    type: "string" },
    { key: "porte",              label: "Porte",                 type: "string" },
  ],
}

const HTTP_DEFAULT_FIELDS: AvailableField[] = [
  { key: "status_code", label: "Status HTTP", type: "number" },
  { key: "body",        label: "Corpo da resposta (JSON)", type: "list" },
]

// ─── Compute available outputs ───────────────────────────────────────────

/** Outputs expostos por uma etapa, dado o tipo + config + label. */
export function getNodeOutputFields(
  data: StrataNodeData,
): AvailableField[] {
  switch (data.nodeType) {
    case "human_input": {
      const fields = (data.config?.fields as Array<{ key: string; label?: string; type?: string }> | undefined) ?? []
      return fields.map((f) => ({
        key: f.key,
        label: f.label ?? f.key,
        type: mapFieldType(f.type),
      }))
    }
    case "specialist_agent": {
      const agent = data.config?.agent as string | undefined
      if (!agent) return []
      return AGENT_OUTPUT_FIELDS[agent] ?? []
    }
    case "document_extractor":
      return AGENT_OUTPUT_FIELDS.document_extractor ?? []
    case "bureau_query": {
      const adapter = data.config?.adapter as string | undefined
      if (!adapter) return []
      return BUREAU_OUTPUT_FIELDS[adapter] ?? []
    }
    case "http_request":
      return HTTP_DEFAULT_FIELDS
    case "conditional_branch":
      return [
        { key: "result", label: "Resultado da decisao (true/false)", type: "boolean" },
      ]
    case "human_review":
      return [
        { key: "approved", label: "Aprovado pelo analista", type: "boolean" },
        { key: "comment",  label: "Comentario do analista", type: "string"  },
      ]
    default:
      return []
  }
}

function mapFieldType(t: string | undefined): FieldType {
  switch (t) {
    case "number": return "number"
    case "boolean": return "boolean"
    case "date": return "date"
    case "select":
    case "list": return "list"
    case "string":
    case "cnpj":
    case "cpf":
    case "email":
    case "textarea":
    case "json":
    default: return "string"
  }
}

// ─── Upstream traversal ──────────────────────────────────────────────────

/** Encontra todos os IDs de etapas upstream da etapa-alvo (transitivo). */
export function findUpstreamNodeIds(
  targetNodeId: string,
  edges: Edge[],
): Set<string> {
  const reverseAdj = new Map<string, string[]>()
  for (const e of edges) {
    if (!reverseAdj.has(e.target)) reverseAdj.set(e.target, [])
    reverseAdj.get(e.target)!.push(e.source)
  }
  const visited = new Set<string>()
  const stack = [targetNodeId]
  while (stack.length > 0) {
    const cur = stack.pop()!
    for (const upstream of reverseAdj.get(cur) ?? []) {
      if (!visited.has(upstream)) {
        visited.add(upstream)
        stack.push(upstream)
      }
    }
  }
  return visited
}

/** Lista todos os AvailableSources que uma etapa pode referenciar.
 *  Inclui o trigger sempre. */
export function getAvailableSources(
  targetNodeId: string,
  nodes: Node[],
  edges: Edge[],
): AvailableSource[] {
  const upstreamIds = findUpstreamNodeIds(targetNodeId, edges)
  const sources: AvailableSource[] = []

  // Trigger sempre primeiro.
  sources.push({
    sourceId: "trigger",
    sourceLabel: "Inicio do fluxo",
    fields: TRIGGER_FIELDS,
  })

  for (const n of nodes) {
    if (!upstreamIds.has(n.id)) continue
    const data = n.data as unknown as StrataNodeData
    const fields = getNodeOutputFields(data)
    if (fields.length === 0) continue
    sources.push({
      sourceId: n.id,
      sourceLabel: data.label || getEtapaLabel(data.nodeType, data.config ?? {}),
      fields,
    })
  }

  return sources
}

// ─── Template syntax serialization ───────────────────────────────────────
//
// Backend espera `{{trigger.<field>}}` ou `{{node.<id>.output.<field>}}`.
// Estas funcoes traduzem entre o backend e o picker visual.

export type FieldRef =
  | { kind: "trigger"; field: string }
  | { kind: "node"; nodeId: string; field: string }
  | { kind: "literal"; value: string }

/** Serializa um FieldRef pro template syntax do backend. */
export function refToTemplate(ref: FieldRef): string {
  if (ref.kind === "trigger") return `{{trigger.${ref.field}}}`
  if (ref.kind === "node") return `{{node.${ref.nodeId}.output.${ref.field}}}`
  return ref.value
}

/** Tenta parsear template syntax. Retorna `literal` se nao bate. */
export function parseTemplate(s: string): FieldRef {
  const trim = s.trim()
  const triggerMatch = /^\{\{trigger\.([a-zA-Z0-9_.]+)\}\}$/.exec(trim)
  if (triggerMatch) return { kind: "trigger", field: triggerMatch[1] }
  const nodeMatch = /^\{\{node\.([a-zA-Z0-9_-]+)\.output\.([a-zA-Z0-9_.]+)\}\}$/.exec(trim)
  if (nodeMatch) return { kind: "node", nodeId: nodeMatch[1], field: nodeMatch[2] }
  return { kind: "literal", value: s }
}

// ─── Condition expression (== / != / >= / <= / > / <) ───────────────────

export type ConditionOperator = "==" | "!=" | ">=" | "<=" | ">" | "<"

export type Condition = {
  left: FieldRef
  operator: ConditionOperator
  right: FieldRef // pode ser literal pra valor "constante"
}

/** Serializa condition pro formato que o backend resolver entende. */
export function conditionToString(cond: Condition): string {
  const l = refToTemplate(cond.left)
  const r =
    cond.right.kind === "literal"
      ? quoteLiteral(cond.right.value)
      : refToTemplate(cond.right)
  return `${l} ${cond.operator} ${r}`
}

function quoteLiteral(v: string): string {
  // Numero ou boolean: nao quote.
  if (/^-?\d+(\.\d+)?$/.test(v)) return v
  if (v === "true" || v === "false") return v
  // String: quote (aspas duplas — backend resolver aceita).
  return `"${v.replace(/"/g, '\\"')}"`
}

const OP_REGEX = /\s*(==|!=|>=|<=|>|<)\s*/

/** Tenta parsear uma string de condicao no formato "L op R". */
export function parseCondition(s: string): Condition | null {
  const m = s.match(OP_REGEX)
  if (!m) return null
  const idx = m.index!
  const op = m[1] as ConditionOperator
  const leftStr = s.slice(0, idx).trim()
  const rightStr = s.slice(idx + m[0].length).trim()
  if (!leftStr || !rightStr) return null
  return {
    left: parseTemplate(leftStr),
    operator: op,
    right: parseRightSide(rightStr),
  }
}

function parseRightSide(s: string): FieldRef {
  const trim = s.trim()
  // Quoted string?
  if (/^".*"$/.test(trim)) {
    return { kind: "literal", value: trim.slice(1, -1).replace(/\\"/g, '"') }
  }
  // Numero ou boolean?
  if (/^-?\d+(\.\d+)?$/.test(trim) || trim === "true" || trim === "false") {
    return { kind: "literal", value: trim }
  }
  // Template?
  return parseTemplate(trim)
}
