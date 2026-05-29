/**
 * Cliente HTTP compartilhado para a API do GR.
 *
 * Regras:
 * - `NEXT_PUBLIC_API_URL` vem de `.env.local`
 * - Token JWT e armazenado em localStorage (chave `gr.token`)
 * - Toda resposta !ok vira uma ApiError com status + detail
 *
 * Uso tipico (com React Query):
 *
 *     import { useQuery } from "@tanstack/react-query"
 *     import { apiClient } from "@/lib/api-client"
 *
 *     useQuery({
 *       queryKey: ["me"],
 *       queryFn: () => apiClient.get("/auth/me"),
 *     })
 */

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1"

const TOKEN_STORAGE_KEY = "gr.token"

export class ApiError extends Error {
  status: number
  /**
   * Whatever the backend returned in the `detail` field. FastAPI lets you
   * raise `HTTPException(detail=<dict>)` to ship structured error payloads
   * (used by /workflows/_validate to return the full ValidationResult).
   * Callers can narrow the type at the use site.
   */
  detail: unknown

  constructor(status: number, detail: unknown) {
    super(`API ${status}: ${stringifyDetail(detail)}`)
    this.name = "ApiError"
    this.status = status
    this.detail = detail
  }
}

function stringifyDetail(detail: unknown): string {
  if (detail == null) return ""
  if (typeof detail === "string") return detail
  // Common case: backend returns `{ message: "...", ... }` for structured
  // errors. Surface the message field for the human-readable Error.message.
  if (typeof detail === "object" && "message" in detail) {
    const m = (detail as { message?: unknown }).message
    if (typeof m === "string") return m
  }
  try {
    return JSON.stringify(detail)
  } catch {
    return String(detail)
  }
}

function getToken(): string | null {
  if (typeof window === "undefined") return null
  return window.localStorage.getItem(TOKEN_STORAGE_KEY)
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return
  window.localStorage.setItem(TOKEN_STORAGE_KEY, token)
}

export function clearToken(): void {
  if (typeof window === "undefined") return
  window.localStorage.removeItem(TOKEN_STORAGE_KEY)
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  }
  const token = getToken()
  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }

  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    cache: "no-store",
  })

  if (!res.ok) {
    let detail: unknown = res.statusText
    try {
      const err = (await res.json()) as { detail?: unknown }
      if (err.detail !== undefined && err.detail !== null) detail = err.detail
    } catch {
      // nao-JSON, usa statusText
    }
    if (res.status === 401) {
      clearToken()
    }
    throw new ApiError(res.status, detail)
  }

  // 204 No Content
  if (res.status === 204) {
    return undefined as T
  }
  return (await res.json()) as T
}

/** GET de resposta binaria (CSV, XLSX, PDF). Usa o mesmo Bearer token. */
async function requestBlob(path: string): Promise<Blob> {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers["Authorization"] = `Bearer ${token}`

  const res = await fetch(`${API_URL}${path}`, {
    method: "GET",
    headers,
    cache: "no-store",
  })

  if (!res.ok) {
    let detail: unknown = res.statusText
    try {
      const err = (await res.json()) as { detail?: unknown }
      if (err.detail !== undefined && err.detail !== null) detail = err.detail
    } catch {
      // nao-JSON, fica statusText
    }
    if (res.status === 401) clearToken()
    throw new ApiError(res.status, detail)
  }
  return await res.blob()
}

/** Forca download de um Blob no browser. Usado por endpoints CSV/XLSX. */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export const apiClient = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body),
  delete: <T>(path: string) => request<T>("DELETE", path),
  getBlob: (path: string) => requestBlob(path),
}

//
// Tipos dos endpoints (espelham os Pydantic schemas do backend)
//

export type LoginResponse = {
  access_token: string
  token_type: string
  expires_in_minutes: number
}

export type Permission = "none" | "read" | "write" | "admin"

export type TenantRoleId = "owner" | "member" | "viewer"
export type TenantStatusId = "trial" | "active" | "suspended" | "cancelled"
export type ModuleId =
  | "bi"
  | "cadastros"
  | "operacoes"
  | "credito"
  | "controladoria"
  | "risco"
  | "integracoes"
  | "laboratorio"
  | "admin"

export type MeResponse = {
  user: {
    id: string
    email: string
    name: string
    tenant_role: TenantRoleId
  }
  tenant: {
    id: string
    slug: string
    name: string
    status: TenantStatusId
    is_system_maintainer: boolean
  }
  enabled_modules: string[]
  user_permissions: Record<string, Permission>
  ai_enabled: boolean
  ai_permission: Permission
}

//
// Tipos do modulo IA (transversal — ver CLAUDE.md sec 19)
//

export type AIQuota = {
  granted: number
  consumed: number
  carryover: number
  topup: number
  remaining: number
  exhausted: boolean
  period_yyyymm: string
}

export type AIConversationListItem = {
  id: string
  title: string | null
  page_context: string | null
  last_msg_at: string
  turn_count: number
}

export type AIConversationMessage = {
  id: string
  turn_index: number
  role: "user" | "ai"
  text: string
  occurred_at: string
}

export type AIInsightsResponse = {
  insights: { text: string }[]
  generated_at: string
}

// ───────────────────────────────────────────────────────────────────────────
// Admin IA — gestao de credenciais de provedores LLM (system maintainer)
// Espelha endpoints em backend/app/modules/admin/api/ai_provider_credentials.py
// ───────────────────────────────────────────────────────────────────────────

export type AIProvider = "openai" | "anthropic"

export type AIProviderCredentialRead = {
  id: string
  provider: AIProvider
  alias: string
  zdr_enabled: boolean
  active: boolean
  rotated_at: string | null
  notes: string | null
  created_at: string
}

export type AIProviderCredentialCreatePayload = {
  provider: AIProvider
  alias: string
  api_key: string
  org_id?: string | null
  zdr_enabled: boolean
  notes?: string | null
}

export type AIProviderCredentialUpdatePayload = {
  api_key?: string
  org_id?: string | null
  zdr_enabled?: boolean
  active?: boolean
  notes?: string | null
}

// ───────────────────────────────────────────────────────────────────────────
// Admin · Tenants (system maintainer)
// Espelha backend/app/modules/admin/api/tenants.py
// ───────────────────────────────────────────────────────────────────────────

export type TenantSubscriptionRead = {
  module: ModuleId
  enabled: boolean
  enabled_since: string | null
  enabled_until: string | null
  plan_ref: string | null
}

export type TenantRead = {
  id: string
  slug: string
  name: string
  subdomain: string | null
  status: TenantStatusId
  trial_ends_at: string | null
  is_system_maintainer: boolean
  ativo: boolean
  created_at: string
  updated_at: string
  subscriptions: TenantSubscriptionRead[]
  user_count: number
}

export type TenantCreatePayload = {
  slug: string
  name: string
  subdomain?: string | null
  status?: TenantStatusId
  trial_ends_at?: string | null
  owner_email: string
  enabled_modules: ModuleId[]
}

export type TenantUpdatePayload = {
  name?: string
  subdomain?: string | null
  status?: TenantStatusId
  trial_ends_at?: string | null
  ativo?: boolean
}

export type TenantSubscriptionUpdatePayload = {
  enabled: boolean
  plan_ref?: string | null
  enabled_until?: string | null
}

export type InvitationRead = {
  id: string
  tenant_id: string
  email: string
  role: TenantRoleId
  invited_by_id: string | null
  expires_at: string
  accepted_at: string | null
  revoked_at: string | null
  created_at: string
}

export type InvitationCreateResponse = {
  invitation: InvitationRead
  token: string
  accept_url: string
}

export type InvitationContext = {
  tenant_id: string
  tenant_name: string
  tenant_slug: string
  email: string
  role: TenantRoleId
  expires_at: string
}

export const adminTenants = {
  list: () => apiClient.get<TenantRead[]>("/admin/tenants"),
  get: (id: string) => apiClient.get<TenantRead>(`/admin/tenants/${id}`),
  create: (payload: TenantCreatePayload) =>
    apiClient.post<InvitationCreateResponse>("/admin/tenants", payload),
  update: (id: string, payload: TenantUpdatePayload) =>
    apiClient.patch<TenantRead>(`/admin/tenants/${id}`, payload),
  setSubscription: (
    id: string,
    moduleId: ModuleId,
    payload: TenantSubscriptionUpdatePayload,
  ) =>
    apiClient.put<TenantSubscriptionRead>(
      `/admin/tenants/${id}/subscriptions/${moduleId}`,
      payload,
    ),
}

// ───────────────────────────────────────────────────────────────────────────
// Admin · Users (Owner do tenant)
// Espelha backend/app/modules/admin/api/users.py
// ───────────────────────────────────────────────────────────────────────────

export type UserPermissionRead = {
  module: ModuleId
  permission: Permission
}

export type UserRead = {
  id: string
  tenant_id: string
  email: string
  name: string
  tenant_role: TenantRoleId
  ativo: boolean
  last_login_at: string | null
  email_verified_at: string | null
  invited_by_id: string | null
  created_at: string
  permissions: UserPermissionRead[]
}

export type UserUpdatePayload = {
  name?: string
  ativo?: boolean
  tenant_role?: TenantRoleId
}

export type UserPermissionUpdatePayload = {
  permission: Permission
}

export type InvitationCreatePayload = {
  email: string
  role: TenantRoleId
}

export const adminUsers = {
  list: () => apiClient.get<UserRead[]>("/admin/users"),
  get: (id: string) => apiClient.get<UserRead>(`/admin/users/${id}`),
  update: (id: string, payload: UserUpdatePayload) =>
    apiClient.patch<UserRead>(`/admin/users/${id}`, payload),
  setPermission: (
    id: string,
    moduleId: ModuleId,
    payload: UserPermissionUpdatePayload,
  ) =>
    apiClient.put<UserPermissionRead>(
      `/admin/users/${id}/permissions/${moduleId}`,
      payload,
    ),
  invitations: {
    list: () => apiClient.get<InvitationRead[]>("/admin/users/invitations"),
    create: (payload: InvitationCreatePayload) =>
      apiClient.post<InvitationCreateResponse>(
        "/admin/users/invitations",
        payload,
      ),
    cancel: (id: string) =>
      apiClient.delete<void>(`/admin/users/invitations/${id}`),
  },
}

// ───────────────────────────────────────────────────────────────────────────
// Invitations publicas (sem auth — surface de aceite)
// ───────────────────────────────────────────────────────────────────────────

export const invitations = {
  context: (token: string) =>
    apiClient.get<InvitationContext>(`/invitations/${encodeURIComponent(token)}`),
  accept: (token: string, payload: { name: string; password: string }) =>
    apiClient.post<LoginResponse>(
      `/invitations/${encodeURIComponent(token)}/accept`,
      payload,
    ),
}

export const adminAI = {
  providers: {
    list: () =>
      apiClient.get<AIProviderCredentialRead[]>("/admin/ai/providers"),
    create: (payload: AIProviderCredentialCreatePayload) =>
      apiClient.post<AIProviderCredentialRead>("/admin/ai/providers", payload),
    update: (id: string, payload: AIProviderCredentialUpdatePayload) =>
      apiClient.put<AIProviderCredentialRead>(
        `/admin/ai/providers/${id}`,
        payload,
      ),
    remove: (id: string) =>
      apiClient.delete<void>(`/admin/ai/providers/${id}`),
  },
  prompts: {
    list: (includeArchived = false) =>
      apiClient.get<AIPromptVersionInfo[]>(
        `/admin/ai/prompts${includeArchived ? "?include_archived=true" : ""}`,
      ),
    get: (id: string) =>
      apiClient.get<AIPromptDetail>(`/admin/ai/prompts/${id}`),
    create: (payload: AIPromptCreatePayload) =>
      apiClient.post<AIPromptDetail>("/admin/ai/prompts", payload),
    update: (id: string, payload: AIPromptUpdatePayload) =>
      apiClient.put<AIPromptDetail>(`/admin/ai/prompts/${id}`, payload),
    activate: (name: string, versionId: string) =>
      apiClient.put<AIPromptVersionInfo>(
        `/admin/ai/prompts/${encodeURIComponent(name)}/active`,
        { version_id: versionId },
      ),
    archive: (id: string) =>
      apiClient.post<AIPromptDetail>(`/admin/ai/prompts/${id}/archive`),
    preview: (id: string, context: Record<string, string>) =>
      apiClient.post<AIPromptPreview>(`/admin/ai/prompts/${id}/preview`, {
        context,
      }),
  },
  agents: {
    listModels: () =>
      apiClient.get<AIAgentModelOption[]>("/admin/ai/agents/models"),
    list: () => apiClient.get<AIAgentConfigRead[]>("/admin/ai/agents"),
    update: (agentName: string, payload: AIAgentConfigUpdatePayload) =>
      apiClient.put<AIAgentConfigRead>(
        `/admin/ai/agents/${encodeURIComponent(agentName)}`,
        payload,
      ),
  },
  // F2.c.1 — CRUD versionado de personas (CLAUDE.md §19.12).
  personas: {
    list: (includeArchived = false) =>
      apiClient.get<AIPersonaVersionInfo[]>(
        `/admin/ia/personas${includeArchived ? "?include_archived=true" : ""}`,
      ),
    get: (id: string) =>
      apiClient.get<AIPersonaDetail>(`/admin/ia/personas/${id}`),
    create: (payload: AIPersonaCreatePayload) =>
      apiClient.post<AIPersonaDetail>("/admin/ia/personas", payload),
    update: (id: string, payload: AIPersonaUpdatePayload) =>
      apiClient.put<AIPersonaDetail>(`/admin/ia/personas/${id}`, payload),
    activate: (name: string, versionId: string) =>
      apiClient.put<AIPersonaVersionInfo>(
        `/admin/ia/personas/${encodeURIComponent(name)}/active`,
        { version_id: versionId },
      ),
    archive: (id: string) =>
      apiClient.post<AIPersonaDetail>(`/admin/ia/personas/${id}/archive`),
  },
  // F2.c.4 — Listagem read-only de tools registradas (@register_tool).
  tools: {
    list: (opts: { module?: string; cost?: string } = {}) => {
      const params = new URLSearchParams()
      if (opts.module) params.set("module", opts.module)
      if (opts.cost) params.set("cost", opts.cost)
      const qs = params.toString()
      return apiClient.get<AIToolInfo[]>(
        `/admin/ia/tools${qs ? `?${qs}` : ""}`,
      )
    },
  },
  // F2.c.3 — CRUD versionado de agent definitions (CLAUDE.md §19.12).
  // Em /admin/ia/agents (portugues, novo) — paralelo ao legado em
  // /admin/ai/agents (ingles, agent_config override) que continua de pe.
  agentDefinitions: {
    list: (opts: { includeArchived?: boolean; module?: string } = {}) => {
      const params = new URLSearchParams()
      if (opts.includeArchived) params.set("include_archived", "true")
      if (opts.module) params.set("module", opts.module)
      const qs = params.toString()
      return apiClient.get<AIAgentDefinitionVersionInfo[]>(
        `/admin/ia/agents${qs ? `?${qs}` : ""}`,
      )
    },
    get: (id: string) =>
      apiClient.get<AIAgentDefinitionDetail>(`/admin/ia/agents/${id}`),
    create: (payload: AIAgentDefinitionCreatePayload) =>
      apiClient.post<AIAgentDefinitionDetail>("/admin/ia/agents", payload),
    update: (id: string, payload: AIAgentDefinitionUpdatePayload) =>
      apiClient.put<AIAgentDefinitionDetail>(
        `/admin/ia/agents/${id}`,
        payload,
      ),
    activate: (name: string, versionId: string) =>
      apiClient.put<AIAgentDefinitionVersionInfo>(
        `/admin/ia/agents/${encodeURIComponent(name)}/active`,
        { version_id: versionId },
      ),
    archive: (id: string) =>
      apiClient.post<AIAgentDefinitionDetail>(
        `/admin/ia/agents/${id}/archive`,
      ),
    preview: (id: string) =>
      apiClient.post<AIAgentDefinitionPreview>(
        `/admin/ia/agents/${id}/preview`,
      ),
  },
  // F2.c.2 — CRUD versionado de expertises (CLAUDE.md §19.12).
  expertises: {
    list: (opts: { includeArchived?: boolean; domain?: string } = {}) => {
      const params = new URLSearchParams()
      if (opts.includeArchived) params.set("include_archived", "true")
      if (opts.domain) params.set("domain", opts.domain)
      const qs = params.toString()
      return apiClient.get<AIExpertiseVersionInfo[]>(
        `/admin/ia/expertises${qs ? `?${qs}` : ""}`,
      )
    },
    get: (id: string) =>
      apiClient.get<AIExpertiseDetail>(`/admin/ia/expertises/${id}`),
    create: (payload: AIExpertiseCreatePayload) =>
      apiClient.post<AIExpertiseDetail>("/admin/ia/expertises", payload),
    update: (id: string, payload: AIExpertiseUpdatePayload) =>
      apiClient.put<AIExpertiseDetail>(`/admin/ia/expertises/${id}`, payload),
    activate: (name: string, versionId: string) =>
      apiClient.put<AIExpertiseVersionInfo>(
        `/admin/ia/expertises/${encodeURIComponent(name)}/active`,
        { version_id: versionId },
      ),
    archive: (id: string) =>
      apiClient.post<AIExpertiseDetail>(`/admin/ia/expertises/${id}/archive`),
  },
}

// ───────────────────────────────────────────────────────────────────────────
// Tipos do admin de expertises
// ───────────────────────────────────────────────────────────────────────────

export type AIExpertiseReference = {
  url: string
  label: string
  kind?: string
}

export type AIExpertiseVersionInfo = {
  id: string
  name: string
  version: number
  display_name: string
  domain: string
  is_active: boolean
  usage_count: number
  created_at: string
  archived_at: string | null
}

export type AIExpertiseDetail = {
  id: string
  name: string
  version: number
  display_name: string
  domain: string
  knowledge_text: string
  reference_urls: AIExpertiseReference[] | null
  is_active: boolean
  usage_count: number
  created_at: string
  archived_at: string | null
}

export type AIExpertiseCreatePayload = {
  name: string
  display_name: string
  domain: string
  knowledge_text: string
  reference_urls?: AIExpertiseReference[]
}

export type AIExpertiseUpdatePayload = Partial<
  Omit<AIExpertiseCreatePayload, "name">
>

// ───────────────────────────────────────────────────────────────────────────
// Tipos do admin de agent definitions (F2.c.3)
// ───────────────────────────────────────────────────────────────────────────

