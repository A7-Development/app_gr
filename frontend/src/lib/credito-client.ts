// src/lib/credito-client.ts
//
// Cliente HTTP do modulo Credito.
//
// Espelha os Pydantic schemas em backend/app/modules/credito/schemas/ +
// app/shared/workflow/schemas/. Endpoints documentados em
// backend/app/modules/credito/api/.

import { apiClient } from "@/lib/api-client"

// ─── Workflow types ──────────────────────────────────────────────────────

export type WorkflowStatus = "draft" | "active" | "archived"
export type RunStatus =
  | "pending"
  | "running"
  | "paused"
  | "completed"
  | "failed"
  | "cancelled"
export type NodeStatus =
  | "pending"
  | "running"
  | "waiting_input"
  | "completed"
  | "failed"
  | "skipped"

export type NodeSpec = {
  id: string
  type: string
  label: string | null
  config: Record<string, unknown>
  position?: { x: number; y: number } | null
}

export type EdgeSpec = {
  id: string
  source: string
  target: string
  condition: string | null
}

export type WorkflowGraph = {
  nodes: NodeSpec[]
  edges: EdgeSpec[]
}

export type WorkflowDefinitionRead = {
  id: string
  tenant_id: string | null
  name: string
  version: number
  description: string | null
  category: string
  graph: WorkflowGraph
  status: WorkflowStatus
  created_by: string | null
  created_at: string
  archived_at: string | null
}

export type WorkflowCreatePayload = {
  name: string
  description?: string | null
  // From scratch:
  category?: string
  graph?: WorkflowGraph
  // Or clone:
  clone_from?: string
}

export type WorkflowUpdatePayload = {
  description?: string | null
  graph: WorkflowGraph
}

export type NodeConfigField = {
  key: string
  type: "string" | "number" | "boolean" | "json" | "text"
  label: string
  placeholder?: string
  required?: boolean
}

export type NodeTypeMeta = {
  type: string
  label: string
  category:
    | "triggers"
    | "humano"
    | "coleta"
    | "agentes"
    | "logica"
    | "integracao"
    | "output"
  description: string
  available: boolean
  icon: string
  config_schema?: NodeConfigField[]
}

// ─── Semantic validation (Fase 2) ────────────────────────────────────────

export type SemanticValidationError = {
  node_id: string
  severity: "error" | "warning"
  code: string
  message: string
  requirement?: string | null
  expected_type?: string | null
  found_type?: string | null
}

export type SemanticValidationResult = {
  has_errors: boolean
  errors: SemanticValidationError[]
  /** node_id -> { var_name: vartype }. Usado pra renderizar chips
   *  de output tipados em cada nó e pill list de variáveis upstream. */
  produced_by_node: Record<string, Record<string, string>>
}

// ─── Dry-run (Fase 3b) ────────────────────────────────────────────────────

export type DryRunStep = {
  node_id: string
  node_type: string
  label: string
  status: "completed" | "failed" | "skipped" | "unavailable"
  output: Record<string, unknown>
  /** Tempo sintético por tipo de nó (ms). Não é tempo real — é uma
   *  estimativa pra dar ordem de grandeza ("Serasa demora ~4s"). */
  duration_ms: number
  error: string | null
}

export type DryRunResult = {
  final_status: "completed" | "failed"
  error: string | null
  steps: DryRunStep[]
}

// ─── Dossier types ───────────────────────────────────────────────────────

export type DossierStatus =
  | "draft"
  | "collecting"
  | "analyzing"
  | "review"
  | "finalized"
  | "cancelled"

export type DossierListItem = {
  id: string
  target_cnpj: string | null
  target_name: string | null
  status: DossierStatus
  operation_type: string | null
  requested_amount: string | null
  analyst_id: string | null
  workflow_definition_id: string
  workflow_run_id: string | null
  created_at: string
  updated_at: string
}

export type DossierRead = DossierListItem & {
  tenant_id: string
  requested_term_days: number | null
  finalized_at: string | null
  notes: string | null
}

export type DossierCreatePayload = {
  workflow_definition_id: string
  target_cnpj?: string | null
  target_name?: string | null
  operation_type?: string | null
  requested_amount?: string | null
  requested_term_days?: number | null
  notes?: string | null
}

// ─── Workflow run state (read by dossier detail page) ────────────────────

export type FormFieldType =
  | "string"
  | "cnpj"
  | "cpf"
  | "email"
  | "textarea"
  | "select"
  | "number"
  | "date"
  | "json"
  | "boolean"

export type FormField = {
  key: string
  type: FormFieldType
  label: string
  required?: boolean
  placeholder?: string
  options?: string[] // for select
}

