// src/app/(app)/credito/workflows/[id]/editor/_lib/glossary.ts
//
// Glossario do editor de fluxo — vocabulario do dominio em vez de tecnico.
//
// Toda string visivel ao usuario passa por aqui. Mudanca de vocabulario,
// SEM mudanca de modelo de dados (os types canonicos seguem em ingles —
// `node`, `edge`, `workflow` — porque sao a API publica do backend).
//
// Quando precisar de um nome amigavel, use `glossary.X` em vez de hard-code.

export const glossary = {
  // ── Conceitos macro ────────────────────────────────────────────────────
  workflow: "Fluxo",
  workflowPlural: "Fluxos",
  workflowDefinition: "Modelo de fluxo",
  workflowRun: "Execucao do fluxo",

  // ── Componentes do graph ───────────────────────────────────────────────
  node: "Etapa",
  nodePlural: "Etapas",
  nodeType: "Tipo de etapa",
  edge: "Conexao",
  edgePlural: "Conexoes",
  edgeWithCondition: "Decisao",

  // ── Campos da etapa ────────────────────────────────────────────────────
  label: "Nome da etapa",
  config: "Configuracao",
  condition: "Quando seguir por aqui",

  // ── Status / lifecycle ─────────────────────────────────────────────────
  statusDraft: "Rascunho",
  statusActive: "Publicado",
  statusArchived: "Arquivado",
  isActiveVersion: "Versao em uso",

  // ── Acoes ──────────────────────────────────────────────────────────────
  saveAsNewVersion: "Salvar mudancas",
  publish: "Publicar",
  activate: "Publicar (usar a partir de agora)",
  deactivate: "Voltar para rascunho",
  testFlow: "Testar playbook",
  back: "Voltar",

  // ── Estados da UI ──────────────────────────────────────────────────────
  unsavedChanges: "Mudancas nao salvas",
  saving: "Salvando...",
  savedNow: "Salvo agora",
  selectAStep: "Selecione uma etapa no canvas para ver e editar.",
  paletteHint: "Arraste para o canvas",

  // ── Validacao ──────────────────────────────────────────────────────────
  validationOk: "Tudo certo",
  validationProblems: (n: number) =>
    n === 1 ? "1 problema" : `${n} problemas`,
  validationBlocking: "Bloqueando publicacao",
} as const

// ── Mapa: nome tecnico do tipo de etapa → nome amigavel curto ────────────
//
// Espelha `backend/app/shared/workflow/nodes/registry.py` mas em domain
// language. Quando um novo tipo for adicionado no backend, adicione aqui.

export const ETAPA_LABEL: Record<string, string> = {
  trigger: "Inicio do playbook",
  human_input: "Pedir dados ao analista",
  document_request: "Pedir documentos",
  document_extractor: "Ler documentos com IA",
  bureau_query: "Consultar bureau",
  official_document_fetch: "Buscar documento oficial",
  http_request: "Chamar servico externo",
  specialist_agent: "Analise IA",
  cross_reference: "Cruzar dados",
  human_review: "Revisao do analista",
  conditional_branch: "Decisao automatica",
  consolidator: "Consolidador",
  notification: "Notificar",
  output_generator: "Gerar saida",
  parallel: "Esperar etapas paralelas",
}

// ── Mapa: agent name → nome amigavel pra "Analise IA" ────────────────────
//
// Quando uma etapa specialist_agent tem `config.agent = "financial_analyst"`,
// o usuario ve "Analise financeira" em vez de "specialist_agent".
// Espelha `backend/app/shared/agents/catalog.py`.

export const AGENT_FRIENDLY_LABEL: Record<string, string> = {
  social_contract_analyst: "Analise de contrato social",
  cadastral_analyst: "Analise cadastral",
  financial_analyst: "Analise financeira",
  revenue_analyst: "Analise de faturamento",
  indebtedness_analyst: "Analise de endividamento",
  legal_analyst: "Analise juridica",
  partner_analyst: "Analise de socios",
  commercial_visit_analyst: "Analise de visita comercial",
  cross_reference_analyst: "Cruzar dados (cross-reference)",
  opinion_writer: "Gerar parecer final",
  document_extractor: "Ler documentos com IA",
  pleito_extractor: "Extrair pleito de texto livre",
}

// ── section_id de cada agente → section do checklist ─────────────────────
//
// Espelha o `section_id` de cada agente em catalog.py (backend). Usado pra
// linkar do inspector da etapa "Analise IA" pra `/credito/criterios?section=...`.

export const AGENT_SECTION_ID: Record<string, string> = {
  social_contract_analyst: "social_contract",
  cadastral_analyst: "cadastral",
  financial_analyst: "financial",
  revenue_analyst: "revenue",
  indebtedness_analyst: "indebtedness",
  legal_analyst: "legal",
  partner_analyst: "partners",
  commercial_visit_analyst: "commercial_visit",
  cross_reference_analyst: "cross_reference",
  opinion_writer: "opinion",
  document_extractor: "documents",
  pleito_extractor: "plea",
}

// ── Helper: pega o nome amigavel de uma etapa do graph ───────────────────
//
// Considera o agent quando aplicavel (ex.: specialist_agent com agent
// configurado vira "Analise financeira" nao "Analise IA").

export function getEtapaLabel(
  nodeType: string,
  config: Record<string, unknown> = {},
): string {
  if (nodeType === "specialist_agent") {
    const agent = config.agent as string | undefined
    if (agent && AGENT_FRIENDLY_LABEL[agent]) {
      return AGENT_FRIENDLY_LABEL[agent]
    }
  }
  return ETAPA_LABEL[nodeType] ?? nodeType
}