export type AIAgentPersonaRef = {
  id: string
  name: string
  display_name: string
  version: number
}

export type AIAgentExpertiseRef = {
  id: string
  name: string
  display_name: string
  domain: string
  version: number
}

export type AIAgentPromptRef = {
  id: string
  name: string
  version: string
}

export type AIAgentDefinitionVersionInfo = {
  id: string
  name: string
  version: number
  module: string
  persona_name: string | null
  expertise_count: number
  prompt_name: string
  model: string | null
  is_active: boolean
  cross_module: boolean
  tenant_id: string | null
  created_at: string
  archived_at: string | null
}

export type AIAgentDefinitionDetail = {
  id: string
  name: string
  version: number
  module: string
  persona: AIAgentPersonaRef | null
  expertises: AIAgentExpertiseRef[]
  prompt: AIAgentPromptRef | null
  prompt_name: string
  model: string | null
  fallback_model: string | null
  temperature: number | null
  max_tokens: number | null
  cross_module: boolean
  // null = usa default do CATALOG (spec.tools); [] = sem tools; [...] = override.
  allowed_tools: string[] | null
  credit_hint: number | null
  tenant_id: string | null
  is_active: boolean
  created_at: string
  archived_at: string | null
}

export type AIAgentDefinitionCreatePayload = {
  name: string
  module: string
  persona_id?: string | null
  expertise_ids?: string[] | null
  prompt_name: string
  model?: string | null
  fallback_model?: string | null
  temperature?: number | null
  max_tokens?: number | null
  cross_module?: boolean
  allowed_tools?: string[] | null
  credit_hint?: number | null
}

export type AIAgentDefinitionUpdatePayload = Partial<
  Omit<AIAgentDefinitionCreatePayload, "name" | "module">
>

export type AIToolInfo = {
  name: string
  description: string
  module: string
  min_permission: string
  cost_hint: string
  input_schema: Record<string, unknown>
}

export type AIAgentDefinitionPreview = {
  name: string
  version: number
  system_text: string
  persona_full_id: string | null
  expertise_full_ids: string[]
  prompt_full_id: string
  model: string
  fallback_model: string | null
  temperature: number | null
  max_tokens: number | null
}

// ───────────────────────────────────────────────────────────────────────────
// Tipos do admin de personas
// ───────────────────────────────────────────────────────────────────────────

export type AIPersonaVersionInfo = {
  id: string
  name: string
  version: number
  display_name: string
  is_active: boolean
  expertise_domains: string[] | null
  description: string | null
  usage_count: number
  created_at: string
  archived_at: string | null
}

export type AIPersonaDetail = {
  id: string
  name: string
  version: number
  display_name: string
  role_block: string
  description: string | null
  expertise_domains: string[] | null
  is_active: boolean
  usage_count: number
  created_at: string
  archived_at: string | null
}

export type AIPersonaCreatePayload = {
  name: string
  display_name: string
  role_block: string
  description?: string
  expertise_domains?: string[]
}

export type AIPersonaUpdatePayload = Partial<
  Omit<AIPersonaCreatePayload, "name">
>

// ───────────────────────────────────────────────────────────────────────────
// Tipos do admin de prompts
// ───────────────────────────────────────────────────────────────────────────

export type AIPromptVersionInfo = {
  id: string
  name: string
  version: string
  is_active: boolean
  model: string
  fallback_model: string | null
  temperature: number
  max_tokens: number
  description: string | null
  created_at: string
  archived_at: string | null
}

export type AIPromptDetail = {
  id: string
  name: string
  version: string
  is_active: boolean
  system_text: string
  user_context_template: string | null
  assistant_prime: string | null
  model: string
  fallback_model: string | null
  temperature: number
  max_tokens: number
  cache_strategy: "none" | "after_system"
  description: string | null
  created_at: string
  updated_at: string
  archived_at: string | null
}

export type AIPromptCreatePayload = {
  name: string
  system_text: string
  user_context_template?: string
  assistant_prime?: string
  model: string
  fallback_model?: string
  temperature?: number
  max_tokens?: number
  cache_strategy?: "none" | "after_system"
  description?: string
}

export type AIPromptUpdatePayload = Partial<Omit<AIPromptCreatePayload, "name">>

export type AIPromptPreview = {
  name: string
  version: string
  model: string
  temperature: number
  max_tokens: number
  messages: Array<{
    role: string
    content: Array<{ type: string; text: string; cache_control?: { type: string } | null }>
  }>
}

// ───────────────────────────────────────────────────────────────────────────
// Admin IA — model override por specialist agent (etapa 1: Anthropic only)
// Espelha endpoints em backend/app/modules/admin/api/ai_agents.py
// ───────────────────────────────────────────────────────────────────────────

export type AIAgentModelTier = "opus" | "sonnet" | "haiku"

export type AIAgentModelOption = {
  id: string
  label: string
  tier: AIAgentModelTier
  description: string
}

export type AIAgentConfigRead = {
  agent_name: string
  description: string
  prompt_name: string
  multimodal: boolean
  section_id: string
  default_model: string
  default_fallback_model: string | null
  model: string
  fallback_model: string | null
  source: "db_override" | "catalog_default"
  updated_at: string | null
  updated_by_user_id: string | null
}

export type AIAgentConfigUpdatePayload = {
  model: string
  fallback_model?: string | null
}

/**
 * Endpoint URL absoluto (precisa para o stream SSE via fetch).
 * Inclui o Bearer token no header.
 */
export function buildAIChatRequest(
  body: {
    message: string
    context: { page: string; period?: string | null; filters?: string | null }
    conversation_id?: string | null
  },
): { url: string; init: RequestInit } {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  return {
    url: `${API_URL}/ai/chat`,
    init: {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      cache: "no-store",
    },
  }
}

/**
 * Request SSE do agente de variacao da Cota Sub (run-stream). Mesma anatomy
 * do buildAIChatRequest: POST + Bearer token + Accept text/event-stream.
 * Sem body — params vao na query string (fundo_id, data). Consumido via
 * fetch + ReadableStream (NUNCA EventSource — nao passa Authorization).
 */
export function buildCotaSubAgenteVariacaoStreamRequest(
  fundoId: string,
  data: string,
): { url: string; init: RequestInit } {
  const headers: Record<string, string> = {
    Accept: "text/event-stream",
  }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  const params = new URLSearchParams({ fundo_id: fundoId, data })
  return {
    url: `${API_URL}/controladoria/cota-sub/agente/analista-variacao/run-stream?${params.toString()}`,
    init: {
      method: "POST",
      headers,
      cache: "no-store",
    },
  }
}

//
// Helpers de alto nivel
//

export async function login(
  email: string,
  password: string,
  tenantSlug?: string,
): Promise<LoginResponse> {
  const res = await apiClient.post<LoginResponse>("/auth/login", {
    email,
    password,
    ...(tenantSlug ? { tenant_slug: tenantSlug } : {}),
  })
  setToken(res.access_token)
  return res
}

// Quando o backend devolve 409 no /auth/login, o email tem match em N tenants
// e precisamos pedir ao usuario que escolha um slug. detail vira:
// { message: string, tenant_slugs: string[] }.
export type LoginAmbiguousTenant = {
  message: string
  tenant_slugs: string[]
}

export async function fetchMe(): Promise<MeResponse> {
  return apiClient.get<MeResponse>("/auth/me")
}

export function logout(): void {
  clearToken()
}

//
// Tipos BI (modulo /bi/*)
//

export type BIFilters = {
  periodoInicio?: string // YYYY-MM-DD
  periodoFim?: string
  /** Siglas de produto — multi-select (WHERE IN no backend). */
  produtoSigla?: string[]
  /** IDs de UA — multi-select (WHERE IN no backend). */
  uaId?: number[]
  cedenteId?: number
  sacadoId?: number
  gerenteDocumento?: string
}

export type Provenance = {
  source_type: string
  source_ids: string[]
  /** Ultima sync bem-sucedida do pipeline — global, independe dos filtros. */
  last_sync_at: string | null
  /** Maior source_updated_at dentro do set filtrado. */
  last_source_updated_at: string | null
  trust_level: "high" | "medium" | "low"
  ingested_by_version: string
  row_count: number
}

export type SyncHealthStatus =
  | "ok"
  | "delayed"
  | "stale"
  | "on_demand"
  | "disabled"

export type SyncHealthEntry = {
  source_type: string
  label: string
  enabled: boolean
  /** null = sob demanda. */
  sync_frequency_minutes: number | null
  /** ISO8601. Ultimo sync com `explanation='OK'`. */
  last_sync_at: string | null
  /** ISO8601. Ultima tentativa de sync — independe do resultado. */
  last_attempt_at: string | null
  /** ISO8601. Quando o dispatcher deve disparar o proximo ciclo. */
  expected_next_at: string | null
  status: SyncHealthStatus
  unidade_administrativa_id: string | null
}
export type SyncHealth = SyncHealthEntry[]

export type SyncHealthFailingEndpoint = {
  source_type: string
  source_label: string
  endpoint_name: string
  endpoint_label: string
  last_sync_started_at: string | null
  last_sync_finished_at: string | null
  last_sync_error: string | null
}

export type SyncHealthSummary = {
  failing_count: number
  failing: SyncHealthFailingEndpoint[]
}

export type BIResponse<T> = {
  data: T
  provenance: Provenance
}

export type KPI = {
  label: string
  valor: number
  unidade: "BRL" | "%" | "un" | "dias"
  detalhe: string | null
}

export type Point = { periodo: string; valor: number }
export type CategoryValue = {
  categoria: string
  valor: number
  quantidade: number | null
}

function filtersToQueryString(f: BIFilters): string {
  const p = new URLSearchParams()
  if (f.periodoInicio) p.set("periodo_inicio", f.periodoInicio)
  if (f.periodoFim) p.set("periodo_fim", f.periodoFim)
  // Multi: repetir o param por valor (FastAPI junta em list).
  if (f.produtoSigla && f.produtoSigla.length > 0) {
    for (const v of f.produtoSigla) p.append("produto_sigla", v)
  }
  if (f.uaId && f.uaId.length > 0) {
    for (const v of f.uaId) p.append("ua_id", String(v))
  }
  if (f.cedenteId !== undefined) p.set("cedente_id", String(f.cedenteId))
  if (f.sacadoId !== undefined) p.set("sacado_id", String(f.sacadoId))
  if (f.gerenteDocumento) p.set("gerente_documento", f.gerenteDocumento)
  const s = p.toString()
  return s ? `?${s}` : ""
}

// ───────────────────────────────────────────────────────────────────────────
// BI · Operacoes2 (refatoracao 2026-05-03 — KPI Strip + 4 abas)
// ───────────────────────────────────────────────────────────────────────────

export type Operacoes2KpiCellNumeric = {
  valor: number
  unidade: "BRL" | "%" | "dias"
  // delta_pct: periodo vs periodo anterior de mesmo tamanho (P/P).
  delta_pct: number | null
  sparkline_12m: Point[]
  // Strip dual (Opcao 4 paradigma 2026-05-03)
  mes_corrente_valor: number
  mes_corrente_label: string
  // mes_corrente_delta_pct: MoM literal (mes corrente vs mes anterior).
  mes_corrente_delta_pct: number | null
}

export type Operacoes2KpiCellProduto = {
  sigla: string
  nome: string | null
  share_pct: number
  delta_share_pp: number | null
  sparkline_share_12m: Point[]
  // Mes corrente (pode ser produto diferente do top do periodo)
  mes_corrente_sigla: string
  mes_corrente_nome: string | null
  mes_corrente_share_pct: number
  mes_corrente_label: string
  // mes_corrente_delta_share_pp: MoM literal — pp do produto-top-do-mes
  // entre mes corrente e mes anterior.
  mes_corrente_delta_share_pp: number | null
}

export type Operacoes2KpiStripData = {
  vop: Operacoes2KpiCellNumeric
  taxa_media: Operacoes2KpiCellNumeric
  prazo_medio: Operacoes2KpiCellNumeric
  produto_top: Operacoes2KpiCellProduto
  receita_contratada: Operacoes2KpiCellNumeric
  comparacao_label_pt: string
}

export type Operacoes2EvolucaoMensalPonto = {
  periodo: string
  vop: number
  n_operacoes: number
  ticket_medio: number
  mm_3m: number | null
}

export type Operacoes2MesDestaque = { periodo: string; vop: number }

export type Operacoes2AcumuladoDiarioPonto = {
  du_index: number
  corrente: number
  anterior: number
}

export type Operacoes2RitmoUaItem = {
  ua_id: number
  ua_nome: string
  vop_corrente: number
  delta_pct: number | null
}

export type Operacoes2RitmoMesCorrente = {
  vop_acumulado: number
  du_corridos: number
  du_total_mes: number
  vop_anterior_mesmo_du: number
  delta_pct: number | null
  projecao_fim_mes: number
  acumulado_dia_a_dia: Operacoes2AcumuladoDiarioPonto[]
  // Quebra textual por UA — VOP MTD da UA + delta MoM same-period DU.
  // Renderizado como lista no rodape do card Hero do Ritmo.
  ritmo_por_ua: Operacoes2RitmoUaItem[]
}

export type Operacoes2PaceDiario = {
  vop_du_corrente: number
  vop_du_anterior: number
  delta_pct: number | null
}

export type Operacoes2KpiSecundario = {
  valor: number
  delta_pct: number | null
  // Sparkline 12M fechados (M-12 a M-1) do indicador. Usado pela tabela
  // condensada de indicadores secundarios. Slope deve ser interpretado
  // em modo relativo (% sobre a media da serie) — escalas variam por KPI
  // (count, BRL, BRL/titulo, BRL/DU).
  sparkline_12m: Point[]
}

export type Operacoes2KpisSecundariosVolume = {
  n_operacoes: Operacoes2KpiSecundario
  ticket_op: Operacoes2KpiSecundario
  ticket_titulo: Operacoes2KpiSecundario
  vop_du_medio: Operacoes2KpiSecundario | null
}

export type Operacoes2QuebraDimensaoLinha = {
  categoria_id: string
  categoria: string
  vop: number
  pct: number
  delta_mom_pct: number | null
  delta_yoy_pct: number | null
  // Mes corrente (Opcao 4)
  vop_mes_corrente: number
  pct_mes_corrente: number
  // Sparkline 12M de share% (Point.valor em escala 0-100). Usado pela tabela
  // trend em modo "share" — detecta drift de mix entre categorias.
  sparkline_share_12m: Point[]
  // Sparkline 12M de VOP absoluto da categoria (Point.valor em BRL). Usado
  // pela tabela trend em modo "absolute" — leitura "categoria vs ela mesma
  // no passado", apropriada quando dimensoes tem trajetoria propria de
  // crescimento (ex.: UA, onde share% conduz a falso negativo).
  sparkline_vop_12m: Point[]
}

export type Operacoes2EvolucaoPorUaPonto = {
  periodo: string
  ua_id: number
  ua_nome: string
  vop: number
}

export type Operacoes2AbaVolumeRitmoData = {
  evolucao_12m: Operacoes2EvolucaoMensalPonto[]
  evolucao_12m_por_ua: Operacoes2EvolucaoPorUaPonto[]
  melhor_mes: Operacoes2MesDestaque | null
  pior_mes: Operacoes2MesDestaque | null
  ritmo: Operacoes2RitmoMesCorrente | null
  pace_diario: Operacoes2PaceDiario | null
  kpis_secundarios: Operacoes2KpisSecundariosVolume
  por_ua: Operacoes2QuebraDimensaoLinha[]
  por_produto: Operacoes2QuebraDimensaoLinha[]
}

// ─── Aba 2: Produtos & Pricing ──────────────────────────────────────────────

export type Operacoes2MixTemporalProdutoPonto = {
  periodo: string
  produto_sigla: string
  vop: number
  n_operacoes: number
  taxa_media: number
  prazo_medio: number
}

export type Operacoes2RankingProdutoLinha = {
  sigla: string
  nome: string | null
  vop: number
  pct: number
  delta_mom_pp: number | null
  taxa_media: number
  prazo_medio: number
  spread_medio: number
  n_operacoes: number
  vop_mes_corrente: number
  taxa_media_mes_corrente: number
}

export type Operacoes2ScatterProdutoPonto = {
  sigla: string
  nome: string | null
  prazo_medio: number
  taxa_media: number
  vop: number
  prazo_medio_mes_corrente: number
  taxa_media_mes_corrente: number
  vop_mes_corrente: number
}

export type Operacoes2HistogramaProdutoBucket = {
  produto_sigla: string
  bucket_label: string
  bucket_lower: number
  bucket_upper: number
  count: number
  vop: number
}

export type Operacoes2HistogramaTaxasResumo = {
  buckets: Operacoes2HistogramaProdutoBucket[]
  media_ponderada: number
  mediana: number
  bucket_size_pp: number
}

export type Operacoes2HistogramaPrazosResumo = {
  buckets: Operacoes2HistogramaProdutoBucket[]
}

export type Operacoes2ProdutoDestaque = {
  sigla: string
  nome: string | null
  valor: number
}

export type Operacoes2AbaProdutosPricingData = {
  mix_temporal_12m: Operacoes2MixTemporalProdutoPonto[]
  lider_periodo: Operacoes2ProdutoDestaque | null
  maior_alta_mom: Operacoes2ProdutoDestaque | null
  maior_queda_mom: Operacoes2ProdutoDestaque | null
  ranking: Operacoes2RankingProdutoLinha[]
  scatter_produtos: Operacoes2ScatterProdutoPonto[]
  histograma_taxas: Operacoes2HistogramaTaxasResumo
  histograma_prazos: Operacoes2HistogramaPrazosResumo
}

// ── Aba 0: Mes corrente (variance decomposition) ────────────────────────────

export type Operacoes2Dimension = "produto" | "ua" | "faixa_ticket"

export type Operacoes2DriverContribution = {
  member_id: string
  member_label: string
  /** Aditiva pra variance (BRL); na unidade do KPI pra PVM (pp em Taxa, dias em Prazo). */
  contribution_brl: number
  /** Pct do |delta total|. Null quando delta total = 0. */
  contribution_pct: number | null
  prior_value: number
  current_value: number
}

export type Operacoes2VarianceBridgeData = {
  prior_anchor_label: string
  prior_anchor_value: number
  current_anchor_label: string
  current_anchor_value: number
  delta_brl: number
  delta_pct: number | null
  drivers: Operacoes2DriverContribution[]
  outros_rollup: Operacoes2DriverContribution | null
  unidade: "BRL"
}

