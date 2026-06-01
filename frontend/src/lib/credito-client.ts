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
  /** Fan-in semantics quando o node tem 2+ incoming edges.
   * "all" = espera todas; "any" = qualquer uma dispara. Default backend: "all". */
  join_mode?: "any" | "all"
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

/** One declared input slot for a specialist agent (Phase A migration).
 *  Fed by `node.config.input_bindings = { [name]: "<ref-path>" }`.
 *  When `inputs` is empty, the agent is on the legacy text-dump path. */
export type AgentInputMeta = {
  name: string
  /** VarType value as string (e.g. "cnpj", "score", "money_brl"). */
  type: string
  description: string
  optional: boolean
}

/** Per-agent metadata exposed by GET /credito/agent-catalog.
 *  Used by the editor to render the input-binding UI for specialist_agent
 *  nodes and to decide whether the agent is on the structured-context path
 *  (`inputs.length > 0`) or the legacy fallback path (`inputs.length === 0`). */
export type AgentMeta = {
  name: string
  description: string
  section_id: string
  multimodal: boolean
  inputs: AgentInputMeta[]
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

export type NextActionKind =
  | "human_input"
  | "agent_running"
  | "blocked"
  | "ready_to_finalize"
  | "finalized"

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
  /** Number of node_runs em status COMPLETED — popula o ProgressCell. */
  completed_steps: number
  /** Total de nodes do workflow_definition.graph. */
  total_steps: number
  next_action_kind: NextActionKind
  /** Pt-BR pronto pra UI (ex.: "Aguardando voce", "Analise IA em curso"). */
  next_action_label: string
  /** Para deep-link na listagem (?step=...). */
  next_node_id: string | null
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

// ─── Evidence (attachments + step notes + step links) ────────────────────

export type AttachmentRead = {
  id: string
  dossier_id: string
  node_id: string | null
  filename: string
  mime_type: string
  size_bytes: number
  sha256: string
  description: string | null
  uploaded_by: string | null
  uploaded_at: string
}

export type NoteRead = {
  id: string
  dossier_id: string
  node_id: string
  body_md: string
  pinned: boolean
  author_id: string | null
  created_at: string
  updated_at: string
}

export type NoteCreatePayload = {
  node_id: string
  body_md: string
  pinned?: boolean
}

export type NoteUpdatePayload = {
  body_md?: string
  pinned?: boolean
}

export type LinkRead = {
  id: string
  dossier_id: string
  node_id: string | null
  url: string
  title: string | null
  description: string | null
  added_by: string | null
  added_at: string
}

export type LinkCreatePayload = {
  node_id?: string | null
  url: string
  title?: string | null
  description?: string | null
}

export type NodeDraftResponse = {
  saved_at: string
  node_id: string
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

export type RedFlagItem = {
  id: string
  section: string | null
  severity: "critical" | "important" | "informational"
  title: string
  description: string
  evidence: string
  check_type: string | null
  provenance: Record<string, unknown> | null
  decision_log_id: string | null
  raised_by_agent: string | null
  analyst_resolution: string | null
  analyst_notes: string | null
  created_at: string | null
}

export type DossierStateResponse = {
  dossier: DossierRead
  run: WorkflowRunSummary | null
  node_runs: NodeRunSummary[]
  pending_node: NodeRunSummary | null
  red_flags: RedFlagItem[]
}

export type NodeSubmitPayload = {
  values: Record<string, unknown>
}

export type OpinionInput = {
  executive_summary: string
  recommendation: "approve" | "deny" | "conditional"
  strengths?: string[]
  concerns?: string[]
  conditions?: string[]
}

export type FinalizePayload = {
  node_id: string
  opinion: OpinionInput
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

/**
 * Multipart upload helper used by `credito.attachments.upload`.
 * The shared `apiClient` only does JSON; this falls back to direct fetch.
 */
async function _uploadMultipart<T>(
  path: string,
  form: FormData,
): Promise<T> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1"
  const tokenKey = "gr.token"
  const headers: Record<string, string> = {}
  if (typeof window !== "undefined") {
    const token = window.localStorage.getItem(tokenKey)
    if (token) headers["Authorization"] = `Bearer ${token}`
  }
  const res = await fetch(`${apiUrl}${path}`, {
    method: "POST",
    headers,
    body: form,
    cache: "no-store",
  })
  if (!res.ok) {
    let detail: unknown = res.statusText
    try {
      const err = (await res.json()) as { detail?: unknown }
      if (err.detail !== undefined && err.detail !== null) detail = err.detail
    } catch {
      // non-JSON response, fallback to statusText
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail))
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

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
    remove: (id: string) =>
      apiClient.delete<void>(`/credito/dossies/${id}`),
    getState: (id: string) =>
      apiClient.get<DossierStateResponse>(`/credito/dossies/${id}/state`),
    submitNodeInput: (id: string, nodeId: string, values: Record<string, unknown>) =>
      apiClient.post<DossierStateResponse>(
        `/credito/dossies/${id}/nodes/${nodeId}/submit`,
        { values } satisfies NodeSubmitPayload,
      ),
    /** Auto-save de form values num node WAITING_INPUT — nao avanca o run. */
    saveNodeDraft: (id: string, nodeId: string, values: Record<string, unknown>) =>
      apiClient.patch<NodeDraftResponse>(
        `/credito/dossies/${id}/nodes/${nodeId}/draft`,
        { values },
      ),
    /** Finaliza: cria o parecer (credit_dossier_opinion) e conclui o checkpoint. */
    finalize: (id: string, payload: FinalizePayload) =>
      apiClient.post<DossierStateResponse>(
        `/credito/dossies/${id}/finalize`,
        payload,
      ),
    /** Reprocessa um node (e tudo a jusante). Sem body. */
    rerunNode: (id: string, nodeId: string) =>
      apiClient.post<DossierStateResponse>(
        `/credito/dossies/${id}/nodes/${nodeId}/rerun`,
      ),
  },
  attachments: {
    list: (dossierId: string, nodeId?: string | null) => {
      const qs = nodeId ? `?node_id=${encodeURIComponent(nodeId)}` : ""
      return apiClient.get<AttachmentRead[]>(
        `/credito/dossies/${dossierId}/attachments${qs}`,
      )
    },
    upload: (
      dossierId: string,
      file: File,
      opts?: { node_id?: string | null; description?: string | null },
    ) => {
      const form = new FormData()
      form.append("file", file)
      if (opts?.node_id) form.append("node_id", opts.node_id)
      if (opts?.description) form.append("description", opts.description)
      return _uploadMultipart<AttachmentRead>(
        `/credito/dossies/${dossierId}/attachments`,
        form,
      )
    },
    remove: (dossierId: string, attachmentId: string) =>
      apiClient.delete<void>(
        `/credito/dossies/${dossierId}/attachments/${attachmentId}`,
      ),
    /** URL absoluta para `<a href>` — passa Bearer token via cookie nao. */
    downloadUrl: (dossierId: string, attachmentId: string) => {
      const apiUrl =
        process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1"
      return `${apiUrl}/credito/dossies/${dossierId}/attachments/${attachmentId}/download`
    },
  },
  notes: {
    list: (dossierId: string, nodeId?: string | null) => {
      const qs = nodeId ? `?node_id=${encodeURIComponent(nodeId)}` : ""
      return apiClient.get<NoteRead[]>(
        `/credito/dossies/${dossierId}/notes${qs}`,
      )
    },
    create: (dossierId: string, payload: NoteCreatePayload) =>
      apiClient.post<NoteRead>(`/credito/dossies/${dossierId}/notes`, payload),
    update: (dossierId: string, noteId: string, payload: NoteUpdatePayload) =>
      apiClient.patch<NoteRead>(
        `/credito/dossies/${dossierId}/notes/${noteId}`,
        payload,
      ),
    remove: (dossierId: string, noteId: string) =>
      apiClient.delete<void>(`/credito/dossies/${dossierId}/notes/${noteId}`),
  },
  links: {
    list: (dossierId: string, nodeId?: string | null) => {
      const qs = nodeId ? `?node_id=${encodeURIComponent(nodeId)}` : ""
      return apiClient.get<LinkRead[]>(
        `/credito/dossies/${dossierId}/links${qs}`,
      )
    },
    create: (dossierId: string, payload: LinkCreatePayload) =>
      apiClient.post<LinkRead>(`/credito/dossies/${dossierId}/links`, payload),
    remove: (dossierId: string, linkId: string) =>
      apiClient.delete<void>(`/credito/dossies/${dossierId}/links/${linkId}`),
  },
  workflows: {
    list: () => apiClient.get<WorkflowDefinitionRead[]>("/credito/workflows"),
    get: (id: string) => apiClient.get<WorkflowDefinitionRead>(`/credito/workflows/${id}`),
    nodeTypes: () => apiClient.get<NodeTypeMeta[]>("/credito/node-types"),
    agentCatalog: () => apiClient.get<AgentMeta[]>("/credito/agent-catalog"),
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