export type WorkflowRunSummary = {
  id: string
  status: RunStatus
  started_at: string | null
  completed_at: string | null
  paused_at: string | null
  trigger_data: Record<string, unknown>
  context_data: Record<string, unknown>
  error_detail: string | null
}

export type NodeRunSummary = {
  id: string
  node_id: string
  node_type: string
  status: NodeStatus
  input_data: Record<string, unknown>
  output_data: Record<string, unknown>
  started_at: string | null
  completed_at: string | null
  duration_ms: number | null
  tokens_input: number
  tokens_output: number
  cost_brl: string
  error_detail: string | null
  attempt_number: number
}

export type DossierStateResponse = {
  dossier: DossierRead
  run: WorkflowRunSummary | null
  node_runs: NodeRunSummary[]
  pending_node: NodeRunSummary | null
}

export type NodeSubmitPayload = {
  values: Record<string, unknown>
}

// ─── Labels (pt-BR) ──────────────────────────────────────────────────────

export const DOSSIER_STATUS_LABEL: Record<DossierStatus, string> = {
  draft: "Rascunho",
  collecting: "Coletando",
  analyzing: "Analisando",
  review: "Em revisao",
  finalized: "Finalizado",
  cancelled: "Cancelado",
}

export const DOSSIER_STATUS_TONE: Record<DossierStatus, string> = {
  draft: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
  collecting: "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300",
  analyzing: "bg-violet-50 text-violet-700 dark:bg-violet-500/10 dark:text-violet-300",
  review: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
  finalized: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
  cancelled: "bg-gray-100 text-gray-500 dark:bg-gray-900 dark:text-gray-500",
}

export const NODE_CATEGORY_LABEL: Record<NodeTypeMeta["category"], string> = {
  triggers: "Triggers",
  humano: "Humano",
  coleta: "Coleta",
  agentes: "Agentes IA",
  logica: "Logica",
  integracao: "Integracao",
  output: "Output",
}

// Cores por categoria — usadas no node visual e na palette para reforcar
// identidade. Mantem aderencia ao §11.6 (cores institucionais por contexto).
export const NODE_CATEGORY_COLOR: Record<NodeTypeMeta["category"], string> = {
  triggers: "bg-emerald-500",
  humano: "bg-blue-500",
  coleta: "bg-amber-500",
  agentes: "bg-violet-500",
  logica: "bg-indigo-500",
  integracao: "bg-rose-500",
  output: "bg-gray-700",
}

// ─── Checklist (per-tenant analysis items) ───────────────────────────────

export type CheckSeverity = "critical" | "important" | "informational"

export type ChecklistItemRead = {
  id: string
  tenant_id: string | null
  section: string
  code: string
  description: string
  guidance: string | null
  severity: CheckSeverity
  auto_evaluable: boolean
  order_index: number
  active: boolean
  created_at: string
}

export type ChecklistItemUpsertPayload = {
  section: string
  code: string
  description: string
  guidance?: string | null
  severity?: CheckSeverity
  auto_evaluable?: boolean
  order_index?: number
  active?: boolean
}

export const SEVERITY_LABEL: Record<CheckSeverity, string> = {
  critical: "Critico",
  important: "Importante",
  informational: "Informativo",
}

export const SEVERITY_TONE: Record<CheckSeverity, string> = {
  critical: "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",
  important: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
  informational: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
}

// ─── Document Templates (per-tenant extraction guides) ──────────────────

export type DocumentType =
  | "dre"
  | "balance_sheet"
  | "revenue_report"
  | "indebtedness"
  | "scr"
  | "income_tax_pf"
  | "cnh"
  | "rg"
  | "social_contract"
  | "commercial_visit"
  | "photo"
  | "abc_curve"
  | "plea_source"
  | "other"

export const DOCUMENT_TYPE_LABEL: Record<DocumentType, string> = {
  dre: "DRE",
  balance_sheet: "Balanco",
  revenue_report: "Faturamento",
  indebtedness: "Endividamento declarado",
  scr: "SCR Bacen",
  income_tax_pf: "IR pessoa fisica",
  cnh: "CNH",
  rg: "RG",
  social_contract: "Contrato social / Ata",
  commercial_visit: "Relatorio de visita",
  photo: "Foto das instalacoes",
  abc_curve: "Curva ABC",
  plea_source: "Pleito (fonte original)",
  other: "Outro",
}

export type DocumentTemplateRead = {
  id: string
  tenant_id: string | null
  doc_type: DocumentType
  name: string
  description: string | null
  fields_schema: Record<string, unknown>
  instructions: string | null
  active: boolean
  created_at: string
  updated_at: string
}

export type DocumentTemplateUpsertPayload = {
  doc_type: DocumentType
  name: string
  description?: string | null
  fields_schema?: Record<string, unknown>
  instructions?: string | null
  active?: boolean
}

// ─── Endpoints ───────────────────────────────────────────────────────────