export type Operacoes2ProjectionBridgeData = {
  current_anchor_label: string
  current_anchor_value: number
  projected_close_label: string
  projected_close_value: number
  delta_brl: number
  delta_pct: number | null
  drivers: Operacoes2DriverContribution[]
  outros_rollup: Operacoes2DriverContribution | null
  unidade: "BRL"
}

export type Operacoes2PvmBridgeData = {
  prior_anchor_label: string
  prior_anchor_value: number
  current_anchor_label: string
  current_anchor_value: number
  /** current - prior (na unidade do KPI). */
  delta: number
  delta_unidade: "pp" | "dias"
  mix_effect: number
  intra_effect: number
  top_mix_contributors: Operacoes2DriverContribution[]
  top_intra_contributors: Operacoes2DriverContribution[]
  outros_mix_rollup: Operacoes2DriverContribution | null
  outros_intra_rollup: Operacoes2DriverContribution | null
}

export type Operacoes2DumbbellPoint = {
  member_id: string
  member_label: string
  /** Escala 0-100. */
  prior_share_pct: number
  current_share_pct: number
  /** current_share_pct - prior_share_pct, em pontos percentuais. */
  delta_share_pp: number
  prior_value: number
  current_value: number
}

export type Operacoes2DumbbellSeriesData = {
  prior_anchor_label: string
  current_anchor_label: string
  /** Top N por |delta_share_pp|, sem categorias com share < 1%% em ambos. */
  points: Operacoes2DumbbellPoint[]
}

export type Operacoes2ConcentracaoMovement = {
  member_id: string
  member_label: string
  prior_share_pct: number
  current_share_pct: number
  delta_share_pp: number
}

export type Operacoes2ConcentracaoDeltaData = {
  dimension_label: string
  prior_anchor_label: string
  current_anchor_label: string
  /** HHI normalizado em [0, 10000]. */
  hhi_prior: number
  hhi_current: number
  delta_hhi: number
  /** Share % dos top 3 do periodo. */
  top_3_share_prior: number
  top_3_share_current: number
  delta_top_3_pp: number
  movements_gainers: Operacoes2ConcentracaoMovement[]
  movements_losers: Operacoes2ConcentracaoMovement[]
}

/**
 * VOP por dia-calendario do mes corrente. Cobre todos os dias (incluindo
 * sab/dom/feriado). Dias futuros vem com `vop=null` (placeholder no eixo X
 * sem barra), `eh_futuro=true`. `eh_dia_util` permite UI dimming/destaque
 * de fim de semana e feriado.
 */
export type Operacoes2VopDiarioPonto = {
  /** Data ISO "YYYY-MM-DD". */
  data: string
  /** VOP do dia em BRL. null para dias futuros. */
  vop: number | null
  eh_dia_util: boolean
  eh_futuro: boolean
  /** Receita do dia (regime caixa, 4 buckets). Opt-in via operacoes4. */
  receita?: number | null
  /** receita/vop em % a.m. Opt-in via operacoes4. */
  yield_pct?: number | null
}

/**
 * VOP por (dia, UA) do mes corrente — alimenta filtro de UA do hero L2.
 */
export type Operacoes2VopDiarioPorUaPonto = {
  data: string
  ua_id: number
  ua_nome: string
  vop: number | null
  eh_dia_util: boolean
  eh_futuro: boolean
}

/**
 * Agregado MTD do VOP por UA — alimenta header KPI quando uma UA
 * especifica e selecionada no card VOP Diario.
 */
export type Operacoes2VopMtdPorUa = {
  ua_id: number
  ua_nome: string
  valor_mtd: number
  /** Δ VOP-DU (paridade DU vs mes anterior). Null = sem base. */
  delta_vop_du_pct: number | null
}

export type Operacoes2AbaMesCorrenteData = {
  /** Frase pt-BR multi-KPI gerada server-side (template deterministico). */
  narrative_sentence: string
  comparacao_label_pt: string
  du_decorridos: number
  du_totais_mes: number
  /** False quando wh_dim_dia_util esta vazia (degraded para dia corrido). */
  du_disponivel: boolean
  vop: Operacoes2VarianceBridgeData
  /** Null em degraded mode (du_disponivel=false ou du_decorridos=du_totais). */
  vop_projecao: Operacoes2ProjectionBridgeData | null
  receita: Operacoes2VarianceBridgeData
  receita_projecao: Operacoes2ProjectionBridgeData | null
  taxa: Operacoes2PvmBridgeData
  prazo: Operacoes2PvmBridgeData
  mix: Operacoes2DumbbellSeriesData
  concentracao: Operacoes2ConcentracaoDeltaData
  /** Serie diaria de VOP do mes corrente (alimenta o card "VOP Diario"). */
  vop_diario: Operacoes2VopDiarioPonto[]
  dimension_active: Operacoes2Dimension
  dimensions_disponiveis: Operacoes2Dimension[]
}

/** Decomposicao por UA do VOP Potencial (FIDC + Securitizadora por default). */
export type Operacoes2VopPotencialPorUa = {
  ua_id: number
  ua_nome: string
  /** Bitfin.UnidadeAdministrativa.Tipo: 1=FIDC, 2=Securitizadora, null=Outras. */
  ua_tipo: number | null
  vop_realizado_mtd: number
  caixa_disponivel: number
  liquidacoes_previstas: number
  vop_potencial: number
}

/**
 * VOP Potencial — quanto o fundo "ainda pode" gerar ate o fim do mes.
 *
 * `vop_potencial = vop_realizado_mtd + caixa_disponivel + liquidacoes_previstas`
 *
 * Janela: mes corrente. `vop_realizado_mtd` cobre [mes_inicio, hoje];
 * `liquidacoes_previstas` cobre (hoje, mes_fim]; `caixa_disponivel` e
 * snapshot em hoje. Default: UAs com `tipo IN (1, 2)`.
 */
export type Operacoes2VopPotencialData = {
  mes_inicio: string
  mes_fim: string
  hoje: string
  vop_realizado_mtd: number
  caixa_disponivel: number
  liquidacoes_previstas: number
  vop_potencial: number
  por_ua: Operacoes2VopPotencialPorUa[]
}

// ── Mes Corrente v3 — pagina /bi/operacoes3 ─────────────────────────────────

/**
 * Cell do termometro v3: valor + 2 deltas (VOP-DU paridade DU e MOM
 * normalizado por DU). Pra Taxa/Prazo, MOM e comparacao direta media-vs-media.
 */
export type Operacoes2MesCorrenteKpiCell = {
  valor: number
  /** MTD corrente vs MTD mes anterior nos mesmos N DUs (paridade). */
  delta_vop_du_pct: number | null
  /** Pace/DU corrente vs pace/DU mes anterior fechado (Taxa/Prazo: direto). */
  delta_mom_pct: number | null
  /** "BRL" | "%" | "dias" — frontend formata adequadamente. */
  unidade: string
  /** Ex.: "mai/26". */
  mes_label: string
}

/** Cell Potencial — absoluto, sem delta. */
export type Operacoes2MesCorrentePotencialCell = {
  valor: number
  realizado: number
  caixa: number
  a_liquidar: number
  mes_label: string
}

export type Operacoes2MesCorrenteTermometro = {
  vop: Operacoes2MesCorrenteKpiCell
  receita: Operacoes2MesCorrenteKpiCell
  taxa: Operacoes2MesCorrenteKpiCell
  prazo: Operacoes2MesCorrenteKpiCell
  potencial: Operacoes2MesCorrentePotencialCell
}

/**
 * Bundle da /bi/operacoes3 — termometro + hero (VOP Diario + Waterfall) +
 * decomposicao avancada (collapsible no frontend).
 */
export type Operacoes2AbaMesCorrenteV3Data = {
  termometro: Operacoes2MesCorrenteTermometro
  comparacao_label_pt: string
  du_decorridos: number
  du_totais_mes: number
  du_disponivel: boolean
  vop_diario: Operacoes2VopDiarioPonto[]
  vop_diario_por_ua: Operacoes2VopDiarioPorUaPonto[]
  vop_mtd_por_ua: Operacoes2VopMtdPorUa[]
  vop: Operacoes2VarianceBridgeData
  vop_projecao: Operacoes2ProjectionBridgeData | null
  receita: Operacoes2VarianceBridgeData
  receita_projecao: Operacoes2ProjectionBridgeData | null
  taxa: Operacoes2PvmBridgeData
  prazo: Operacoes2PvmBridgeData
  mix: Operacoes2DumbbellSeriesData
  concentracao: Operacoes2ConcentracaoDeltaData
}

/** Operacao individual exibida no DrillDownSheet do dia. */
export type Operacoes2OperacaoDoDiaItem = {
  operacao_id: string
  data_de_efetivacao: string
  cedente: string | null
  produto_sigla: string | null
  produto_nome: string | null
  ua_id: number | null
  ua_nome: string | null
  valor_bruto: number
  taxa: number | null
  prazo_medio: number | null
}

export type Operacoes2QuebraDiaPorDimensao = {
  label: string
  valor: number
  share_pct: number
}

/**
 * Linha da tabela narrativa de cedentes MTD.
 *
 * Status:
 *   - "novo":       cedente sem operacoes anteriores ao MTD
 *   - "sumido":     teve op no mes anterior mas zero no MTD (volume_mtd=null)
 *   - "recorrente": teve op antes do MTD E no MTD
 */
export type Operacoes2CedenteMtdItem = {
  cedente_nome: string
  cedente_id: number | null
  volume_mtd: number | null
  delta_vs_mes_ant_pct: number | null
  status: "novo" | "recorrente" | "sumido"
  n_op: number | null
  dias_mtd: number | null
  taxa_media: number | null
  primeira_op: string | null
  ultima_op: string | null
  /** Receita alocada ao cedente (regime caixa). Opt-in via operacoes4. */
  receita_total?: number | null
  /** receita_total / volume_mtd em % a.m. Opt-in via operacoes4. */
  yield_pct?: number | null
}

export type Operacoes2CedentesMtdData = {
  cedentes: Operacoes2CedenteMtdItem[]
  total: number
  mes_label: string
}

/** Drill 'operacoes do dia X' — conteudo do DrillDownSheet. */
export type Operacoes2OperacoesDoDiaData = {
  data: string
  vop_do_dia: number
  n_operacoes: number
  ticket_medio: number
  taxa_media: number | null
  prazo_medio: number | null
  operacoes: Operacoes2OperacaoDoDiaItem[]
  por_produto: Operacoes2QuebraDiaPorDimensao[]
  por_ua: Operacoes2QuebraDiaPorDimensao[]
}

export const biOperacoes2 = {
  kpiStrip: (f: BIFilters) =>
    apiClient.get<BIResponse<Operacoes2KpiStripData>>(
      `/bi/operacoes2/kpi-strip${filtersToQueryString(f)}`,
    ),
  abaVolumeRitmo: (f: BIFilters) =>
    apiClient.get<BIResponse<Operacoes2AbaVolumeRitmoData>>(
      `/bi/operacoes2/aba1-volume-ritmo${filtersToQueryString(f)}`,
    ),
  abaProdutosPricing: (f: BIFilters) =>
    apiClient.get<BIResponse<Operacoes2AbaProdutosPricingData>>(
      `/bi/operacoes2/aba2-produtos-pricing${filtersToQueryString(f)}`,
    ),
  abaMesCorrente: (
    f: BIFilters,
    dimension: Operacoes2Dimension = "produto",
  ) => {
    const baseQs = filtersToQueryString(f)
    const sep = baseQs ? "&" : "?"
    return apiClient.get<BIResponse<Operacoes2AbaMesCorrenteData>>(
      `/bi/operacoes2/aba1-mes-corrente${baseQs}${sep}dimension=${dimension}`,
    )
  },
  vopPotencial: (f: BIFilters) =>
    apiClient.get<BIResponse<Operacoes2VopPotencialData>>(
      `/bi/operacoes2/vop-potencial${filtersToQueryString(f)}`,
    ),
  abaMesCorrenteV3: (
    f: BIFilters,
    dimension: Operacoes2Dimension = "produto",
  ) => {
    const baseQs = filtersToQueryString(f)
    const sep = baseQs ? "&" : "?"
    return apiClient.get<BIResponse<Operacoes2AbaMesCorrenteV3Data>>(
      `/bi/operacoes2/aba3-mes-corrente${baseQs}${sep}dimension=${dimension}`,
    )
  },
  operacoesDoDia: (f: BIFilters, data: string) => {
    const baseQs = filtersToQueryString(f)
    const sep = baseQs ? "&" : "?"
    return apiClient.get<BIResponse<Operacoes2OperacoesDoDiaData>>(
      `/bi/operacoes2/operacoes-do-dia${baseQs}${sep}data=${data}`,
    )
  },
  cedentesMtd: (f: BIFilters) =>
    apiClient.get<BIResponse<Operacoes2CedentesMtdData>>(
      `/bi/operacoes2/cedentes-mtd${filtersToQueryString(f)}`,
    ),
}

// ── Operacoes4 (Mes Corrente · controladoria) — pagina /bi/operacoes4 ────────
//
// Lente alternativa de operacoes3 em REGIME CAIXA (wh_operacao). Responde
// perguntas que chegam da equipe de controladoria sobre o mes em curso.
// Espelho do backend `app/modules/bi/api/operacoes4.py`. Detalhes em
// CLAUDE.md banner operacoes4 + handoff SPEC.

export type Operacoes4ReceitaTipo =
  | "desagio"
  | "tarifa_cessao"
  | "tarifas_operacionais"
  | "outras"

export type Operacoes4ReceitaComposicaoItem = {
  tipo: Operacoes4ReceitaTipo
  /** Valor MTD do bucket em BRL (Decimal serializado como string ou number). */
  valor: string | number
  share_pct: number
  delta_pct: number | null
  flag_atypical: boolean
}

export type Operacoes4YieldPonto = {
  du: number
  yield_pct: number
  yield_parity_pct: number | null
  today: boolean
}

export type Operacoes4Mover = {
  tipo: Operacoes4ReceitaTipo
  delta_pct: number
  valor: string | number
}

export type Operacoes4Movers = {
  cresceu: Operacoes4Mover | null
  caiu: Operacoes4Mover | null
}

export type Operacoes4LensReceitasData = {
  total_mtd: string | number
  total_parity: string | number
  delta_pct: number | null
  composicao: Operacoes4ReceitaComposicaoItem[]
  yield_du: Operacoes4YieldPonto[]
  yield_wavg: number
  yield_delta_pp: number | null
  yield_parity_wavg: number
  movers: Operacoes4Movers
  mes_label: string
  du_decorridos: number
  du_totais_mes: number
  du_disponivel: boolean
}

export type Operacoes4DiariaPonto = {
  du: number
  data: string
  vop: number
  receita: number
  yield_pct: number | null
  today: boolean
  delta_par_pct: number | null
  outlier: boolean
}

export type Operacoes4DiariaData = {
  pontos: Operacoes4DiariaPonto[]
  mes_label: string
  mes_inicio: string
  mes_fim: string
  du_decorridos: number
  du_totais_mes: number
  du_disponivel: boolean
}

export const biOperacoes4 = {
  lensReceitas: (f: BIFilters) =>
    apiClient.get<BIResponse<Operacoes4LensReceitasData>>(
      `/bi/operacoes4/lens-receitas${filtersToQueryString(f)}`,
    ),
  diaria: (f: BIFilters) =>
    apiClient.get<BIResponse<Operacoes4DiariaData>>(
      `/bi/operacoes4/diaria${filtersToQueryString(f)}`,
    ),
}

//
// Benchmark (L2 dentro de BI) — CVM FIDC via postgres_fdw.
// Detalhes em docs/integracao-cvm-fidc.md. CLAUDE.md §13.1.
//

export type BenchmarkResumo = {
  /** Competencia YYYY-MM exibida no header; null quando ponte FDW sem dados. */
  competencia: string | null
  total_fundos: KPI
  pl_total: KPI
  pdd_mediana: KPI
  inadimplencia_mediana: KPI
  cobertura_mediana: KPI
}

export type PDDDistribuicao = {
  /** Histograma em buckets (<1%, 1-2%, ..., 20%+). */
  histograma: CategoryValue[]
  /** Top fundos por %PDD. */
  top_fundos: CategoryValue[]
}

export type BenchmarkEvolucao = {
  pl_mediano: Point[]
  pl_total: Point[]
  num_fundos: Point[]
}

export type AdminLinha = {
  cnpj_admin: string | null
  admin: string
  quantidade_fundos: number
  pl_total: number
}

export type BenchmarkAdmins = {
  /** 'YYYY-MM' — snapshot na competencia-fim do range. */
  competencia: string
  top_por_quantidade: AdminLinha[]
  top_por_pl: AdminLinha[]
  total_admins: number
}

export type CondomPonto = {
  /** 'YYYY-MM-DD' (primeiro dia do mes). */
  periodo: string
  aberto_qtd: number
  fechado_qtd: number
  aberto_pct: number
  fechado_pct: number
}

export type BenchmarkCondom = {
  /** 'YYYY-MM' — snapshot na competencia-fim do range. */
  competencia: string
  aberto_qtd: number
  fechado_qtd: number
  aberto_pct: number
  fechado_pct: number
  evolucao: CondomPonto[]
}

export type FundoRow = {
  cnpj_fundo: string
  denominacao_social: string | null
  classe_anbima: string | null
  situacao: string | null
  patrimonio_liquido: number
  numero_cotistas: number | null
  valor_total_dc: number | null
  percentual_pdd: number | null
  indice_inadimplencia: number | null
}

export type FundosLista = {
  competencia: string
  fundos: FundoRow[]
  total: number
}

export type BenchmarkFilters = {
  /** 'YYYY-MM' — quando omitido, backend usa ultima competencia disponivel. */
  competencia?: string
  /** Quantidade de competencias mais recentes (L3 Evolucao — legado). */
  meses?: number
  /** Busca por nome ou CNPJ (ILIKE parcial) — usado na L3 Fundos. */
  busca?: string
}

/**
 * Filtros para endpoints com range mensal (evolucao, admins, condom).
 * Ausencia de `periodoInicio`/`periodoFim` = backend decide (ultimos 12m).
 */
export type BenchmarkRangeFilters = {
  /** 'YYYY-MM' — inicio do range. */
  periodoInicio?: string
  /** 'YYYY-MM' — fim do range. */
  periodoFim?: string
  /** Valores de `tab_i.tp_fundo_classe` — ex.: ['Fundo'], ['Classe']. */
  tipoFundo?: string[]
  /** Default false — quando true, inclui `fundo_exclusivo='S'`. */
  incluirExclusivos?: boolean
}

function benchmarkQS(f: BenchmarkFilters): string {
  const p = new URLSearchParams()
  if (f.competencia) p.set("competencia", f.competencia)
  if (f.meses !== undefined) p.set("meses", String(f.meses))
  if (f.busca && f.busca.trim()) p.set("busca", f.busca.trim())
  const s = p.toString()
  return s ? `?${s}` : ""
}

function benchmarkRangeQS(f: BenchmarkRangeFilters): string {
  const p = new URLSearchParams()
  if (f.periodoInicio) p.set("periodo_inicio", f.periodoInicio)
  if (f.periodoFim) p.set("periodo_fim", f.periodoFim)
  if (f.tipoFundo && f.tipoFundo.length > 0) {
    for (const t of f.tipoFundo) p.append("tipo_fundo", t)
  }
  if (f.incluirExclusivos) p.set("incluir_exclusivos", "true")
  const s = p.toString()
  return s ? `?${s}` : ""
}

// L3 Comparativo — confronta 2..5 fundos na competencia + series + composicao.
// Payload espelha `ComparativoResponse` em app/modules/bi/schemas/benchmark_comparativo.py.

export type FundoHeader = {
  /** CNPJ digits-only (14 chars). */
  cnpj: string
  denom_social: string | null
  classe_anbima: string | null
  /** Slot 0..4 na paleta A7 (slate/sky/teal/emerald/amber). */
  cor_index: number
}

export type RankingValor = {
  cnpj: string
  valor: number | null
}

export type RankingLinha = {
  /** Chave estavel do indicador (ex.: 'pl', 'pct_inad_total'). */
  key: string
  label: string
  /** 'BRL' | '%' | 'un' | 'dias'. */
  unidade: string
  /** 'asc' = menor e melhor, 'desc' = maior e melhor. */
  direction: "asc" | "desc"
  mediana_mercado: number | null
  valores: RankingValor[]
}

export type PontoSerieValor = {
  cnpj: string
  valor: number | null
}

export type PontoSerie = {
  /** 'YYYY-MM'. */
  competencia: string
  mediana: number | null
  valores: PontoSerieValor[]
}

export type ComposicaoFatia = {
  categoria: string
  valor: number
  percentual: number | null
}

export type ComposicaoFundo = {
  cnpj: string
  ativo_total: number | null
  ativo: ComposicaoFatia[]
  setores_top: ComposicaoFatia[]
  scr_devedor: ComposicaoFatia[]
}

export type ComparativoResponse = {
  /** 'YYYY-MM' da competencia de referencia. */
  competencia: string
  fundos: FundoHeader[]
  ranking: RankingLinha[]
  /** indicador_key -> lista de pontos mensais (N meses). */
  series: Record<string, PontoSerie[]>
  composicoes: ComposicaoFundo[]
}

export type ComparativoArgs = {
  /** 2..5 CNPJs digits-only. */
  cnpjs: string[]
  /** 'YYYY-MM'; quando omitido, backend usa a ultima competencia. */
  competencia?: string
  /** Meses das series evolutivas (3..120). Default: 24. */
  meses?: number
}

function comparativoQS(a: ComparativoArgs): string {
  const p = new URLSearchParams()
  for (const c of a.cnpjs) p.append("cnpjs", c)
  if (a.competencia) p.set("competencia", a.competencia)
  if (a.meses !== undefined) p.set("meses", String(a.meses))
  return `?${p.toString()}`
}

// L3 Ficha do fundo — snapshot + series ~24m por CNPJ.
// Payload espelha `FichaFundo` em app/modules/bi/schemas/fundo.py.

export type FundoIdentificacao = {
  cnpj: string
  denom_social: string | null
  tp_fundo_classe: string | null
  condom: string | null
  classe: string | null
  admin: string | null
  cnpj_admin: string | null
  prazo_conversao_cota: number | null
  prazo_pagto_resgate: number | null
  competencia_atual: string
  competencia_primeira: string
}

export type FundoPLPonto = {
  competencia: string
  pl: number
  pl_medio: number | null
}

// Ativo (Tabela I) do Informe Mensal FIDC CVM.
// Hierarquia: (I) Ativo = (I.1) Disp + (I.2) Carteira + (I.3) Deriv + (I.4) Outros.
export type FundoCarteiraPonto = {
  competencia: string
  disp: number              // (I.1)
  dc_risco: number          // (I.2.a) DC com aquisicao substancial de riscos
  dc_sem_risco: number      // (I.2.b) DC sem aquisicao substancial de riscos
  vlmob: number             // (I.2.c) Valores mobiliarios (subtotal)
  tit_pub: number           // (I.2.d)
  cdb: number               // (I.2.e)
  oper_comprom: number      // (I.2.f)
  outros_rf: number         // (I.2.g)
  cotas_fidc: number        // (I.2.h)
  cotas_fidc_np: number     // (I.2.i)
  contrato_futuro: number   // (I.2.j) Warrants/futuros
  carteira_sub: number      // (I.2)  Subtotal Carteira
  deriv: number             // (I.3)
  outro_ativo: number       // (I.4) — mapeia "Imoveis" no layout Austin
  pdd_aprox: number         // (I.2.a.11) redutor ja contido em dc_risco
  ativo_total: number       // (I)
  // Decomposicao do DC (tab_v) - usado pelo layout Lamina Austin que separa
  // "Direitos Creditorios" (a vencer) de "Creditos Vencidos" (inad).
  dc_a_vencer: number | null
  dc_inadimplente: number | null
  // Decomposicao COMPLETA (com risco i2a vs sem risco i2b). CVM detalha
  // a-vencer/vencidos em AMBAS categorias. Cobre fundos que classificam
  // a maior parte como "sem risco" (REALINVEST, Puma).
  dc_a_vencer_com_risco: number | null
  dc_vencido_com_risco: number | null
  dc_a_vencer_sem_risco: number | null
  dc_vencido_sem_risco: number | null
}

// Cobertura PL Subordinada / Sigma(maiores cedentes) — em vezes.
// Reproduz "Indices de Cobertura da Subordinacao" da Lamina Austin (so
// cedentes, sem sacados; so top-9, limite CVM).
// `dado_indisponivel=true` quando tab_x_qt_cota=NULL (caso Puma).
export type FundoCoberturaSubordinacaoPonto = {
  competencia: string
  pl_subordinada: number | null
  cobertura_maior_cedente: number | null
  cobertura_top3_cedentes: number | null
  cobertura_top5_cedentes: number | null
  cobertura_top9_cedentes: number | null
  dado_indisponivel: boolean
}

export type FundoAtrasoBuckets = {
  b0_30: number
  b30_60: number
  b60_90: number
  b90_120: number
  b120_150: number
  b150_180: number
  b180_360: number
  b360_720: number
  b720_1080: number
  b1080_plus: number
}

export type FundoAtrasoPonto = {
  competencia: string
  buckets: FundoAtrasoBuckets
  pct_pl_total: number
}

export type FundoPrazoMedioPonto = { competencia: string; dias_aprox: number }

export type FundoCedenteLinha = {
  cpf_cnpj: string | null
  rank: number
  pct: number
}

export type FundoSetorLinha = { setor: string; valor: number; pct: number }

export type FundoSubclasseLinha = {
  classe_serie: string
  id_subclasse: string | null
  qt_cota: number
  vl_cota: number
  pl: number
  pct_pl: number
  nr_cotst: number
}

export type FundoCotistasPonto = {
  competencia: string
  por_serie: Record<string, number>
}

export type FundoCotistasTipoPonto = {
  competencia: string
  senior: Record<string, number>
  subord: Record<string, number>
}

export type FundoPLSubclassesPonto = {
  competencia: string
  por_subclasse: Record<string, number>
}

export type FundoRentPonto = {
  competencia: string
  por_subclasse: Record<string, number>
}

export type FundoRentAcumuladaPonto = {
  competencia: string
  por_subclasse: Record<string, number>
  cdi_acum: number | null
}

export type FundoDesempenhoGap = {
  esperado: number
  realizado: number
  gap: number
}

export type FundoDesempenhoPonto = {
  competencia: string
  por_subclasse: Record<string, FundoDesempenhoGap>
}

export type FundoLiquidezFaixas = {
  d0: number
  d30: number
  d60: number
  d90: number
  d180: number
  d360: number
  mais_360: number
}

export type FundoLiquidezPonto = {
  competencia: string
  faixas: FundoLiquidezFaixas
}

export type FundoFluxoCotasPonto = {
  competencia: string
  tp_oper: string
  classe_serie: string
  vl_total: number
  qt_cota: number
}

export type FundoRecompraPonto = {
  competencia: string
  qt_recompra: number
  vl_recompra: number
  vl_contab_recompra: number
  pct_pl: number | null
}

export type FundoSCRLinha = { rating: string; valor: number; pct: number }

export type FundoGarantias = { vl_garantia: number; pct_garantia: number }

export type FichaFundo = {
  identificacao: FundoIdentificacao
  pl_serie: FundoPLPonto[]
  carteira_serie: FundoCarteiraPonto[]
  atraso_serie: FundoAtrasoPonto[]
  prazo_medio_serie: FundoPrazoMedioPonto[]
  cedentes: FundoCedenteLinha[]
  setores: FundoSetorLinha[]
  subclasses: FundoSubclasseLinha[]
  cotistas_serie: FundoCotistasPonto[]
  cotistas_tipo_serie: FundoCotistasTipoPonto[]
  pl_subclasses_serie: FundoPLSubclassesPonto[]
  rent_serie: FundoRentPonto[]
  rent_acumulada: FundoRentAcumuladaPonto[]
  desempenho_vs_meta: FundoDesempenhoPonto[]
  liquidez_serie: FundoLiquidezPonto[]
  fluxo_cotas: FundoFluxoCotasPonto[]
  recompra_serie: FundoRecompraPonto[]
  scr_distribuicao: FundoSCRLinha[]
  garantias: FundoGarantias | null
  limitacoes: string[]
  cobertura_subordinacao_serie: FundoCoberturaSubordinacaoPonto[]
}

// Favoritos de fundo (por user, escopo tenant).
// Backend retorna `FavoritosLista` direto (sem envelope BIResponse) — preferencia
// pessoal nao tem proveniencia de dado canonico.

export type FavoritoItem = {
  cnpj: string
  denom_social: string | null
  created_at: string
}

export type FavoritosLista = {
  favoritos: FavoritoItem[]
  total: number
}

export const biBenchmark = {
  resumo: (f: BenchmarkFilters = {}) =>
    apiClient.get<BIResponse<BenchmarkResumo>>(
      `/bi/benchmark/resumo${benchmarkQS(f)}`,
    ),
  pdd: (f: BenchmarkFilters = {}) =>
    apiClient.get<BIResponse<PDDDistribuicao>>(
      `/bi/benchmark/pdd${benchmarkQS(f)}`,
    ),
  evolucao: (f: BenchmarkRangeFilters = {}) =>
    apiClient.get<BIResponse<BenchmarkEvolucao>>(
      `/bi/benchmark/evolucao${benchmarkRangeQS(f)}`,
    ),
  admins: (f: BenchmarkRangeFilters = {}) =>
    apiClient.get<BIResponse<BenchmarkAdmins>>(
      `/bi/benchmark/admins${benchmarkRangeQS(f)}`,
    ),
  condom: (f: BenchmarkRangeFilters = {}) =>
    apiClient.get<BIResponse<BenchmarkCondom>>(
      `/bi/benchmark/condom${benchmarkRangeQS(f)}`,
    ),
  fundos: (f: BenchmarkFilters = {}) =>
    apiClient.get<BIResponse<FundosLista>>(
      `/bi/benchmark/fundos${benchmarkQS(f)}`,
    ),
  comparativo: (a: ComparativoArgs) =>
    apiClient.get<BIResponse<ComparativoResponse>>(
      `/bi/benchmark/comparativo${comparativoQS(a)}`,
    ),
  fundo: (
    cnpj: string,
    params: { periodoInicio?: string; periodoFim?: string } = {},
  ) => {
    const digits = cnpj.replace(/\D/g, "")
    const qs = new URLSearchParams()
    if (params.periodoInicio) qs.set("periodo_inicio", params.periodoInicio)
    if (params.periodoFim) qs.set("periodo_fim", params.periodoFim)
    const suffix = qs.toString() ? `?${qs.toString()}` : ""
    return apiClient.get<BIResponse<FichaFundo>>(
      `/bi/benchmark/fundo/${digits}${suffix}`,
    )
  },
  cvmRange: () =>
    apiClient.get<{ data_minima: string | null; data_maxima: string | null }>(
      "/bi/benchmark/cvm-range",
    ),
  favoritos: () =>
    apiClient.get<FavoritosLista>("/bi/benchmark/favoritos"),
  adicionarFavorito: (cnpj: string) =>
    apiClient.put<void>(`/bi/benchmark/favoritos/${cnpj.replace(/\D/g, "")}`),
  removerFavorito: (cnpj: string) =>
    apiClient.delete<void>(`/bi/benchmark/favoritos/${cnpj.replace(/\D/g, "")}`),
}

//
// Metadados do modulo BI (taxonomias para filtros de UI).
//

export type UAOption = {
  id: number
  nome: string
  ativa: boolean
}

export type ProdutoOption = {
  sigla: string
  nome: string
  tipo_de_contrato: string | null
  produto_de_risco: boolean
}

export type DataMinimaResponse = {
  /** ISO date 'YYYY-MM-DD' ou null se tenant nao tem operacoes. */
  data_minima: string | null
}

// ───────────────────────────────────────────────────────────────────────────
// BI · Benchmark2 (lista completa de fundos CVM via <DataTableShell>)
// ───────────────────────────────────────────────────────────────────────────

export type Benchmark2FundoRow = {
  cnpj: string
  fundo: string
  condom: "aberto" | "fechado" | null
  admin: string | null
  cotistas: number | null
  pl_medio_3m: number | null
  pl_ult_mes: number | null
}

export type Benchmark2FundosLista = {
  competencia: string
  fundos: Benchmark2FundoRow[]
  total: number
}

export const biBenchmark2 = {
  fundos: () =>
    apiClient.get<Benchmark2FundosLista>("/bi/benchmark2/fundos"),
}

export const biMetadata = {
  uas: () => apiClient.get<UAOption[]>("/bi/metadata/uas"),
  produtos: () => apiClient.get<ProdutoOption[]>("/bi/metadata/produtos"),
  dataMinima: () => apiClient.get<DataMinimaResponse>("/bi/metadata/data-minima"),
}

//
// System — cross-cutting (pipeline health, etc).
//
export const system = {
  syncHealth: () => apiClient.get<SyncHealth>("/system/sync-health"),
  syncHealthSummary: () =>
    apiClient.get<SyncHealthSummary>("/system/sync-health-summary"),
}

//
// Integracoes — catalogo de fontes + CRUD de credenciais por tenant.
//

export type Environment = "sandbox" | "production"

/** Valores aceitos pelo `source_type` no backend (espelha core/enums.py::SourceType). */
export type SourceTypeId =
  | "erp:bitfin"
  | "admin:qitech"
  | "bureau:serasa_pj"
  | "bureau:serasa_pf"
  | "bureau:scr_bacen"
  | "document:nfe"
  | "self_declared"
  | "peer_declared"
  | "internal_note"
  | "derived"

export type SourceListItem = {
  source_type: SourceTypeId
  label: string
  category: string
  owner_org: string | null
  description: string | null
  configured: boolean
  enabled: boolean
  environment: Environment | null
  last_sync_at: string | null
  /** null = sob demanda. Numero = cadencia ativa do scheduler em minutos. */
  sync_frequency_minutes: number | null
  /** Multi-UA: para fontes admin (QiTech), pode haver N entradas, uma por UA. */
  unidade_administrativa_id: string | null
}

export type SourceDetail = {
  source_type: SourceTypeId
  label: string
  category: string
  owner_org: string | null
  description: string | null
  environment: Environment
  configured: boolean
  enabled: boolean
  /** Campos com secrets vem como "***SET***" — nunca em claro. */
  config: Record<string, unknown>
  sync_frequency_minutes: number | null
  updated_at: string | null
  unidade_administrativa_id: string | null
}

export type ConfigUpdatePayload = {
  config?: Record<string, unknown>
  environment?: Environment
  enabled?: boolean
  sync_frequency_minutes?: number | null
  /** Multi-UA: vincula esta credencial a uma UA do tenant. */
  unidade_administrativa_id?: string | null
}

export type TestResult = {
  ok: boolean
  latency_ms: number | null
  detail: unknown
  adapter_version: string | null
}

export type SyncResult = {
  adapter_version: string | null
  started_at: string | null
  elapsed_seconds: number | null
  since: string | null
  tables: Array<Record<string, unknown>>
  errors: string[]
}

export type RunEntry = {
  id: string
  occurred_at: string
  rule_or_model: string | null
  rule_or_model_version: string | null
  triggered_by: string
  explanation: string | null
  output: Record<string, unknown> | null
}

// CrossSourceRunEntry — espelha o backend (routers/operacao.py). Identica a
// RunEntry + campo `source_type` derivado de rule_or_model. Usada pela pagina
// /integracoes/operacao/historico (PR 4, 2026-05-21).
export type CrossSourceRunEntry = {
  id: string
  occurred_at: string
  source_type: SourceTypeId
  rule_or_model: string
  rule_or_model_version: string | null
  triggered_by: string
  explanation: string | null
  output: Record<string, unknown> | null
}

export type CrossSourceRunsFilters = {
  source_type?: SourceTypeId[]
  since?: string | null   // YYYY-MM-DD
  until?: string | null   // YYYY-MM-DD
  status?: "ok" | "error" | null
  triggered_by?: string | null
  limit?: number
}

/** Cadência por endpoint (CLAUDE.md §13 — refactor 2026-05-05).
 *
 * Granularidade fina: cada source pode ter N endpoints, cada um com cadência
 * própria. `EndpointDetail` é o catálogo + (opcional) override do tenant.
 * Quando os campos override (`enabled`, `schedule_kind`, etc) vêm `null` é
 * porque o tenant nunca persistiu — frontend deve cair no `default_*`.
 */

export type ScheduleKind = "interval" | "daily_at" | "on_demand"