export const credito = {
  dossies: {
    list: (params?: { status?: DossierStatus; limit?: number; offset?: number }) => {
      const qs = new URLSearchParams()
      if (params?.status) qs.set("status_filter", params.status)
      if (params?.limit) qs.set("limit", String(params.limit))
      if (params?.offset) qs.set("offset", String(params.offset))
      const suffix = qs.toString() ? `?${qs.toString()}` : ""
      return apiClient.get<DossierListItem[]>(`/credito/dossies${suffix}`)
    },
    get: (id: string) => apiClient.get<DossierRead>(`/credito/dossies/${id}`),
    create: (payload: DossierCreatePayload) =>
      apiClient.post<DossierRead>("/credito/dossies", payload),
    update: (id: string, payload: Partial<DossierCreatePayload>) =>
      apiClient.patch<DossierRead>(`/credito/dossies/${id}`, payload),
    getState: (id: string) =>
      apiClient.get<DossierStateResponse>(`/credito/dossies/${id}/state`),
    submitNodeInput: (id: string, nodeId: string, values: Record<string, unknown>) =>
      apiClient.post<DossierStateResponse>(
        `/credito/dossies/${id}/nodes/${nodeId}/submit`,
        { values } satisfies NodeSubmitPayload,
      ),
  },
  workflows: {
    list: () => apiClient.get<WorkflowDefinitionRead[]>("/credito/workflows"),
    get: (id: string) => apiClient.get<WorkflowDefinitionRead>(`/credito/workflows/${id}`),
    nodeTypes: () => apiClient.get<NodeTypeMeta[]>("/credito/node-types"),
    create: (payload: WorkflowCreatePayload) =>
      apiClient.post<WorkflowDefinitionRead>("/credito/workflows", payload),
    update: (id: string, payload: WorkflowUpdatePayload) =>
      apiClient.patch<WorkflowDefinitionRead>(`/credito/workflows/${id}`, payload),
    remove: (id: string) =>
      apiClient.delete<void>(`/credito/workflows/${id}`),
    activate: (name: string, definition_id: string) =>
      apiClient.put<WorkflowDefinitionRead>(`/credito/workflows/${name}/active`, {
        definition_id,
      }),
    validate: (graph: WorkflowGraph) =>
      apiClient.post<SemanticValidationResult>(
        "/credito/workflows/_validate",
        graph,
      ),
    dryRun: (workflowId: string, triggerData: Record<string, unknown>) =>
      apiClient.post<DryRunResult>(
        `/credito/workflows/${workflowId}/dry-run`,
        { trigger_data: triggerData },
      ),
    getActive: (name: string) =>
      apiClient.get<WorkflowDefinitionRead>(
        `/credito/workflows/${encodeURIComponent(name)}/active`,
      ),
  },
  checklist: {
    list: (params?: { section?: string; include_starter?: boolean }) => {
      const qs = new URLSearchParams()
      if (params?.section) qs.set("section", params.section)
      if (params?.include_starter !== undefined)
        qs.set("include_starter", String(params.include_starter))
      const suffix = qs.toString() ? `?${qs.toString()}` : ""
      return apiClient.get<ChecklistItemRead[]>(`/credito/checklist${suffix}`)
    },
    create: (payload: ChecklistItemUpsertPayload) =>
      apiClient.post<ChecklistItemRead>("/credito/checklist", payload),
    update: (id: string, payload: ChecklistItemUpsertPayload) =>
      apiClient.patch<ChecklistItemRead>(`/credito/checklist/${id}`, payload),
    remove: (id: string) => apiClient.delete<void>(`/credito/checklist/${id}`),
    clone: (id: string) =>
      apiClient.post<ChecklistItemRead>(`/credito/checklist/${id}/clone`),
  },
  templates: {
    list: (params?: { doc_type?: DocumentType; include_starter?: boolean }) => {
      const qs = new URLSearchParams()
      if (params?.doc_type) qs.set("doc_type", params.doc_type)
      if (params?.include_starter !== undefined)
        qs.set("include_starter", String(params.include_starter))
      const suffix = qs.toString() ? `?${qs.toString()}` : ""
      return apiClient.get<DocumentTemplateRead[]>(`/credito/templates${suffix}`)
    },
    create: (payload: DocumentTemplateUpsertPayload) =>
      apiClient.post<DocumentTemplateRead>("/credito/templates", payload),
    update: (id: string, payload: DocumentTemplateUpsertPayload) =>
      apiClient.patch<DocumentTemplateRead>(`/credito/templates/${id}`, payload),
    remove: (id: string) => apiClient.delete<void>(`/credito/templates/${id}`),
    clone: (id: string) =>
      apiClient.post<DocumentTemplateRead>(`/credito/templates/${id}/clone`),
  },
}