export type EndpointDetail = {
  // Catálogo (sempre presente)
  name: string
  label: string
  description: string
  canonical_table: string
  default_schedule_kind: ScheduleKind
  default_schedule_value: string | null

  // Identidade cross-admin / cross-tenant (Fase 1 do refactor de proveniência
  // transversal, 2026-05-18). `admin_code` é o slug da administradora
  // (ex.: "qitech", "bitfin"). `global_id` é único no sistema todo
  // (ex.: "qitech.market.fidc_estoque"). `tenant_endpoint_handle` inclui o
  // slug do tenant (ex.: "realinvest.qitech.market.fidc_estoque") — útil pra
  // copy-to-clipboard em logs / debug / suporte.
  admin_code: string
  global_id: string
  tenant_endpoint_handle: string

  // Doc do shape do payload (Fase 2 do refactor, 2026-05-18). Path relativo
  // à raiz do repo apontando pro arquivo .md em `payload_shapes/`. `null`
  // significa que o adapter ainda não publicou catálogo. UI mostra link
  // "Ver shape" no Dialog de edição quando preenchido.
  payload_shape_doc_relpath: string | null

  // Defaults de tolerância de publicação (2026-05-15) — sempre presentes do
  // catálogo. Frontend exibe como placeholder/legenda na seção Tolerância
  // do Dialog de configuração.
  default_expected_lag_business_days: number
  default_tolerance_business_days: number
  default_give_up_business_days: number

  // Override do tenant (null se nunca foi persistida linha em TSEC)
  enabled: boolean | null
  schedule_kind: ScheduleKind | null
  schedule_value: string | null
  last_sync_started_at: string | null
  last_sync_finished_at: string | null
  last_sync_status: "ok" | "erro" | "em_progresso" | null
  last_sync_error: string | null
  unidade_administrativa_id: string | null

  // Override de tolerância (null = "segue default do catálogo").
  expected_lag_business_days_override: number | null
  tolerance_business_days_override: number | null
  give_up_business_days_override: number | null

  // Valores efetivos = override OR default. Sempre preenchidos — frontend
  // usa direto sem recombinar.
  effective_expected_lag_business_days: number
  effective_tolerance_business_days: number
  effective_give_up_business_days: number

  // Próximo sync agendado (ISO 8601 UTC). Quando `next_sync_source ===
  // "state_machine"`, vem de MIN(endpoint_date_state.next_attempt_at) —
  // próxima retentativa adaptativa ou TTL de refresh-complete. Quando
  // "schedule", é derivado de schedule_kind/value + last_sync_started_at
  // (próximo HH:MM do daily_at ou last + intervalo do interval). Quando
  // "manual_only" ou null, endpoint é on_demand ou não tem cadência —
  // só sincroniza via "Sincronizar agora".
  next_sync_at: string | null
  next_sync_source: "state_machine" | "schedule" | "manual_only" | null
}

/** Estado de tolerância de publicação — graduação por tempo decorrido.
 *
 * Aplica-se a dias cuja publicação ainda não chegou (GAP/NOT_PUBLISHED/
 * PENDING). Outros status (OK/PARTIAL/WEEKEND/etc) ficam com tolerance_state
 * null. UI usa cor + tooltip baseado no estado.
 */
export type PublicationState =
  | "esperado"
  | "atrasado"
  | "suspeito"
  | "furo_definitivo"

/** Coverage — historico de datas cobertas por endpoint (Fase 1 aba Cobertura). */
export type CoverageStatus =
  | "ok"
  | "partial"          // http 200 mas payload parcial/vazio (Opcao A, 2026-05-13)
  | "not_published"
  | "gap"
  | "weekend"
  | "holiday"
  | "pending"
  | "before_first_sync"
  | "unsupported"

/** Completeness do payload quando http=200 (Opcao A, 2026-05-13).
 *
 * Avaliado em backend/adapters/admin/qitech/completeness.py. Hoje so
 * `market.mec` e `market.rf` tem perfil especifico — outros endpoints
 * retornam 'complete' como default.
 */
export type Completeness = "complete" | "partial" | "empty"

/** Linha do sumario semantico do payload de um raw (2026-05-20).
 *
 * Carteira, papel, conta ou movimento — generico para todos os tipos. UI
 * mostra `name` sempre, `value` formatado quando presente, badge de Δ
 * quando `delta_pct` existe, icone amber + tooltip quando `suspicious`.
 *
 * `value` vem do backend como string (Decimal serializado) ou null.
 * Frontend faz Number(value) so na hora de formatar.
 */
export type ItemSummary = {
  name: string
  /** Decimal serializado como string. */
  value: string | null
  /** Decimal serializado como string. */
  delta_pct: string | null
  suspicious: boolean
  suspicious_reason: string | null
}

/** Sumario do payload bruto — alimenta o tooltip do `QiTechCoverageStrip`. */
export type PayloadSummary = {
  total_items: number
  expected_items: number | null
  suspicious_count: number
  items: ItemSummary[]
}

export type CoverageDay = {
  data: string // ISO date
  status: CoverageStatus
  http_status: number | null
  completeness: Completeness | null
  // Estado de tolerância (2026-05-15) — null quando não aplicável
  // (dia OK/PARTIAL/WEEKEND/HOLIDAY/etc).
  tolerance_state: PublicationState | null
  // Sinais de qualidade (2026-05-20) — alimentam tooltip enriquecido do
  // strip. So populados em endpoints com payload JSONB
  // (`wh_qitech_raw_relatorio`); demais vem null e UI degrada.
  fetched_at: string | null
  fetched_by_version: string | null
  payload_sha256_short: string | null
  summary: PayloadSummary | null
}

export type EndpointCoverage = {
  name: string
  label: string
  schedule_kind: ScheduleKind
  supported: boolean
  days: CoverageDay[]
  count_ok: number
  count_partial: number
  count_not_published: number
  count_gap: number
  // Janela efetiva (override OR catalogo).
  expected_lag_business_days: number | null
  tolerance_business_days: number | null
  give_up_business_days: number | null
  // Agregados por estado de tolerância no range pedido.
  count_esperado: number
  count_atrasado: number
  count_suspeito: number
  count_furo_definitivo: number
}

export type CoverageResponse = {
  start_date: string // ISO date
  end_date: string // ISO date
  endpoints: EndpointCoverage[]
}

/** Backfill assincrono — Sub-fase 2A da freshness story (2026-05-12). */
export type BackfillJobStatus =
  | "pending"
  | "running"
  | "done"
  | "failed"
  | "cancelled"

export type BackfillJobFailedDate = {
  date: string
  error: string
}

export type BackfillJob = {
  id: string
  source_type: string
  environment: Environment
  unidade_administrativa_id: string | null
  endpoint_name: string
  status: BackfillJobStatus
  dates_pending: string[]
  dates_done: string[]
  dates_failed: BackfillJobFailedDate[]
  created_by: string
  created_at: string
  updated_at: string
  started_at: string | null
  completed_at: string | null
}

export type BackfillCreatePayload = {
  dates: string[]
  environment?: Environment
  unidade_administrativa_id?: string | null
}

export type EndpointConfigPayload = {
  /** null = preserva o atual (não toca enabled). */
  enabled?: boolean | null
  schedule_kind: ScheduleKind
  /**
   * Formato depende do schedule_kind:
   *   - interval  → "60" (minutos, 15..1440)
   *   - daily_at  → "07:30" (HH:MM em America/Sao_Paulo)
   *   - on_demand → null
   */
  schedule_value: string | null
  environment?: Environment
  unidade_administrativa_id?: string | null
  /** Tolerância — null = "limpa override, herda do catálogo". Omitir o campo
   * inteiro do payload = "preserva valor atual" (semântica `model_fields_set`
   * no backend). */
  expected_lag_business_days_override?: number | null
  tolerance_business_days_override?: number | null
  give_up_business_days_override?: number | null
}

export type EndpointSyncResult = {
  ok: boolean
  adapter_version: string | null
  endpoint_name: string
  started_at: string | null
  elapsed_seconds: number | null
  rows_ingested: number
  steps: Array<Record<string, unknown>>
  errors: string[]
}

/** Helpers do modulo integracoes.
 * Obs: `source_type` contem `:` (ex.: `erp:bitfin`) — NAO encode, o backend aceita literal.
 *
 * Multi-UA (Phase F): rotas que escopam credencial admin (QiTech) aceitam
 * `unidade_administrativa_id` como query param opcional. Sem o param, casa
 * a linha legacy (UA=NULL) — preserva retrocompat.
 */
function _appendUa(qs: URLSearchParams, uaId?: string | null) {
  if (uaId) qs.set("unidade_administrativa_id", uaId)
}

export const integracoes = {
  listSources: (environment: Environment = "production") =>
    apiClient.get<SourceListItem[]>(
      `/integracoes/sources?environment=${environment}`,
    ),
  getSource: (
    sourceType: SourceTypeId,
    environment: Environment = "production",
    uaId?: string | null,
  ) => {
    const qs = new URLSearchParams({ environment })
    _appendUa(qs, uaId)
    return apiClient.get<SourceDetail>(
      `/integracoes/sources/${sourceType}?${qs.toString()}`,
    )
  },
  updateConfig: (sourceType: SourceTypeId, payload: ConfigUpdatePayload) =>
    apiClient.put<SourceDetail>(
      `/integracoes/sources/${sourceType}/config`,
      payload,
    ),
  setEnabled: (
    sourceType: SourceTypeId,
    enabled: boolean,
    environment: Environment = "production",
    uaId?: string | null,
  ) =>
    apiClient.post<SourceDetail>(
      `/integracoes/sources/${sourceType}/enable`,
      {
        enabled,
        environment,
        unidade_administrativa_id: uaId ?? null,
      },
    ),
  test: (
    sourceType: SourceTypeId,
    environment: Environment = "production",
    uaId?: string | null,
  ) => {
    const qs = new URLSearchParams({ environment })
    _appendUa(qs, uaId)
    return apiClient.post<TestResult>(
      `/integracoes/sources/${sourceType}/test?${qs.toString()}`,
    )
  },
  sync: (
    sourceType: SourceTypeId,
    environment: Environment = "production",
    uaId?: string | null,
  ) => {
    const qs = new URLSearchParams({ environment })
    _appendUa(qs, uaId)
    return apiClient.post<SyncResult>(
      `/integracoes/sources/${sourceType}/sync?${qs.toString()}`,
    )
  },
  runs: (sourceType: SourceTypeId, limit = 50) =>
    apiClient.get<RunEntry[]>(
      `/integracoes/sources/${sourceType}/runs?limit=${limit}`,
    ),

  // Historico cross-source (PR 4). Filtros opcionais por fonte (multi), janela
  // de tempo, status (ok/error) e quem disparou. Mora em /integracoes/operacao/
  // (router separado pra nao colidir com /sources/{source_type}/runs).
  crossRuns: (filters: CrossSourceRunsFilters = {}) => {
    const qs = new URLSearchParams()
    for (const st of filters.source_type ?? []) qs.append("source_type", st)
    if (filters.since) qs.set("since", filters.since)
    if (filters.until) qs.set("until", filters.until)
    if (filters.status) qs.set("status", filters.status)
    if (filters.triggered_by) qs.set("triggered_by", filters.triggered_by)
    if (filters.limit !== undefined) qs.set("limit", String(filters.limit))
    const s = qs.toString()
    return apiClient.get<CrossSourceRunEntry[]>(
      s ? `/integracoes/operacao/runs?${s}` : `/integracoes/operacao/runs`,
    )
  },

  // Cadência por endpoint (CLAUDE.md §13). encodeURIComponent no endpoint_name
  // porque pode conter "." (ex.: "market.outros_fundos") — o backend usa
  // {endpoint_name:path} no Path() e aceita o ponto, mas mantemos o encode
  // como defesa para casos com chars inesperados.
  listEndpoints: (
    sourceType: SourceTypeId,
    environment: Environment = "production",
    uaId?: string | null,
  ) => {
    const qs = new URLSearchParams({ environment })
    if (uaId) qs.set("ua", uaId)
    return apiClient.get<EndpointDetail[]>(
      `/integracoes/sources/${sourceType}/endpoints?${qs.toString()}`,
    )
  },
  getEndpoint: (
    sourceType: SourceTypeId,
    endpointName: string,
    environment: Environment = "production",
    uaId?: string | null,
  ) => {
    const qs = new URLSearchParams({ environment })
    if (uaId) qs.set("ua", uaId)
    return apiClient.get<EndpointDetail>(
      `/integracoes/sources/${sourceType}/endpoints/${encodeURIComponent(
        endpointName,
      )}?${qs.toString()}`,
    )
  },
  updateEndpoint: (
    sourceType: SourceTypeId,
    endpointName: string,
    payload: EndpointConfigPayload,
  ) =>
    apiClient.put<EndpointDetail>(
      `/integracoes/sources/${sourceType}/endpoints/${encodeURIComponent(
        endpointName,
      )}`,
      payload,
    ),
  syncEndpoint: (
    sourceType: SourceTypeId,
    endpointName: string,
    environment: Environment = "production",
    uaId?: string | null,
  ) => {
    const qs = new URLSearchParams({ environment })
    if (uaId) qs.set("ua", uaId)
    return apiClient.post<EndpointSyncResult>(
      `/integracoes/sources/${sourceType}/endpoints/${encodeURIComponent(
        endpointName,
      )}/sync?${qs.toString()}`,
    )
  },
  coverage: (
    sourceType: SourceTypeId,
    options: { rangeDays?: number; uaId?: string | null } = {},
  ) => {
    const qs = new URLSearchParams({
      range_days: String(options.rangeDays ?? 180),
    })
    if (options.uaId) qs.set("ua", options.uaId)
    return apiClient.get<CoverageResponse>(
      `/integracoes/sources/${sourceType}/coverage?${qs.toString()}`,
    )
  },
  createBackfill: (
    sourceType: SourceTypeId,
    endpointName: string,
    payload: BackfillCreatePayload,
  ) =>
    apiClient.post<BackfillJob>(
      `/integracoes/sources/${sourceType}/endpoints/${encodeURIComponent(
        endpointName,
      )}/backfill`,
      payload,
    ),
  getBackfillJob: (sourceType: SourceTypeId, jobId: string) =>
    apiClient.get<BackfillJob>(
      `/integracoes/sources/${sourceType}/backfill/${jobId}`,
    ),
  cancelBackfillJob: (sourceType: SourceTypeId, jobId: string) =>
    apiClient.delete<BackfillJob>(
      `/integracoes/sources/${sourceType}/backfill/${jobId}`,
    ),
  listActiveBackfills: (
    sourceType: SourceTypeId,
    endpointName?: string,
  ) => {
    const qs = new URLSearchParams()
    if (endpointName) qs.set("endpoint_name", endpointName)
    const suffix = qs.toString() ? `?${qs.toString()}` : ""
    return apiClient.get<BackfillJob[]>(
      `/integracoes/sources/${sourceType}/backfill/active${suffix}`,
    )
  },
}

/** Modulo cadastros — entidades primarias do tenant. */

export type TipoUA =
  | "fidc"
  | "consultoria"
  | "securitizadora"
  | "factoring"
  | "gestora"

export type UnidadeAdministrativa = {
  id: string
  tenant_id: string
  nome: string
  cnpj: string | null
  tipo: TipoUA
  ativa: boolean
  bitfin_ua_id: number | null
  created_at: string
  updated_at: string
}

export type UACreatePayload = {
  nome: string
  cnpj?: string | null
  tipo: TipoUA
  ativa?: boolean
  bitfin_ua_id?: number | null
}

export type UAUpdatePayload = Partial<UACreatePayload>

export type UAListFilters = {
  ativa?: boolean
  tipo?: TipoUA
}

export const cadastros = {
  listUAs: (filters: UAListFilters = {}) => {
    const params = new URLSearchParams()
    if (filters.ativa !== undefined) params.set("ativa", String(filters.ativa))
    if (filters.tipo !== undefined) params.set("tipo", filters.tipo)
    const qs = params.toString()
    return apiClient.get<UnidadeAdministrativa[]>(
      `/cadastros/unidades-administrativas${qs ? `?${qs}` : ""}`,
    )
  },
  getUA: (id: string) =>
    apiClient.get<UnidadeAdministrativa>(
      `/cadastros/unidades-administrativas/${id}`,
    ),
  createUA: (payload: UACreatePayload) =>
    apiClient.post<UnidadeAdministrativa>(
      "/cadastros/unidades-administrativas",
      payload,
    ),
  updateUA: (id: string, payload: UAUpdatePayload) =>
    apiClient.patch<UnidadeAdministrativa>(
      `/cadastros/unidades-administrativas/${id}`,
      payload,
    ),
  deleteUA: (id: string) =>
    apiClient.delete<void>(`/cadastros/unidades-administrativas/${id}`),
}

// ─────────────────────────────────────────────────────────────────────────────
// Controladoria · Cota Sub
// ─────────────────────────────────────────────────────────────────────────────

// Detector de itens nao reconhecidos (2026-05-27, pos-VCNC). Um valor novo num
// campo de classificacao que vaza pro residuo (vaza_residuo), entra num driver
// indevidamente (entra_indevido) ou e exposto pra auditoria (vigia).
export type NaoReconhecidoModo = "vaza_residuo" | "entra_indevido" | "vigia"

export type ItemNaoReconhecido = {
  fonte:          string  // tabela silver origem
  endpoint:       string  // endpoint QiTech
  campo:          string  // campo de classificacao que falhou
  identificador:  string  // valor cru nao reconhecido
  label:          string  // rotulo humano
  valor_d0:       number
  valor_d_prev:   number
  modo:           NaoReconhecidoModo
  driver_afetado: string
  motivo:         string
}

// Decimal vem como string no JSON do Pydantic — coercao via _coerceNaoReconhecido.
type ItemNaoReconhecidoDTO = Omit<ItemNaoReconhecido, "valor_d0" | "valor_d_prev"> & {
  valor_d0:     number | string
  valor_d_prev: number | string
}

function _coerceNaoReconhecido(i: ItemNaoReconhecidoDTO): ItemNaoReconhecido {
  return { ...i, valor_d0: Number(i.valor_d0), valor_d_prev: Number(i.valor_d_prev) }
}

// ── Balanco Patrimonial (Balance hero, F1 do redesign 2026-05-22) ──────────
//
// Endpoint /controladoria/cota-sub/balanco-patrimonial — shape dedicado ao
// novo Balance hero. Sinais ABSOLUTOS: passivos vem positivos no payload.

export type CategoriaPatrimonialKey =
  | "compromissada"
  | "titulos_publicos"
  | "fundos_di"
  | "dc"
  | "op_estruturadas"
  | "outros_ativos"
  | "cpr_receber"
  | "tesouraria"
  | "saldo_conta_corrente"
  | "cpr_pagar"
  | "mezanino"
  | "senior"
  | "pdd"


export type CategoriaPatrimonial = {
  key:    CategoriaPatrimonialKey
  label:  string
  tipo:   "ativo" | "passivo"
  d1:     number
  d0:     number
  delta:  number
  source: string
  /** Contra-ativo (redutor, ex.: PDD): polaridade do delta invertida —
   *  subir piora o PL Sub, entao positivo=vermelho / negativo=verde. */
  contra?: boolean
}


// Endpoint /controladoria/cota-sub/balanco-estrutural — redesign 2026-05-27.
// Coerente por natureza + sinal: PDD = contra-ativo (abate DC), CPR dividido
// por sinal (a receber=ativo / a pagar=passivo), Senior+Mezanino agrupados como
// "Cotas Prioritarias", residuo MEC em bloco de reconciliacao (nao e linha).

export type BalancoNaturezaLinha = "ativo" | "contra_ativo" | "passivo"
export type BalancoGrupoKey =
  | "direitos_creditorios"
  | "aplicacoes"
  | "disponibilidades"
  | "operacional"
  | "cotas_prioritarias"

type BalancoLinhaEstruturalDTO = {
  key:         string
  label:       string
  natureza:    BalancoNaturezaLinha
  grupo:       BalancoGrupoKey
  grupo_label: string
  d1:          number | string
  d0:          number | string
  delta:       number | string
  source:      string
  drill_key:   CategoriaPatrimonialKey | null
}

export type BalancoLinhaEstrutural = {
  key:         string
  label:       string
  natureza:    BalancoNaturezaLinha
  grupo:       BalancoGrupoKey
  grupo_label: string
  d1:          number
  d0:          number
  delta:       number
  source:      string
  drill_key:   CategoriaPatrimonialKey | null
}

type ReconciliacaoMecDTO = {
  pl_fonte_d1:       number | string
  pl_fonte_d0:       number | string
  pl_fonte_delta:    number | string
  residuo_d1:        number | string
  residuo_d0:        number | string
  residuo_delta:     number | string
  dentro_tolerancia: boolean
}

export type ReconciliacaoMec = {
  pl_fonte_d1:       number
  pl_fonte_d0:       number
  pl_fonte_delta:    number
  residuo_d1:        number
  residuo_d0:        number
  residuo_delta:     number
  dentro_tolerancia: boolean
}

type BalancoEstruturalResponseDTO = {
  fundo_id:            string
  fundo_nome:          string
  data:                string
  data_anterior:       string
  ativos:              BalancoLinhaEstruturalDTO[]
  passivos:            BalancoLinhaEstruturalDTO[]
  dc_liquido_d1:       number | string
  dc_liquido_d0:       number | string
  dc_liquido_delta:    number | string
  total_ativo_d1:      number | string
  total_ativo_d0:      number | string
  total_ativo_delta:   number | string
  total_passivo_d1:    number | string
  total_passivo_d0:    number | string
  total_passivo_delta: number | string
  pl_sub_d1:           number | string
  pl_sub_d0:           number | string
  pl_sub_delta:        number | string
  reconciliacao:       ReconciliacaoMecDTO
  nao_reconhecidos?:   ItemNaoReconhecidoDTO[]
}

export type BalancoEstruturalResponse = {
  fundo_id:            string
  fundo_nome:          string
  data:                string
  data_anterior:       string
  ativos:              BalancoLinhaEstrutural[]
  passivos:            BalancoLinhaEstrutural[]
  dc_liquido_d1:       number
  dc_liquido_d0:       number
  dc_liquido_delta:    number
  total_ativo_d1:      number
  total_ativo_d0:      number
  total_ativo_delta:   number
  total_passivo_d1:    number
  total_passivo_d0:    number
  total_passivo_delta: number
  pl_sub_d1:           number
  pl_sub_d0:           number
  pl_sub_delta:        number
  reconciliacao:       ReconciliacaoMec
  nao_reconhecidos:    ItemNaoReconhecido[]
}

function _coerceBalancoLinhaEstrutural(l: BalancoLinhaEstruturalDTO): BalancoLinhaEstrutural {
  return {
    key:         l.key,
    label:       l.label,
    natureza:    l.natureza,
    grupo:       l.grupo,
    grupo_label: l.grupo_label,
    d1:          Number(l.d1),
    d0:          Number(l.d0),
    delta:       Number(l.delta),
    source:      l.source,
    drill_key:   l.drill_key,
  }
}

function _coerceBalancoEstrutural(r: BalancoEstruturalResponseDTO): BalancoEstruturalResponse {
  return {
    fundo_id:            r.fundo_id,
    fundo_nome:          r.fundo_nome,
    data:                r.data,
    data_anterior:       r.data_anterior,
    ativos:              r.ativos.map(_coerceBalancoLinhaEstrutural),
    passivos:            r.passivos.map(_coerceBalancoLinhaEstrutural),
    dc_liquido_d1:       Number(r.dc_liquido_d1),
    dc_liquido_d0:       Number(r.dc_liquido_d0),
    dc_liquido_delta:    Number(r.dc_liquido_delta),
    total_ativo_d1:      Number(r.total_ativo_d1),
    total_ativo_d0:      Number(r.total_ativo_d0),
    total_ativo_delta:   Number(r.total_ativo_delta),
    total_passivo_d1:    Number(r.total_passivo_d1),
    total_passivo_d0:    Number(r.total_passivo_d0),
    total_passivo_delta: Number(r.total_passivo_delta),
    pl_sub_d1:           Number(r.pl_sub_d1),
    pl_sub_d0:           Number(r.pl_sub_d0),
    pl_sub_delta:        Number(r.pl_sub_delta),
    reconciliacao: {
      pl_fonte_d1:       Number(r.reconciliacao.pl_fonte_d1),
      pl_fonte_d0:       Number(r.reconciliacao.pl_fonte_d0),
      pl_fonte_delta:    Number(r.reconciliacao.pl_fonte_delta),
      residuo_d1:        Number(r.reconciliacao.residuo_d1),
      residuo_d0:        Number(r.reconciliacao.residuo_d0),
      residuo_delta:     Number(r.reconciliacao.residuo_delta),
      dentro_tolerancia: r.reconciliacao.dentro_tolerancia,
    },
    nao_reconhecidos: (r.nao_reconhecidos ?? []).map(_coerceNaoReconhecido),
  }
}

// ── Drills DC + PDD + CPR (F2 do redesign, 2026-05-23) ─────────────────────
//
// Endpoints /controladoria/cota-sub/drill/{dc,pdd,cpr} — cada um abre o
// DrillDownSheet lateral direito quando user clica na categoria correspondente
// do Balance hero. Sinais absolutos; UI interpreta.

// ---- DRILL DC ----
type DrillDcAquisicaoDTO = {
  cedente_doc:        string
  cedente_nome:       string
  sacado_doc:         string
  sacado_nome:        string
  seu_numero:         string
  numero_documento:   string
  tipo_recebivel:     string
  data_vencimento:    string | null
  valor_compra:       number | string
  valor_vencimento:   number | string
  taxa_aquisicao:     number | string
  prazo_recebivel:    number
}
export type DrillDcAquisicao = Omit<DrillDcAquisicaoDTO, "valor_compra" | "valor_vencimento" | "taxa_aquisicao"> & {
  valor_compra:     number
  valor_vencimento: number
  taxa_aquisicao:   number
}

type DrillDcLiquidacaoPorTipoDTO = {
  tipo_movimento:       string
  qtd_papeis:           number
  sum_valor_pago:       number | string
  sum_valor_aquisicao:  number | string
  sum_valor_vencimento: number | string
  sum_ajuste:           number | string
  ganho_liquido:        number | string
}
export type DrillDcLiquidacaoPorTipo = {
  tipo_movimento:       string
  qtd_papeis:           number
  sum_valor_pago:       number
  sum_valor_aquisicao:  number
  sum_valor_vencimento: number
  sum_ajuste:           number
  ganho_liquido:        number
}

type DrillDcLiquidacaoLinhaDTO = {
  cedente_doc:      string
  cedente_nome:     string
  sacado_doc:       string
  sacado_nome:      string
  seu_numero:       string
  documento:        string
  tipo_recebivel:   string
  tipo_movimento:   string
  valor_pago:       number | string
  valor_aquisicao:  number | string
  valor_vencimento: number | string
  ajuste:           number | string
  ganho_liquido:    number | string
}
export type DrillDcLiquidacaoLinha = Omit<
  DrillDcLiquidacaoLinhaDTO,
  "valor_pago" | "valor_aquisicao" | "valor_vencimento" | "ajuste" | "ganho_liquido"
> & {
  valor_pago:       number
  valor_aquisicao:  number
  valor_vencimento: number
  ajuste:           number
  ganho_liquido:    number
}

type DrillDcApropriacaoDTO = {
  estoque_d1:         number | string
  estoque_d0:         number | string
  delta_estoque:      number | string
  aquisicoes_total:   number | string
  liquidacoes_total:  number | string
  apropriacao:        number | string
}
export type DrillDcApropriacao = {
  estoque_d1:         number
  estoque_d0:         number
  delta_estoque:      number
  aquisicoes_total:   number
  liquidacoes_total:  number
  apropriacao:        number
}

// F2 redesign 2026-05-24: decomposicao do ΔDC em 5 buckets a partir do granular.
type DrillDcDecomposicaoDTO = {
  saldo_d1:                       number | string
  saldo_d0:                       number | string
  delta_saldo:                    number | string
  aquisicoes_n:                   number
  aquisicoes_total:               number | string
  liquidacoes_n:                  number
  liquidacoes_total:              number | string
  migracao_wop_n:                 number
  migracao_wop_total:             number | string
  apropriacao_n:                  number
  apropriacao_total:              number | string
  mutacao_n:                      number
  mutacao_total:                  number | string
  residuo:                        number | string
  cross_check_aquisicoes_evento:  (number | string) | null
  cross_check_liquidacoes_evento: (number | string) | null
  cross_check_diff_aquisicoes:    (number | string) | null
  cross_check_diff_liquidacoes:   (number | string) | null
}
export type DrillDcDecomposicao = {
  saldo_d1:                       number
  saldo_d0:                       number
  delta_saldo:                    number
  aquisicoes_n:                   number
  aquisicoes_total:               number
  liquidacoes_n:                  number
  liquidacoes_total:              number
  migracao_wop_n:                 number
  migracao_wop_total:             number
  apropriacao_n:                  number
  apropriacao_total:              number
  mutacao_n:                      number
  mutacao_total:                  number
  residuo:                        number
  cross_check_aquisicoes_evento:  number | null
  cross_check_liquidacoes_evento: number | null
  cross_check_diff_aquisicoes:    number | null
  cross_check_diff_liquidacoes:   number | null
}

type DrillDcMutacaoPapelDTO = {
  cedente_doc:        string
  cedente_nome:       string
  sacado_doc:         string
  sacado_nome:        string
  seu_numero:         string
  numero_documento:   string
  tipo_recebivel:     string
  vp_d1:              number | string
  vp_d0:              number | string
  delta_vp:           number | string
  vn_d1:              number | string
  vn_d0:              number | string
  taxa_d1:            number | string
  taxa_d0:            number | string
  venc_d1:            string | null
  venc_d0:            string | null
  mudou_vn:           boolean
  mudou_taxa:         boolean
  mudou_venc:         boolean
}
export type DrillDcMutacaoPapel = Omit<
  DrillDcMutacaoPapelDTO,
  "vp_d1" | "vp_d0" | "delta_vp" | "vn_d1" | "vn_d0" | "taxa_d1" | "taxa_d0"
> & {
  vp_d1:    number
  vp_d0:    number
  delta_vp: number
  vn_d1:    number
  vn_d0:    number
  taxa_d1:  number
  taxa_d0:  number
}

type DrillDcMigracaoWopPapelDTO = {
  cedente_doc:        string
  cedente_nome:       string
  sacado_doc:         string
  sacado_nome:        string
  seu_numero:         string
  numero_documento:   string
  tipo_recebivel:     string
  faixa_pdd_d1:       string
  vp_d1:              number | string
  valor_pdd_d1:       number | string
}
export type DrillDcMigracaoWopPapel = Omit<
  DrillDcMigracaoWopPapelDTO,
  "vp_d1" | "valor_pdd_d1"
> & {
  vp_d1:        number
  valor_pdd_d1: number
}

type DrillDcResponseDTO = {
  fundo_id:               string
  fundo_nome:             string
  data:                   string
  data_anterior:          string
  aquisicoes_qtd:         number
  aquisicoes_total:       number | string
  aquisicoes:             DrillDcAquisicaoDTO[]
  liquidacoes_qtd:        number
  liquidacoes_total:      number | string
  liquidacoes_por_tipo:   DrillDcLiquidacaoPorTipoDTO[]
  liquidacoes_top:        DrillDcLiquidacaoLinhaDTO[]
  apropriacao:            DrillDcApropriacaoDTO
  decomposicao:           DrillDcDecomposicaoDTO
  mutacao_papeis:         DrillDcMutacaoPapelDTO[]
  migracao_wop_papeis:    DrillDcMigracaoWopPapelDTO[]
}
export type DrillDcResponse = {
  fundo_id:               string
  fundo_nome:             string
  data:                   string
  data_anterior:          string
  aquisicoes_qtd:         number
  aquisicoes_total:       number
  aquisicoes:             DrillDcAquisicao[]
  liquidacoes_qtd:        number
  liquidacoes_total:      number
  liquidacoes_por_tipo:   DrillDcLiquidacaoPorTipo[]
  liquidacoes_top:        DrillDcLiquidacaoLinha[]
  apropriacao:            DrillDcApropriacao
  decomposicao:           DrillDcDecomposicao
  mutacao_papeis:         DrillDcMutacaoPapel[]
  migracao_wop_papeis:    DrillDcMigracaoWopPapel[]
}

function _coerceDrillDcAquisicao(a: DrillDcAquisicaoDTO): DrillDcAquisicao {
  return {
    ...a,
    valor_compra:     Number(a.valor_compra),
    valor_vencimento: Number(a.valor_vencimento),
    taxa_aquisicao:   Number(a.taxa_aquisicao),
  }
}

function _coerceDrillDcLiquidacaoPorTipo(t: DrillDcLiquidacaoPorTipoDTO): DrillDcLiquidacaoPorTipo {
  return {
    tipo_movimento:       t.tipo_movimento,
    qtd_papeis:           t.qtd_papeis,
    sum_valor_pago:       Number(t.sum_valor_pago),
    sum_valor_aquisicao:  Number(t.sum_valor_aquisicao),
    sum_valor_vencimento: Number(t.sum_valor_vencimento),
    sum_ajuste:           Number(t.sum_ajuste),
    ganho_liquido:        Number(t.ganho_liquido),
  }
}

function _coerceDrillDcLiquidacaoLinha(l: DrillDcLiquidacaoLinhaDTO): DrillDcLiquidacaoLinha {
  return {
    ...l,
    valor_pago:       Number(l.valor_pago),
    valor_aquisicao:  Number(l.valor_aquisicao),
    valor_vencimento: Number(l.valor_vencimento),
    ajuste:           Number(l.ajuste),
    ganho_liquido:    Number(l.ganho_liquido),
  }
}

function _coerceDrillDcDecomposicao(d: DrillDcDecomposicaoDTO): DrillDcDecomposicao {
  const numOrNull = (v: (number | string) | null) => v === null ? null : Number(v)
  return {
    saldo_d1:                       Number(d.saldo_d1),
    saldo_d0:                       Number(d.saldo_d0),
    delta_saldo:                    Number(d.delta_saldo),
    aquisicoes_n:                   d.aquisicoes_n,
    aquisicoes_total:               Number(d.aquisicoes_total),
    liquidacoes_n:                  d.liquidacoes_n,
    liquidacoes_total:              Number(d.liquidacoes_total),
    migracao_wop_n:                 d.migracao_wop_n,
    migracao_wop_total:             Number(d.migracao_wop_total),
    apropriacao_n:                  d.apropriacao_n,
    apropriacao_total:              Number(d.apropriacao_total),
    mutacao_n:                      d.mutacao_n,
    mutacao_total:                  Number(d.mutacao_total),
    residuo:                        Number(d.residuo),
    cross_check_aquisicoes_evento:  numOrNull(d.cross_check_aquisicoes_evento),
    cross_check_liquidacoes_evento: numOrNull(d.cross_check_liquidacoes_evento),
    cross_check_diff_aquisicoes:    numOrNull(d.cross_check_diff_aquisicoes),
    cross_check_diff_liquidacoes:   numOrNull(d.cross_check_diff_liquidacoes),
  }
}

function _coerceDrillDcMutacaoPapel(p: DrillDcMutacaoPapelDTO): DrillDcMutacaoPapel {
  return {
    ...p,
    vp_d1:    Number(p.vp_d1),
    vp_d0:    Number(p.vp_d0),
    delta_vp: Number(p.delta_vp),
    vn_d1:    Number(p.vn_d1),
    vn_d0:    Number(p.vn_d0),
    taxa_d1:  Number(p.taxa_d1),
    taxa_d0:  Number(p.taxa_d0),
  }
}

function _coerceDrillDcMigracaoWopPapel(p: DrillDcMigracaoWopPapelDTO): DrillDcMigracaoWopPapel {
  return {
    ...p,
    vp_d1:        Number(p.vp_d1),
    valor_pdd_d1: Number(p.valor_pdd_d1),
  }
}

function _coerceDrillDc(r: DrillDcResponseDTO): DrillDcResponse {
  return {
    fundo_id:               r.fundo_id,
    fundo_nome:             r.fundo_nome,
    data:                   r.data,
    data_anterior:          r.data_anterior,
    aquisicoes_qtd:         r.aquisicoes_qtd,
    aquisicoes_total:       Number(r.aquisicoes_total),
    aquisicoes:             r.aquisicoes.map(_coerceDrillDcAquisicao),
    liquidacoes_qtd:        r.liquidacoes_qtd,
    liquidacoes_total:      Number(r.liquidacoes_total),
    liquidacoes_por_tipo:   r.liquidacoes_por_tipo.map(_coerceDrillDcLiquidacaoPorTipo),
    liquidacoes_top:        r.liquidacoes_top.map(_coerceDrillDcLiquidacaoLinha),
    apropriacao: {
      estoque_d1:        Number(r.apropriacao.estoque_d1),
      estoque_d0:        Number(r.apropriacao.estoque_d0),
      delta_estoque:     Number(r.apropriacao.delta_estoque),
      aquisicoes_total:  Number(r.apropriacao.aquisicoes_total),
      liquidacoes_total: Number(r.apropriacao.liquidacoes_total),
      apropriacao:       Number(r.apropriacao.apropriacao),
    },
    decomposicao:        _coerceDrillDcDecomposicao(r.decomposicao),
    mutacao_papeis:      r.mutacao_papeis.map(_coerceDrillDcMutacaoPapel),
    migracao_wop_papeis: r.migracao_wop_papeis.map(_coerceDrillDcMigracaoWopPapel),
  }
}

// ---- DRILL PDD ----
export type PddFaixaKey = "A" | "B" | "C" | "D" | "E" | "F" | "G" | "H" | "WOP" | "LIQUIDADO" | "NOVO"

type DrillPddMigracaoCelulaDTO = {
  faixa_de:               PddFaixaKey
  faixa_para:             PddFaixaKey
  qtd_papeis:             number
  sum_valor_nominal:      number | string
  sum_valor_presente_d1:  number | string
  sum_valor_presente_d0:  number | string
  sum_valor_pdd_d1:       number | string
  sum_valor_pdd_d0:       number | string
  sum_delta_pdd:          number | string
}
export type DrillPddMigracaoCelula = {
  faixa_de:               PddFaixaKey
  faixa_para:             PddFaixaKey
  qtd_papeis:             number
  sum_valor_nominal:      number
  sum_valor_presente_d1:  number
  sum_valor_presente_d0:  number
  sum_valor_pdd_d1:       number
  sum_valor_pdd_d0:       number
  sum_delta_pdd:          number
}

type DrillPddPapelDTO = {
  cedente_doc:                string
  cedente_nome:               string
  sacado_doc:                 string
  sacado_nome:                string
  seu_numero:                 string
  numero_documento:           string
  tipo_recebivel:             string
  valor_nominal:              number | string
  data_vencimento_ajustada:   string | null
  faixa_pdd_d1:               PddFaixaKey | null
  faixa_pdd_d0:               PddFaixaKey | null
  valor_pdd_d1:               number | string
  valor_pdd_d0:               number | string
  delta_valor_pdd:            number | string
  situacao_recebivel_d0:      string | null
}
export type DrillPddPapel = Omit<
  DrillPddPapelDTO,
  "valor_nominal" | "valor_pdd_d1" | "valor_pdd_d0" | "delta_valor_pdd"
> & {
  valor_nominal:   number
  valor_pdd_d1:    number
  valor_pdd_d0:    number
  delta_valor_pdd: number
}

type DrillPddResponseDTO = {
  fundo_id:                       string
  fundo_nome:                     string
  data:                           string
  data_anterior:                  string
  pdd_consolidado_d1:             number | string
  pdd_consolidado_d0:             number | string
  pdd_consolidado_delta:          number | string
  pdd_granular_d1:                number | string
  pdd_granular_d0:                number | string
  pdd_granular_ex_wop_d1:         number | string
  pdd_granular_ex_wop_d0:         number | string
  pdd_granular_wop_d1:            number | string
  pdd_granular_wop_d0:            number | string
  estoque_disponivel_d1:          boolean
  estoque_disponivel_d0:          boolean
  motivo_indisponivel:            string | null
  matriz:                         DrillPddMigracaoCelulaDTO[]
  papeis_wop:                     DrillPddPapelDTO[]
  papeis_wop_total_pdd_d1:        number | string
  top_papeis:                     DrillPddPapelDTO[]
  top_papeis_threshold_brl:       number | string
  top_papeis_n_solicitado:        number
  top_papeis_total_acima_threshold: number
}
export type DrillPddResponse = {
  fundo_id:                       string
  fundo_nome:                     string
  data:                           string
  data_anterior:                  string
  pdd_consolidado_d1:             number
  pdd_consolidado_d0:             number
  pdd_consolidado_delta:          number
  pdd_granular_d1:                number
  pdd_granular_d0:                number
  pdd_granular_ex_wop_d1:         number
  pdd_granular_ex_wop_d0:         number
  pdd_granular_wop_d1:            number
  pdd_granular_wop_d0:            number
  estoque_disponivel_d1:          boolean
  estoque_disponivel_d0:          boolean
  motivo_indisponivel:            string | null
  matriz:                         DrillPddMigracaoCelula[]
  papeis_wop:                     DrillPddPapel[]
  papeis_wop_total_pdd_d1:        number
  top_papeis:                     DrillPddPapel[]
  top_papeis_threshold_brl:       number
  top_papeis_n_solicitado:        number
  top_papeis_total_acima_threshold: number
}

function _coerceDrillPddCelula(c: DrillPddMigracaoCelulaDTO): DrillPddMigracaoCelula {
  return {
    faixa_de:               c.faixa_de,
    faixa_para:             c.faixa_para,
    qtd_papeis:             c.qtd_papeis,
    sum_valor_nominal:      Number(c.sum_valor_nominal),
    sum_valor_presente_d1:  Number(c.sum_valor_presente_d1),
    sum_valor_presente_d0:  Number(c.sum_valor_presente_d0),
    sum_valor_pdd_d1:       Number(c.sum_valor_pdd_d1),
    sum_valor_pdd_d0:       Number(c.sum_valor_pdd_d0),
    sum_delta_pdd:          Number(c.sum_delta_pdd),
  }
}

function _coerceDrillPddPapel(p: DrillPddPapelDTO): DrillPddPapel {
  return {
    ...p,
    valor_nominal:   Number(p.valor_nominal),
    valor_pdd_d1:    Number(p.valor_pdd_d1),
    valor_pdd_d0:    Number(p.valor_pdd_d0),
    delta_valor_pdd: Number(p.delta_valor_pdd),
  }
}

function _coerceDrillPdd(r: DrillPddResponseDTO): DrillPddResponse {
  return {
    fundo_id:                       r.fundo_id,
    fundo_nome:                     r.fundo_nome,
    data:                           r.data,
    data_anterior:                  r.data_anterior,
    pdd_consolidado_d1:             Number(r.pdd_consolidado_d1),
    pdd_consolidado_d0:             Number(r.pdd_consolidado_d0),
    pdd_consolidado_delta:          Number(r.pdd_consolidado_delta),
    pdd_granular_d1:                Number(r.pdd_granular_d1),
    pdd_granular_d0:                Number(r.pdd_granular_d0),
    pdd_granular_ex_wop_d1:         Number(r.pdd_granular_ex_wop_d1 ?? 0),
    pdd_granular_ex_wop_d0:         Number(r.pdd_granular_ex_wop_d0 ?? 0),
    pdd_granular_wop_d1:            Number(r.pdd_granular_wop_d1 ?? 0),
    pdd_granular_wop_d0:            Number(r.pdd_granular_wop_d0 ?? 0),
    estoque_disponivel_d1:          r.estoque_disponivel_d1,
    estoque_disponivel_d0:          r.estoque_disponivel_d0,
    motivo_indisponivel:            r.motivo_indisponivel,
    matriz:                         r.matriz.map(_coerceDrillPddCelula),
    papeis_wop:                     r.papeis_wop.map(_coerceDrillPddPapel),
    papeis_wop_total_pdd_d1:        Number(r.papeis_wop_total_pdd_d1),
    top_papeis:                     r.top_papeis.map(_coerceDrillPddPapel),
    top_papeis_threshold_brl:       Number(r.top_papeis_threshold_brl),
    top_papeis_n_solicitado:        r.top_papeis_n_solicitado,
    top_papeis_total_acima_threshold: r.top_papeis_total_acima_threshold,
  }
}

// ---- DRILL CPR ----
export type CprNaturezaKey =
  | "diferimento"
  | "apropriacao_taxa"
  | "apropriacao_despesa"
  | "iof_ir"
  | "provisao_liquidacao"
  | "aporte_engaiolado"
  | "outros"

type DrillCprLinhaDTO = {
  descricao:           string
  historico_traduzido: string
  valor_d1:            number | string
  valor_d0:            number | string
  delta_valor:         number | string
  natureza:            CprNaturezaKey
}
export type DrillCprLinha = Omit<DrillCprLinhaDTO, "valor_d1" | "valor_d0" | "delta_valor"> & {
  valor_d1:    number
  valor_d0:    number
  delta_valor: number
}

type DrillCprNaturezaGroupDTO = {
  natureza:        CprNaturezaKey
  label:           string
  qtd_linhas:      number
  sum_valor_d1:    number | string
  sum_valor_d0:    number | string
  sum_delta:       number | string
  top_linhas:      DrillCprLinhaDTO[]
}
export type DrillCprNaturezaGroup = {
  natureza:     CprNaturezaKey
  label:        string
  qtd_linhas:   number
  sum_valor_d1: number
  sum_valor_d0: number
  sum_delta:    number
  top_linhas:   DrillCprLinha[]
}

export type AporteEngaioladoEstado = "entrou" | "devolvido" | "persiste"

type DrillCprAporteEngaioladoDTO = {
  descricao:    string
  estado:       AporteEngaioladoEstado
  valor_d1:     number | string
  valor_d0:     number | string
  delta_valor:  number | string
}
export type DrillCprAporteEngaiolado = {
  descricao:    string
  estado:       AporteEngaioladoEstado
  valor_d1:     number
  valor_d0:     number
  delta_valor:  number
}

type DrillCprResponseDTO = {
  fundo_id:             string
  fundo_nome:           string
  data:                 string
  data_anterior:        string
  cpr_total_d1:         number | string
  cpr_total_d0:         number | string
  cpr_total_delta:      number | string
  qtd_linhas_d1:        number
  qtd_linhas_d0:        number
  naturezas:            DrillCprNaturezaGroupDTO[]
  aportes_engaiolados:  DrillCprAporteEngaioladoDTO[]
}
export type DrillCprResponse = {
  fundo_id:             string
  fundo_nome:           string
  data:                 string
  data_anterior:        string
  cpr_total_d1:         number
  cpr_total_d0:         number
  cpr_total_delta:      number
  qtd_linhas_d1:        number
  qtd_linhas_d0:        number
  naturezas:            DrillCprNaturezaGroup[]
  aportes_engaiolados:  DrillCprAporteEngaiolado[]
}

function _coerceDrillCprLinha(l: DrillCprLinhaDTO): DrillCprLinha {
  return {
    ...l,
    valor_d1:    Number(l.valor_d1),
    valor_d0:    Number(l.valor_d0),
    delta_valor: Number(l.delta_valor),
  }
}

function _coerceDrillCprNatureza(n: DrillCprNaturezaGroupDTO): DrillCprNaturezaGroup {
  return {
    natureza:     n.natureza,
    label:        n.label,
    qtd_linhas:   n.qtd_linhas,
    sum_valor_d1: Number(n.sum_valor_d1),
    sum_valor_d0: Number(n.sum_valor_d0),
    sum_delta:    Number(n.sum_delta),
    top_linhas:   n.top_linhas.map(_coerceDrillCprLinha),
  }
}

function _coerceDrillCpr(r: DrillCprResponseDTO): DrillCprResponse {
  return {
    fundo_id:        r.fundo_id,
    fundo_nome:      r.fundo_nome,
    data:            r.data,
    data_anterior:   r.data_anterior,
    cpr_total_d1:    Number(r.cpr_total_d1),
    cpr_total_d0:    Number(r.cpr_total_d0),
    cpr_total_delta: Number(r.cpr_total_delta),
    qtd_linhas_d1:   r.qtd_linhas_d1,
    qtd_linhas_d0:   r.qtd_linhas_d0,
    naturezas:       r.naturezas.map(_coerceDrillCprNatureza),
    aportes_engaiolados: r.aportes_engaiolados.map((a) => ({
      descricao:    a.descricao,
      estado:       a.estado,
      valor_d1:     Number(a.valor_d1),
      valor_d0:     Number(a.valor_d0),
      delta_valor:  Number(a.delta_valor),
    })),
  }
}

// ── DRILL ORIGEM (ver origem — linhas-fonte simples, 2026-05-28) ────────────
// Drill generico das 9 linhas SEM drill rico. Lista as linhas-fonte que
// compoem o valor da linha + prova de fechamento (soma == valor_balanco).

type DrillOrigemLinhaDTO = {
  identificador: string
  descricao:     string
  detalhe:       string | null
  valor:         number | string
}
export type DrillOrigemLinha = {
  identificador: string
  descricao:     string
  detalhe:       string | null
  valor:         number
}
type DrillOrigemResponseDTO = {
  fundo_id:      string
  fundo_nome:    string
  data:          string
  linha_key:     string
  linha_label:   string
  fonte:         string
  linhas:        DrillOrigemLinhaDTO[]
  soma:          number | string
  valor_balanco: number | string
  diferenca:     number | string
  fecha:         boolean
}
export type DrillOrigemResponse = {
  fundo_id:      string
  fundo_nome:    string
  data:          string
  linha_key:     string
  linha_label:   string
  fonte:         string
  linhas:        DrillOrigemLinha[]
  soma:          number
  valor_balanco: number
  diferenca:     number
  fecha:         boolean
}
function _coerceDrillOrigem(r: DrillOrigemResponseDTO): DrillOrigemResponse {
  return {
    fundo_id:      r.fundo_id,
    fundo_nome:    r.fundo_nome,
    data:          r.data,
    linha_key:     r.linha_key,
    linha_label:   r.linha_label,
    fonte:         r.fonte,
    linhas:        r.linhas.map((l) => ({
      identificador: l.identificador,
      descricao:     l.descricao,
      detalhe:       l.detalhe,
      valor:         Number(l.valor),
    })),
    soma:          Number(r.soma),
    valor_balanco: Number(r.valor_balanco),
    diferenca:     Number(r.diferenca),
    fecha:         r.fecha,
  }
}

// ── Agente IA · analista de variacao da Cota Sub Jr ───────────────────

// Espelha AnalysisVariacaoCotaResponse (Pydantic) + AgenteVariacaoRunMetadata
// do backend. Coercao Decimal -> number igual aos drills.

export type AgenteSanityCheck = {
  passou:             boolean
  residuo_brl:        number
  pl_deduzido_delta:  number
  pl_fonte_delta:     number
  diagnostico:        string
}

export type AgenteCategoriaDelta = {
  key:             string
  label:           string
  tipo:            "ativo" | "passivo"
  d1:              number
  d0:              number
  delta:           number
  rank_magnitude:  number
}

export type AgentePapelMencionado = {
  seu_numero:       string
  numero_documento: string
  cedente_nome:   string
  sacado_nome:    string
  delta_brl:      number
  natureza:       string
}

export type AgenteClassificacaoPrincipal =
  | "carrego_normal"
  | "fluxo_novo_intenso"
  | "mutacao_silenciosa_pura"
  | "padrao_abatimento_offrecord"
  | "constituicao_pdd"
  | "reversao_pdd"
  | "aporte_engaiolado"
  | "evento_pontual_explicado"
  | "evento_pontual_sem_explicacao"
  | "outro"

export type AgenteExplicacaoCategoria = {
  categoria_key:            string
  narrativa:                string
  papeis_mencionados:       AgentePapelMencionado[]
  classificacao_principal:  AgenteClassificacaoPrincipal
  confianca:                number
}

export type AgenteSinalAlerta = {
  severidade:  "info" | "atencao" | "critico"
  tipo:
    | "cedente_reincidente"
    | "sacado_problematico"
    | "concentracao_categoria"
    | "mutacao_silenciosa_material"
    | "residuo_alto"
    | "outro"
  entidade:    string
  descricao:   string
  evidencia:   string
}

export type AgenteSugestaoAcao = {
  prioridade:  "alta" | "media" | "baixa"
  acao:        string
  detalhe:     string
}

export type AgenteAnaliseVariacao = {
  fundo_nome:           string
  data:                 string
  data_anterior:        string
  nivel_1_sanity:       AgenteSanityCheck
  nivel_2_decomposicao: AgenteCategoriaDelta[]
  nivel_3_explicacoes:  AgenteExplicacaoCategoria[]
  sinais_alerta:        AgenteSinalAlerta[]
  sugestoes_acao:       AgenteSugestaoAcao[]
  sumario_executivo:    string
}

export type AgenteVariacaoRunMetadata = {
  analysis_run_id:        string
  audit_version:          string
  model_used:             string
  from_cache:             boolean
  cache_age_seconds:      number
  tokens_input:           number
  tokens_output:          number
  tokens_cache_read:      number
  tokens_cache_creation:  number
  cost_brl_estimated:     number
  duration_ms:            number
}

export type AgenteVariacaoRunResponse = {
  metadata:  AgenteVariacaoRunMetadata
  analise:   AgenteAnaliseVariacao
}

export type AgenteVariacaoRunResponseDTO = {
  metadata: {
    analysis_run_id:        string
    audit_version:          string
    model_used:             string
    from_cache:             boolean
    cache_age_seconds:      number
    tokens_input:           number
    tokens_output:          number
    tokens_cache_read:      number
    tokens_cache_creation:  number
    cost_brl_estimated:     number | string
    duration_ms:            number
  }
  analise: AgenteAnaliseVariacao  // Pydantic ja serializa numeros direto
}

export function coerceAgenteVariacaoRun(r: AgenteVariacaoRunResponseDTO): AgenteVariacaoRunResponse {
  return {
    metadata: {
      ...r.metadata,
      cost_brl_estimated: Number(r.metadata.cost_brl_estimated),
    },
    analise: r.analise,
  }
}


// ─────────────────────────────────────────────────────────────────────────────
// Controladoria · Evolucao Patrimonial — serie temporal do PL do passivo.
// Backend serializa float (display), entao consumimos `number` direto (sem
// coerce string->number). Espelha
// backend/app/modules/controladoria/schemas/evolucao_patrimonial.py
// ─────────────────────────────────────────────────────────────────────────────

export type EvolucaoClasse = "sub" | "mez" | "sr"
export type EvolucaoGranularidade = "diaria" | "mensal"

export type EvolucaoSeriePontoClasse = {
  classe:              EvolucaoClasse
  patrimonio:          number
  quantidade:          number
  valor_cota:          number
  variacao_diaria_pct: number
  variacao_mensal_pct: number
  entradas:            number
  saidas:              number
  captacao_liquida:    number
  pct_cdi:             number | null
  rentab_real_cdi_pct: number | null
}

export type EvolucaoSeriePonto = {
  data:            string  // YYYY-MM-DD
  pl_total:        number
  cdi_retorno_pct: number | null
  classes:         EvolucaoSeriePontoClasse[]
}

export type EvolucaoClasseInfo = {
  classe:                 EvolucaoClasse
  label:                  string
  carteira_cliente_nome:  string
  primeiro_dia:           string
  ultimo_dia:             string
}

export type EvolucaoResumoClasse = {
  classe:                   EvolucaoClasse
  label:                    string
  pl_inicio:                number
  pl_atual:                 number
  valor_cota_inicio:        number
  valor_cota_atual:         number
  rentab_periodo_pct:       number | null
  captacao_liquida_periodo: number
  pct_cdi_ultimo:           number | null
  participacao_pct:         number | null
}

export type EvolucaoKpis = {
  pl_total_inicio:         number
  pl_total_atual:          number
  pl_total_delta_pct:      number | null
  captacao_liquida_periodo: number
  subordinacao_pct:        number | null
  rentab_sub_periodo_pct:  number | null
  pct_cdi_sub_ultimo:      number | null
}

export type EvolucaoProveniencia = {
  fonte:          string
  relatorio:      string
  atualizado_em:  string | null
  gaps_ignorados: number
}

export type EvolucaoPatrimonialResponse = {
  fundo_id:            string
  fundo_nome:          string
  periodo_inicio:      string
  periodo_fim:         string
  granularidade:       EvolucaoGranularidade
  classes_disponiveis: EvolucaoClasseInfo[]
  serie:               EvolucaoSeriePonto[]
  resumo_por_classe:   EvolucaoResumoClasse[]
  kpis:                EvolucaoKpis
  proveniencia:        EvolucaoProveniencia
}

export const controladoria = {
  evolucaoPatrimonialSerie: async (opts: {
    fundoId:        string
    periodoInicio?: string  // YYYY-MM-DD
    periodoFim?:    string  // YYYY-MM-DD
    granularidade?: EvolucaoGranularidade
    classes?:       EvolucaoClasse[]
  }): Promise<EvolucaoPatrimonialResponse> => {
    const params = new URLSearchParams({ fundo_id: opts.fundoId })
    if (opts.periodoInicio) params.set("periodo_inicio", opts.periodoInicio)
    if (opts.periodoFim) params.set("periodo_fim", opts.periodoFim)
    if (opts.granularidade) params.set("granularidade", opts.granularidade)
    for (const c of opts.classes ?? []) params.append("classes", c)
    // float no backend -> number direto, sem coerce.
    return apiClient.get<EvolucaoPatrimonialResponse>(
      `/controladoria/evolucao-patrimonial/serie?${params.toString()}`,
    )
  },

  cotaSubDatasDisponiveis: async (
    fundoId: string,
  ): Promise<string[]> => {
    // Lista ISO desc de datas em que a QiTech publicou snapshot da UA.
    // Consumido pelo Calendar para impedir selecao de dias sem dados
    // (fim de semana, feriado, falha ETL).
    const params = new URLSearchParams({ fundo_id: fundoId })
    return apiClient.get<string[]>(
      `/controladoria/cota-sub/datas-disponiveis?${params.toString()}`,
    )
  },

  cotaSubBalancoEstrutural: async (
    fundoId: string,
    data: string,           // YYYY-MM-DD
    dataAnterior?: string,  // YYYY-MM-DD opcional (override de D-1)
  ): Promise<BalancoEstruturalResponse> => {
    const params = new URLSearchParams({ fundo_id: fundoId, data })
    if (dataAnterior) params.set("data_anterior", dataAnterior)
    const raw = await apiClient.get<BalancoEstruturalResponseDTO>(
      `/controladoria/cota-sub/balanco-estrutural?${params.toString()}`,
    )
    return _coerceBalancoEstrutural(raw)
  },

  cotaSubVariacoesDia: async (
    fundoId: string,
    data: string,
    dataAnterior?: string,
  ): Promise<VariacoesDiaResponse> => {
    const params = new URLSearchParams({ fundo_id: fundoId, data })
    if (dataAnterior) params.set("data_anterior", dataAnterior)
    const raw = await apiClient.get<VariacoesDiaResponseRaw>(
      `/controladoria/cota-sub/variacoes-dia?${params.toString()}`,
    )
    return {
      ...raw,
      apropriacoes:       raw.apropriacoes.map(_coerceVariacaoItem),
      apropriacoes_total: Number(raw.apropriacoes_total),
      pagamentos:         raw.pagamentos.map(_coerceVariacaoItem),
      pagamentos_total:   Number(raw.pagamentos_total),
      anomalias:          raw.anomalias.map(_coerceVariacaoItem),
      conferencia: {
        delta_passivo_contabil: Number(raw.conferencia.delta_passivo_contabil),
        soma_apropriacoes:      Number(raw.conferencia.soma_apropriacoes),
        divergencia:            Number(raw.conferencia.divergencia),
        ok:                     raw.conferencia.ok,
      },
    }
  },

  // ── Drills DC / PDD / CPR (F2 do redesign, 2026-05-23) ────────────────
  cotaSubDrillDc: async (
    fundoId: string,
    data: string,
    dataAnterior?: string,
  ): Promise<DrillDcResponse> => {
    const params = new URLSearchParams({ fundo_id: fundoId, data })
    if (dataAnterior) params.set("data_anterior", dataAnterior)
    const raw = await apiClient.get<DrillDcResponseDTO>(
      `/controladoria/cota-sub/drill/dc?${params.toString()}`,
    )
    return _coerceDrillDc(raw)
  },

  cotaSubDrillPdd: async (
    fundoId: string,
    data: string,
    opts?: {
      dataAnterior?:  string
      thresholdBrl?:  number
      topN?:          number
    },
  ): Promise<DrillPddResponse> => {
    const params = new URLSearchParams({ fundo_id: fundoId, data })
    if (opts?.dataAnterior) params.set("data_anterior", opts.dataAnterior)
    if (opts?.thresholdBrl !== undefined) params.set("threshold_brl", String(opts.thresholdBrl))
    if (opts?.topN !== undefined) params.set("top_n", String(opts.topN))
    const raw = await apiClient.get<DrillPddResponseDTO>(
      `/controladoria/cota-sub/drill/pdd?${params.toString()}`,
    )
    return _coerceDrillPdd(raw)
  },

  cotaSubDrillCpr: async (
    fundoId: string,
    data: string,
    dataAnterior?: string,
    side?: "receber" | "pagar",
  ): Promise<DrillCprResponse> => {
    const params = new URLSearchParams({ fundo_id: fundoId, data })
    if (dataAnterior) params.set("data_anterior", dataAnterior)
    if (side) params.set("side", side)
    const raw = await apiClient.get<DrillCprResponseDTO>(
      `/controladoria/cota-sub/drill/cpr?${params.toString()}`,
    )
    return _coerceDrillCpr(raw)
  },

  cotaSubDrillOrigem: async (
    fundoId: string,
    data: string,
    linha: string,
  ): Promise<DrillOrigemResponse> => {
    const params = new URLSearchParams({ fundo_id: fundoId, data, linha })
    const raw = await apiClient.get<DrillOrigemResponseDTO>(
      `/controladoria/cota-sub/drill/origem?${params.toString()}`,
    )
    return _coerceDrillOrigem(raw)
  },

  // ── Agente IA · analista de variacao da Cota Sub Jr ─────────────────
  // POST porque invoca LLM (side effect — grava em agent_analysis_run).
  // Cache automatico no backend: 2a chamada com mesmos params retorna
  // em <1s, custo R$ 0.
  cotaSubAgenteAnalistaVariacaoRun: async (
    fundoId: string,
    data: string,
  ): Promise<AgenteVariacaoRunResponse> => {
    const params = new URLSearchParams({ fundo_id: fundoId, data })
    const raw = await apiClient.post<AgenteVariacaoRunResponseDTO>(
      `/controladoria/cota-sub/agente/analista-variacao/run?${params.toString()}`,
      undefined,
    )
    return coerceAgenteVariacaoRun(raw)
  },

  // ── DRE — Demonstrativo do Resultado do Exercicio ─────────────────────
  // Le silver wh_dre_mensal (populado pelo ETL Bitfin v2.0.0 + classifier).
  // fundo_id e Integer (Bitfin.UnidadeAdministrativa.Id), NAO UUID — nao
  // confundir com o fundoId UUID da cota-sub (QiTech).

  dreCompetenciasDisponiveis: async (filters: DreBaseFilters = {}): Promise<string[]> => {
    const params = _dreParams(filters)
    return apiClient.get<string[]>(
      `/controladoria/dre/competencias-disponiveis?${params.toString()}`,
    )
  },

  drePivot: async (filters: DrePivotFilters): Promise<DrePivotResponse> => {
    const params = _dreParams(filters)
    params.set("competencia_de", filters.competenciaDe)
    params.set("competencia_ate", filters.competenciaAte)
    const raw = await apiClient.get<DrePivotResponseRaw>(
      `/controladoria/dre/pivot?${params.toString()}`,
    )
    return _coerceDrePivot(raw)
  },

  dreDrillFornecedores: async (
    filters: DreDrillFornecedoresFilters,
  ): Promise<DreFornecedoresResponse> => {
    const params = _dreParams(filters)
    params.set("grupo_dre", filters.grupoDre)
    params.set("competencia_de", filters.competenciaDe)
    params.set("competencia_ate", filters.competenciaAte)
    if (filters.subgrupo) params.set("subgrupo", filters.subgrupo)
    if (filters.descricao) params.set("descricao", filters.descricao)
    if (filters.top) params.set("top", String(filters.top))
    const raw = await apiClient.get<DreFornecedoresResponseRaw>(
      `/controladoria/dre/drill/fornecedores?${params.toString()}`,
    )
    return _coerceDreFornecedores(raw)
  },
}

// ── DRE — Tipos + helpers ──────────────────────────────────────────────────

export type DreBaseFilters = {
  fundoId?:   number
  produtoId?: number
  fonte?:     string
}

export type DrePivotFilters = DreBaseFilters & {
  competenciaDe:  string  // YYYY-MM-DD (1o dia do mes)
  competenciaAte: string  // YYYY-MM-DD (1o dia do mes)
}

export type DreDrillFornecedoresFilters = DrePivotFilters & {
  grupoDre:   string
  subgrupo?:  string
  descricao?: string
  top?:       number
}

function _dreParams(f: DreBaseFilters): URLSearchParams {
  const params = new URLSearchParams()
  if (f.fundoId !== undefined)   params.set("fundo_id", String(f.fundoId))
  if (f.produtoId !== undefined) params.set("produto_id", String(f.produtoId))
  if (f.fonte)                   params.set("fonte", f.fonte)
  return params
}

// Backend: Pydantic Decimal -> JSON string. Quantidade vem como number int.
type DreCelulaRaw = {
  competencia: string
  receita:     number | string
  custo:       number | string
  resultado:   number | string
  quantidade:  number
}

export type DreCelula = {
  competencia: string  // YYYY-MM-DD
  receita:     number
  custo:       number
  resultado:   number
  quantidade:  number
}

type DreLinhaTotaisRaw = {
  receita:    number | string
  custo:      number | string
  resultado:  number | string
  quantidade: number
}

export type DreLinhaTotais = {
  receita:    number
  custo:      number
  resultado:  number
  quantidade: number
}

type DreFornecedorRaw = {
  fornecedor:           string | null
  fornecedor_documento: string | null
  valores:              DreCelulaRaw[]
  totais:               DreLinhaTotaisRaw
}

export type DreFornecedorNode = {
  fornecedor:          string | null
  fornecedorDocumento: string | null
  valores:             DreCelula[]
  totais:              DreLinhaTotais
}

type DreDescricaoRaw = {
  descricao:    string
  fornecedores: DreFornecedorRaw[]
  valores:      DreCelulaRaw[]
  totais:       DreLinhaTotaisRaw
}

export type DreDescricao = {
  descricao:    string
  fornecedores: DreFornecedorNode[]
  valores:      DreCelula[]
  totais:       DreLinhaTotais
}

type DreSubgrupoRaw = {
  ordem_grupo: number
  subgrupo:    string
  descricoes:  DreDescricaoRaw[]
  valores:     DreCelulaRaw[]
  totais:      DreLinhaTotaisRaw
}

export type DreSubgrupo = {
  ordemGrupo: number
  subgrupo:   string
  descricoes: DreDescricao[]
  valores:    DreCelula[]
  totais:     DreLinhaTotais
}

type DreGrupoRaw = {
  grupo_dre:  string
  subgrupos:  DreSubgrupoRaw[]
  valores:    DreCelulaRaw[]
  totais:     DreLinhaTotaisRaw
}

export type DreGrupo = {
  grupoDre:  string
  subgrupos: DreSubgrupo[]
  valores:   DreCelula[]
  totais:    DreLinhaTotais
}

type DrePivotResponseRaw = {
  competencias:   string[]
  grupos:         DreGrupoRaw[]
  valores_total:  DreCelulaRaw[]
  totais:         DreLinhaTotaisRaw
}

export type DrePivotResponse = {
  competencias:  string[]
  grupos:        DreGrupo[]
  valoresTotal:  DreCelula[]
  totais:        DreLinhaTotais
}

type DreFornecedorRowRaw = {
  fornecedor:           string | null
  fornecedor_documento: string | null
  receita:              number | string
  custo:                number | string
  resultado:            number | string
  quantidade:           number
}

export type DreFornecedorRow = {
  fornecedor:          string | null
  fornecedorDocumento: string | null
  receita:             number
  custo:               number
  resultado:           number
  quantidade:          number
}

type DreFornecedoresResponseRaw = {
  grupo_dre:           string
  subgrupo:            string | null
  descricao:           string | null
  competencia_de:      string
  competencia_ate:     string
  fornecedores:        DreFornecedorRowRaw[]
  total_fornecedores:  number
}

export type DreFornecedoresResponse = {
  grupoDre:           string
  subgrupo:           string | null
  descricao:          string | null
  competenciaDe:      string
  competenciaAte:     string
  fornecedores:       DreFornecedorRow[]
  totalFornecedores:  number
}

function _coerceDreCelula(r: DreCelulaRaw): DreCelula {
  return {
    competencia: r.competencia,
    receita:     Number(r.receita),
    custo:       Number(r.custo),
    resultado:   Number(r.resultado),
    quantidade:  r.quantidade,
  }
}

function _coerceDreTotais(r: DreLinhaTotaisRaw): DreLinhaTotais {
  return {
    receita:    Number(r.receita),
    custo:      Number(r.custo),
    resultado:  Number(r.resultado),
    quantidade: r.quantidade,
  }
}

function _coerceDreFornecedor(r: DreFornecedorRaw): DreFornecedorNode {
  return {
    fornecedor:          r.fornecedor,
    fornecedorDocumento: r.fornecedor_documento,
    valores:             r.valores.map(_coerceDreCelula),
    totais:              _coerceDreTotais(r.totais),
  }
}

function _coerceDreDescricao(r: DreDescricaoRaw): DreDescricao {
  return {
    descricao:    r.descricao,
    fornecedores: r.fornecedores.map(_coerceDreFornecedor),
    valores:      r.valores.map(_coerceDreCelula),
    totais:       _coerceDreTotais(r.totais),
  }
}

function _coerceDreSubgrupo(r: DreSubgrupoRaw): DreSubgrupo {
  return {
    ordemGrupo: r.ordem_grupo,
    subgrupo:   r.subgrupo,
    descricoes: r.descricoes.map(_coerceDreDescricao),
    valores:    r.valores.map(_coerceDreCelula),
    totais:     _coerceDreTotais(r.totais),
  }
}

function _coerceDreGrupo(r: DreGrupoRaw): DreGrupo {
  return {
    grupoDre:  r.grupo_dre,
    subgrupos: r.subgrupos.map(_coerceDreSubgrupo),
    valores:   r.valores.map(_coerceDreCelula),
    totais:    _coerceDreTotais(r.totais),
  }
}

function _coerceDrePivot(r: DrePivotResponseRaw): DrePivotResponse {
  return {
    competencias: r.competencias,
    grupos:       r.grupos.map(_coerceDreGrupo),
    valoresTotal: r.valores_total.map(_coerceDreCelula),
    totais:       _coerceDreTotais(r.totais),
  }
}

function _coerceDreFornecedores(r: DreFornecedoresResponseRaw): DreFornecedoresResponse {
  return {
    grupoDre:           r.grupo_dre,
    subgrupo:           r.subgrupo,
    descricao:          r.descricao,
    competenciaDe:      r.competencia_de,
    competenciaAte:     r.competencia_ate,
    fornecedores: r.fornecedores.map((f) => ({
      fornecedor:          f.fornecedor,
      fornecedorDocumento: f.fornecedor_documento,
      receita:             Number(f.receita),
      custo:               Number(f.custo),
      resultado:           Number(f.resultado),
      quantidade:          f.quantidade,
    })),
    totalFornecedores: r.total_fornecedores,
  }
}

// ── Variacoes do Dia (auditoria de movimentos) ─────────────────────────────

export type VariacaoItem = {
  cosif:     string | null
  label:     string
  historico: string | null
  descricao: string | null
  valor:     number
}

type VariacaoItemRaw = {
  cosif:     string | null
  label:     string
  historico: string | null
  descricao: string | null
  valor:     number | string
}

export type ConferenciaVariacao = {
  delta_passivo_contabil: number
  soma_apropriacoes:      number
  divergencia:            number
  ok:                     boolean
}

type ConferenciaVariacaoRaw = {
  delta_passivo_contabil: number | string
  soma_apropriacoes:      number | string
  divergencia:            number | string
  ok:                     boolean
}

export type VariacoesDiaResponse = {
  fundo_id:           string
  data:               string
  data_anterior:      string
  apropriacoes:       VariacaoItem[]
  apropriacoes_total: number
  pagamentos:         VariacaoItem[]
  pagamentos_total:   number
  anomalias:          VariacaoItem[]
  conferencia:        ConferenciaVariacao
}

type VariacoesDiaResponseRaw = {
  fundo_id:           string
  data:               string
  data_anterior:      string
  apropriacoes:       VariacaoItemRaw[]
  apropriacoes_total: number | string
  pagamentos:         VariacaoItemRaw[]
  pagamentos_total:   number | string
  anomalias:          VariacaoItemRaw[]
  conferencia:        ConferenciaVariacaoRaw
}

function _coerceVariacaoItem(r: VariacaoItemRaw): VariacaoItem {
  return {
    cosif:     r.cosif ?? null,
    label:     r.label,
    historico: r.historico ?? null,
    descricao: r.descricao ?? null,
    valor:     Number(r.valor),
  }
}
