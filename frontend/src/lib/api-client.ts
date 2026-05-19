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
}

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

export type CoverageDay = {
  data: string // ISO date
  status: CoverageStatus
  http_status: number | null
  completeness: Completeness | null
  // Estado de tolerância (2026-05-15) — null quando não aplicável
  // (dia OK/PARTIAL/WEEKEND/HOLIDAY/etc).
  tolerance_state: PublicationState | null
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

export type PlCategoriaKey =
  | "compromissada"
  | "mezanino"
  | "senior"
  | "titulos_publicos"
  | "fundos_di"
  | "dc"
  | "op_estruturadas"
  | "outros_ativos"
  | "pdd"
  | "cpr"
  | "tesouraria"

export type PlCategoria = {
  key:    PlCategoriaKey
  label:  string
  d1:     number
  d0:     number
  delta:  number
  source: string
}

export type DecomposicaoSinal = "ganho" | "prejuizo" | "neutro"

export type DecomposicaoItem = {
  key:   string
  label: string
  valor: number
  sinal: DecomposicaoSinal
}

export type ApropriacaoDcLinha = {
  estoque_d1:  number
  aquisicoes:  number
  liquidados:  number
  estoque_d0:  number
  apropriacao: number
}

export type ApropriacaoDc = {
  a_vencer: ApropriacaoDcLinha
  vencidos: ApropriacaoDcLinha
  total:    number
}

export type CprMovimentoItem = { descricao: string; valor: number }

export type CprDetalhado = {
  receber_d1: CprMovimentoItem[]
  receber_d0: CprMovimentoItem[]
  pagar_d1:   CprMovimentoItem[]
  pagar_d0:   CprMovimentoItem[]
  total_d1:   number
  total_d0:   number
  variacao:   number
}

/**
 * Driver canonico da Cota Sub (Fase 3b do refactor de proveniencia transversal,
 * 2026-05-18). Cada driver e uma decomposicao parcial do ΔPL Sub no metodo
 * do gestor REALINVEST. Σ drivers (excluindo indeterminados) ≈ ΔPL_Sub_MEC.
 *
 * Espelha backend `cota_sub_drivers.compute.DriverResult` +
 * `schemas/cota_sub.py::DriverResultOut`.
 */
export type SaldoTesourariaEvidencia = {
  /** "wh_saldo_tesouraria" | "wh_saldo_conta_corrente". */
  fonte:        string
  /** Nome da conta (ex.: "Saldo em Tesouraria", "CC - BRADESCO"). */
  descricao:    string
  /** Codigo da conta corrente (BRADESCO, SOCOPA) quando aplicavel. */
  codigo:       string | null
  valor_d_prev: number
  valor_d0:     number
  /** valor_d0 - valor_d_prev. */
  delta:        number
}

export type ApropriacaoDcEvidencia = {
  /** Ex.: "Estoque a vencer", "Aquisições do dia". */
  label:        string
  /** wh_estoque_recebivel | wh_aquisicao_recebivel | wh_liquidacao_recebivel. */
  fonte:        string
  bloco:        "a_vencer" | "vencidos" | "aquisicoes" | "liquidados"
  /** Estoque em D-1 (só para 'a_vencer'/'vencidos'). */
  valor_d_prev: number | null
  /** Estoque em D0 (só para 'a_vencer'/'vencidos'). */
  valor_d0:     number | null
  /** Valor que entra na fórmula (com sinal coerente: ΔEstoque ou -Aq/-Liq_neg). */
  valor_brl:    number
}

export type DriverResultOut = {
  metric_global_id:       string  // ex.: "controladoria.cota_sub.driver.pdd"
  label:                  string
  formula_description:    string
  valor_brl:              number  // impacto liquido no PL Sub
  valor_d_prev:           number | null
  valor_d0:               number | null
  endpoints_required:     string[]
  indeterminado_por_dado: boolean
  motivo_indeterminado:   string | null
  endpoints_unavailable:  string[]
  // Evidencias especializadas por driver (Fase 4b, 2026-05-18). Cada driver
  // popula 0-1 campo; demais ficam vazios. Frontend renderiza condicional
  // ao tipo de evidencia presente. Quando o numero crescer, refactor pra
  // discriminated union (kind="pdd"|"mtm"|...).
  pdd_evidencias:                 PddEvidencia[]                 // driver PDD
  mtm_evidencias:                 MtmEvidencia[]                 // driver Titulos Publicos
  cpr_evidencias:                 EvidenciaCprLinha[]            // driver Apropriacao Despesas
  remuneracao_evidencias:         RemuneracaoSrMezEvidencia[]    // drivers Senior / Mezanino
  /** Apropriação DC: INFORMACIONAL (sub-seção "Atividade do dia", não compõe valor_brl). */
  movimento_carteira_evidencias:  MovimentoCarteiraEvidencia[]
  saldo_tesouraria_evidencias:    SaldoTesourariaEvidencia[]     // driver Tesouraria
  apropriacao_dc_evidencias:      ApropriacaoDcEvidencia[]       // driver Apropriação DC
  /**
   * Quando o granular nao pode ser computado por dado upstream ausente
   * (ex.: wh_estoque_recebivel vazio em D-1 ou D0), carrega explicacao curta.
   * Driver continua valido (vem do consolidado MEC); evidencias_*[] ficam vazias.
   * Frontend renderiza este texto no lugar da lista.
   */
  evidencias_indisponiveis_motivo: string | null
}

export type VariacaoDiariaResponse = {
  fundo_id:           string
  fundo_nome:         string
  data:               string  // ISO date
  data_anterior:      string  // ISO date
  pl_d1:              number
  pl_d0:              number
  pl_delta:           number
  pl_delta_pct:       number
  categorias:         PlCategoria[]
  decomposicao:       DecomposicaoItem[]
  decomposicao_total: number
  divergencia:        number
  apropriacao_dc:     ApropriacaoDc
  cpr_detalhado:      CprDetalhado
  // Fase 3b/4: drivers canonicos + soma + residuo do modelo. Paralelo a
  // `decomposicao` legacy — frontend migra incrementalmente.
  drivers:            DriverResultOut[]
  soma_drivers:       number
  residuo_modelo:     number
}

// ── Explainers heuristicos da variacao ───────────────────────────────────
// Backend: backend/app/modules/controladoria/services/cota_sub_explainers.py
// Doc:     backend/docs/cota-sub-explainers-heuristicos.md

export type ExplainerCategoria =
  | "pdd"
  | "mtm"
  | "aporte"
  | "movimento_cotas"
  | "diferimento"
  | "apropriacao"
  | "liquidacao"
  | "aquisicao"
  | "outros"

/**
 * 1 conta COSIF folha mapeada pro bucket — fonte contabil do delta_brl.
 * Refactor 2026-05-17: cada Explanation traz a lista de COSIFs que compoem
 * o delta_brl do bucket. Permite auditar exatamente de onde vem o impacto
 * antes mesmo de qualquer heuristica de enriquecimento.
 */
export type CosifOrigem = {
  codigo:    string
  nome:      string
  d_minus_1: number
  d_zero:    number
  delta:     number
}

export type PddEvidencia = {
  cedente_doc:              string
  cedente_nome:             string
  sacado_doc:               string
  sacado_nome:              string
  seu_numero:               string
  numero_documento:         string
  tipo_recebivel:           string
  data_vencimento_ajustada: string | null
  valor_nominal:            number
  valor_pdd_d1:             number
  valor_pdd_d0:             number
  delta_valor_pdd:          number
  faixa_pdd_d1:             string | null
  faixa_pdd_d0:             string | null
}

/** Evidencia generica de rubrica CPR — usada por Diferimento e Apropriacao. */
export type EvidenciaCprLinha = {
  descricao:           string
  historico_traduzido: string
  valor_d1:            number
  valor_d0:            number
  delta_valor:         number
}

export type PddExplanation = {
  categoria:            "pdd"
  narrative:            string
  delta_brl:            number
  evidencias_total:     number
  evidencias_mostradas: number
  outros_delta_brl:     number
  evidencias:           PddEvidencia[]
  cosif_origin?:        CosifOrigem[]
}

export type DiferimentoExplanation = {
  categoria:            "diferimento"
  narrative:            string
  delta_brl:            number
  evidencias_total:     number
  evidencias_mostradas: number
  outros_delta_brl:     number
  evidencias:           EvidenciaCprLinha[]
  cosif_origin?:        CosifOrigem[]
}

export type ApropriacaoExplanation = {
  categoria:            "apropriacao"
  narrative:            string
  delta_brl:            number
  evidencias_total:     number
  evidencias_mostradas: number
  outros_delta_brl:     number
  evidencias:           EvidenciaCprLinha[]
  cosif_origin?:        CosifOrigem[]
}

export type ClasseCotaKey = "sub_jr" | "mezanino" | "senior"

export type FluxoCaixaEvidencia = {
  tipo:           "aporte" | "resgate"
  classe:         ClasseCotaKey
  classe_label:   string
  valor_brl:      number
  delta_qtd:      number
  valor_cota_d0:  number
  /** Impacto liquido no PL Sub com sinal coerente (verde se +, vermelho se -). */
  impacto_pl_sub: number
}

export type EventoOperacionalEvidencia = {
  tipo:      "aporte_engaiolado" | "devolucao_engaiolado"
  descricao: string
  valor_brl: number
  detalhe:   string | null
}

export type FluxoCaixaExplanation = {
  categoria:            "fluxo_caixa"
  narrative:            string
  delta_brl:            number
  evidencias:           FluxoCaixaEvidencia[]
  eventos_operacionais: EventoOperacionalEvidencia[]
  cosif_origin?:        CosifOrigem[]
}

export type MovimentoCarteiraEvidencia = {
  tipo:                     "liquidado" | "adquirido"
  cedente_doc:              string
  cedente_nome:             string
  sacado_doc:               string
  sacado_nome:              string
  seu_numero:               string
  numero_documento:         string
  tipo_recebivel:           string
  valor_brl:                number
  valor_nominal:            number
  data_vencimento_ajustada: string | null
}

export type MovimentoCarteiraExplanation = {
  categoria:            "movimento_carteira"
  narrative:            string
  /**
   * Σ Δ folhas COSIF: bancos (1.1.2.*) + recebiveis (1.6.1.30.*) + transito
   * + creditos a conciliar. ANTES era sempre 0 ("informacional"); apos
   * refactor 2026-05-17 reflete o impacto contabil real do giro de carteira.
   */
  delta_brl:            number
  total_liquidado_brl:  number
  total_adquirido_brl:  number
  papeis_liquidados:    number
  papeis_adquiridos:    number
  evidencias_mostradas: number
  evidencias:           MovimentoCarteiraEvidencia[]
  cosif_origin?:        CosifOrigem[]
}

export type MtmEvidencia = {
  codigo:           string
  nome_do_papel:    string
  emitente:         string
  indexador:        string
  data_vencimento:  string | null
  quantidade:       number
  valor_d1:         number
  valor_d0:         number
  delta_valor:      number
  pu_d1:            number
  pu_d0:            number
}

/**
 * Bucket "Renda Fixa" (categoria interna ainda "mtm" pra evitar migration):
 * agrega TPF (LTN, NTN), Notas Comerciais, Cotas de fundos de RF. Inclui
 * MtM puro + ganhos/perdas de liquidacao + apropriacao de juros de RF.
 * Display label e "Renda Fixa" no frontend.
 */
export type MtmExplanation = {
  categoria:            "mtm"
  narrative:            string
  delta_brl:            number
  evidencias_total:     number
  evidencias_mostradas: number
  outros_delta_brl:     number
  evidencias:           MtmEvidencia[]
  cosif_origin?:        CosifOrigem[]
}

export type RemuneracaoSrMezEvidencia = {
  classe:         "senior" | "mezanino"
  classe_label:   string
  pl_d1:          number
  pl_d0:          number
  /** pl_d0 - pl_d1 - (entradas_d0 - saidas_d0). Positivo = classe valorizou. */
  delta_pl:       number
  /** delta_pl / pl_d1 (fracao decimal). */
  delta_pct:      number
  valor_cota_d1:  number
  valor_cota_d0:  number
  /** -delta_pl (Sub paga a remuneracao das tranches mais seniores). */
  impacto_pl_sub: number
}

export type RemuneracaoSrMezExplanation = {
  categoria:            "remuneracao_sr_mez"
  narrative:            string
  /** -(ΔPL_Sr + ΔPL_Mez) — negativo = Sub paga subordinacao. */
  delta_brl:            number
  evidencias:           RemuneracaoSrMezEvidencia[]
  cosif_origin?:        CosifOrigem[]
}

/**
 * Bucket residual — folhas COSIF que nao casaram com nenhum mapping.
 * Em regime estavel deve ser zero; quando nao for, lista folhas explicitas
 * pra adicionar em `cosif_to_bucket.py`.
 */
export type OutrosExplanation = {
  categoria:    "outros"
  narrative:    string
  delta_brl:    number
  cosif_origin: CosifOrigem[]
}

export type Explanation =
  | PddExplanation
  | DiferimentoExplanation
  | ApropriacaoExplanation
  | FluxoCaixaExplanation
  | MovimentoCarteiraExplanation
  | MtmExplanation
  | RemuneracaoSrMezExplanation
  | OutrosExplanation

export type ExplicacaoVariacaoResponse = {
  fundo_id:                  string
  data:                      string
  data_anterior:             string
  /** ΔPL Sub apurado pelo MEC (administrador). */
  delta_pl_sub:              number
  /** ΔPL Sub calculado pelo balancete COSIF (refactor 2026-05-17). */
  delta_pl_sub_contabil:     number
  /** delta_pl_sub - delta_pl_sub_contabil. Residuo MEC vs Contabil. */
  divergencia_mec_contabil:  number
  threshold_brl:             number
  top_n:                     number
  explanations:              Explanation[]
  /** Σ Δ folhas COSIF sem mapping (esperado: zero). */
  indeterminado_brl:         number
}

// Pydantic v2 serializa Decimal como string. Convertemos para number aqui pra
// manter os tipos do frontend numericos. Precisao suficiente para displays;
// se algum calculo critico precisar Decimal, troca para `decimal.js`.
function _coerceCategoria(c: PlCategoria): PlCategoria {
  return { ...c, d1: Number(c.d1), d0: Number(c.d0), delta: Number(c.delta) }
}
function _coerceDecomp(d: DecomposicaoItem): DecomposicaoItem {
  return { ...d, valor: Number(d.valor) }
}
function _coerceLinha(l: ApropriacaoDcLinha): ApropriacaoDcLinha {
  return {
    estoque_d1:  Number(l.estoque_d1),
    aquisicoes:  Number(l.aquisicoes),
    liquidados:  Number(l.liquidados),
    estoque_d0:  Number(l.estoque_d0),
    apropriacao: Number(l.apropriacao),
  }
}
function _coerceCprItem(i: CprMovimentoItem): CprMovimentoItem {
  return { ...i, valor: Number(i.valor) }
}
function _coerceSaldoTesourariaEvidencia(e: SaldoTesourariaEvidencia): SaldoTesourariaEvidencia {
  return {
    ...e,
    valor_d_prev: Number(e.valor_d_prev),
    valor_d0:     Number(e.valor_d0),
    delta:        Number(e.delta),
  }
}
function _coerceApropriacaoDcEvidencia(e: ApropriacaoDcEvidencia): ApropriacaoDcEvidencia {
  return {
    ...e,
    valor_d_prev: e.valor_d_prev === null ? null : Number(e.valor_d_prev),
    valor_d0:     e.valor_d0 === null ? null : Number(e.valor_d0),
    valor_brl:    Number(e.valor_brl),
  }
}
function _coerceDriverResultOut(d: DriverResultOut): DriverResultOut {
  return {
    ...d,
    valor_brl:                     Number(d.valor_brl),
    valor_d_prev:                  d.valor_d_prev === null ? null : Number(d.valor_d_prev),
    valor_d0:                      d.valor_d0 === null ? null : Number(d.valor_d0),
    pdd_evidencias:                d.pdd_evidencias.map(_coercePddEvidencia),
    mtm_evidencias:                d.mtm_evidencias.map(_coerceMtmEvidencia),
    cpr_evidencias:                d.cpr_evidencias.map(_coerceCprEvidencia),
    remuneracao_evidencias:        d.remuneracao_evidencias.map(_coerceRemuneracaoSrMezEvidencia),
    movimento_carteira_evidencias: d.movimento_carteira_evidencias.map(_coerceMovimentoCarteiraEvidencia),
    saldo_tesouraria_evidencias:   (d.saldo_tesouraria_evidencias ?? []).map(_coerceSaldoTesourariaEvidencia),
    apropriacao_dc_evidencias:     (d.apropriacao_dc_evidencias ?? []).map(_coerceApropriacaoDcEvidencia),
  }
}
function _coerceVariacao(r: VariacaoDiariaResponse): VariacaoDiariaResponse {
  return {
    ...r,
    pl_d1:              Number(r.pl_d1),
    pl_d0:              Number(r.pl_d0),
    pl_delta:           Number(r.pl_delta),
    pl_delta_pct:       Number(r.pl_delta_pct),
    decomposicao_total: Number(r.decomposicao_total),
    divergencia:        Number(r.divergencia),
    categorias:         r.categorias.map(_coerceCategoria),
    decomposicao:       r.decomposicao.map(_coerceDecomp),
    apropriacao_dc: {
      a_vencer: _coerceLinha(r.apropriacao_dc.a_vencer),
      vencidos: _coerceLinha(r.apropriacao_dc.vencidos),
      total:    Number(r.apropriacao_dc.total),
    },
    cpr_detalhado: {
      receber_d1: r.cpr_detalhado.receber_d1.map(_coerceCprItem),
      receber_d0: r.cpr_detalhado.receber_d0.map(_coerceCprItem),
      pagar_d1:   r.cpr_detalhado.pagar_d1.map(_coerceCprItem),
      pagar_d0:   r.cpr_detalhado.pagar_d0.map(_coerceCprItem),
      total_d1:   Number(r.cpr_detalhado.total_d1),
      total_d0:   Number(r.cpr_detalhado.total_d0),
      variacao:   Number(r.cpr_detalhado.variacao),
    },
    drivers:        r.drivers.map(_coerceDriverResultOut),
    soma_drivers:   Number(r.soma_drivers),
    residuo_modelo: Number(r.residuo_modelo),
  }
}

function _coercePddEvidencia(e: PddEvidencia): PddEvidencia {
  return {
    ...e,
    valor_nominal:   Number(e.valor_nominal),
    valor_pdd_d1:    Number(e.valor_pdd_d1),
    valor_pdd_d0:    Number(e.valor_pdd_d0),
    delta_valor_pdd: Number(e.delta_valor_pdd),
  }
}
function _coerceCprEvidencia(e: EvidenciaCprLinha): EvidenciaCprLinha {
  return {
    ...e,
    valor_d1:    Number(e.valor_d1),
    valor_d0:    Number(e.valor_d0),
    delta_valor: Number(e.delta_valor),
  }
}
function _coerceFluxoCaixaEvidencia(e: FluxoCaixaEvidencia): FluxoCaixaEvidencia {
  return {
    ...e,
    valor_brl:      Number(e.valor_brl),
    delta_qtd:      Number(e.delta_qtd),
    valor_cota_d0:  Number(e.valor_cota_d0),
    impacto_pl_sub: Number(e.impacto_pl_sub),
  }
}
function _coerceEventoOperacional(e: EventoOperacionalEvidencia): EventoOperacionalEvidencia {
  return { ...e, valor_brl: Number(e.valor_brl) }
}
function _coerceMovimentoCarteiraEvidencia(e: MovimentoCarteiraEvidencia): MovimentoCarteiraEvidencia {
  return {
    ...e,
    valor_brl:     Number(e.valor_brl),
    valor_nominal: Number(e.valor_nominal),
  }
}
function _coerceMtmEvidencia(e: MtmEvidencia): MtmEvidencia {
  return {
    ...e,
    quantidade:  Number(e.quantidade),
    valor_d1:    Number(e.valor_d1),
    valor_d0:    Number(e.valor_d0),
    delta_valor: Number(e.delta_valor),
    pu_d1:       Number(e.pu_d1),
    pu_d0:       Number(e.pu_d0),
  }
}
function _coerceRemuneracaoSrMezEvidencia(e: RemuneracaoSrMezEvidencia): RemuneracaoSrMezEvidencia {
  return {
    ...e,
    pl_d1:          Number(e.pl_d1),
    pl_d0:          Number(e.pl_d0),
    delta_pl:       Number(e.delta_pl),
    delta_pct:      Number(e.delta_pct),
    valor_cota_d1:  Number(e.valor_cota_d1),
    valor_cota_d0:  Number(e.valor_cota_d0),
    impacto_pl_sub: Number(e.impacto_pl_sub),
  }
}
function _coerceCosifOrigem(c: CosifOrigem): CosifOrigem {
  return {
    ...c,
    d_minus_1: Number(c.d_minus_1),
    d_zero:    Number(c.d_zero),
    delta:     Number(c.delta),
  }
}
function _coerceCosifOrigemList(list: CosifOrigem[] | undefined): CosifOrigem[] | undefined {
  return list ? list.map(_coerceCosifOrigem) : undefined
}
function _coerceExplanation(e: Explanation): Explanation {
  switch (e.categoria) {
    case "pdd":
      return {
        ...e,
        delta_brl:        Number(e.delta_brl),
        outros_delta_brl: Number(e.outros_delta_brl),
        evidencias:       e.evidencias.map(_coercePddEvidencia),
        cosif_origin:     _coerceCosifOrigemList(e.cosif_origin),
      }
    case "diferimento":
    case "apropriacao":
      return {
        ...e,
        delta_brl:        Number(e.delta_brl),
        outros_delta_brl: Number(e.outros_delta_brl),
        evidencias:       e.evidencias.map(_coerceCprEvidencia),
        cosif_origin:     _coerceCosifOrigemList(e.cosif_origin),
      }
    case "fluxo_caixa":
      return {
        ...e,
        delta_brl:            Number(e.delta_brl),
        evidencias:           e.evidencias.map(_coerceFluxoCaixaEvidencia),
        eventos_operacionais: e.eventos_operacionais.map(_coerceEventoOperacional),
        cosif_origin:         _coerceCosifOrigemList(e.cosif_origin),
      }
    case "movimento_carteira":
      return {
        ...e,
        delta_brl:           Number(e.delta_brl),
        total_liquidado_brl: Number(e.total_liquidado_brl),
        total_adquirido_brl: Number(e.total_adquirido_brl),
        evidencias:          e.evidencias.map(_coerceMovimentoCarteiraEvidencia),
        cosif_origin:        _coerceCosifOrigemList(e.cosif_origin),
      }
    case "mtm":
      return {
        ...e,
        delta_brl:        Number(e.delta_brl),
        outros_delta_brl: Number(e.outros_delta_brl),
        evidencias:       e.evidencias.map(_coerceMtmEvidencia),
        cosif_origin:     _coerceCosifOrigemList(e.cosif_origin),
      }
    case "remuneracao_sr_mez":
      return {
        ...e,
        delta_brl:    Number(e.delta_brl),
        evidencias:   e.evidencias.map(_coerceRemuneracaoSrMezEvidencia),
        cosif_origin: _coerceCosifOrigemList(e.cosif_origin),
      }
    case "outros":
      return {
        ...e,
        delta_brl:    Number(e.delta_brl),
        cosif_origin: e.cosif_origin.map(_coerceCosifOrigem),
      }
    default:
      return e
  }
}
function _coerceExplicacao(r: ExplicacaoVariacaoResponse): ExplicacaoVariacaoResponse {
  return {
    ...r,
    delta_pl_sub:             Number(r.delta_pl_sub),
    delta_pl_sub_contabil:    Number(r.delta_pl_sub_contabil),
    divergencia_mec_contabil: Number(r.divergencia_mec_contabil),
    threshold_brl:            Number(r.threshold_brl),
    indeterminado_brl:        Number(r.indeterminado_brl),
    explanations:             r.explanations.map(_coerceExplanation),
  }
}

// ── Balanco diario · otica Sub Jr ──────────────────────────────────────────

export type BalanceRowType = "section" | "line" | "subtotal" | "total"

export type BalanceRowDTO = {
  id:         string
  type:       BalanceRowType
  label:      string
  cosif?:     string | null
  descricao?: string | null
  source?:    string | null
  d1?:        number | string | null  // Pydantic Decimal -> string; coerce abaixo
  d0?:        number | string | null
  delta?:     number | string | null
  subRows?:   BalanceRowDTO[] | null
}

export type BalanceRow = {
  id:         string
  type:       BalanceRowType
  label:      string
  cosif?:     string | null
  descricao?: string | null
  source?:    string | null
  d1:         number | null
  d0:         number | null
  delta:      number | null
  subRows?:   BalanceRow[]
}

export type BalancoResponse = {
  fundo_id:      string
  fundo_nome:    string
  data:          string  // ISO date
  data_anterior: string  // ISO date
  rows:          BalanceRow[]
}

type BalancoResponseRaw = {
  fundo_id:      string
  fundo_nome:    string
  data:          string
  data_anterior: string
  rows:          BalanceRowDTO[]
}

function _coerceBalanceVal(v: number | string | null | undefined): number | null {
  if (v === null || v === undefined) return null
  return Number(v)
}

function _coerceBalanceRow(r: BalanceRowDTO): BalanceRow {
  return {
    id:        r.id,
    type:      r.type,
    label:     r.label,
    cosif:     r.cosif ?? null,
    descricao: r.descricao ?? null,
    source:    r.source ?? null,
    d1:        _coerceBalanceVal(r.d1),
    d0:        _coerceBalanceVal(r.d0),
    delta:     _coerceBalanceVal(r.delta),
    subRows:   r.subRows ? r.subRows.map(_coerceBalanceRow) : undefined,
  }
}

// ── Balancete Patrimonial Diario COSIF (Fase 1 Cota Sub) ───────────────────
//
// Modelo agnostico multi-tenant — backend devolve arvore COSIF plana
// (`nodes`) que o frontend reconstroi via `parent_codigo`. Decimals chegam
// como string no JSON; coercao para number e feita aqui no client.

export type CosifSource = "override" | "rule" | "mixed" | "pendente" | string

export type CosifNode = {
  codigo:         string | null  // null = pendente (nao classificado)
  nome:           string
  natureza:       "D" | "C" | "?"
  nivel:          number  // 1-6 na arvore COSIF; 0 quando pendente
  grupo:          number  // 1=Ativo, 4=Passivo, 6=PL, 8=Despesa; 0 quando pendente
  parent_codigo:  string | null
  d_minus_1:      number
  d_zero:         number
  delta:          number
  delta_pct:      number
  rows_classified: number
  cosif_source:   CosifSource
}

export type ClasseBreakdown = {
  classe:    "senior" | "mezanino" | "subordinado" | "compensacao" | "aporte" | string
  d_minus_1: number
  d_zero:    number
  delta:     number
}

export type Reconciliacao = {
  pl_total_d1:                number
  pl_total_d0:                number
  delta_pl_total:             number
  cotas_sr_emitidas_d1:       number  // modulo (positivo)
  cotas_sr_emitidas_d0:       number
  delta_cotas_sr:             number
  cotas_mez_emitidas_d1:      number
  cotas_mez_emitidas_d0:      number
  delta_cotas_mez:            number
  pl_cota_sub_d1:             number
  pl_cota_sub_d0:             number
  delta_pl_cota_sub_real:     number
  delta_pl_cota_sub_esperado: number
  residuo:                    number  // real - esperado (deve ~0)
  delta_pct_sobre_d1:         number
}

export type PendenteEntry = {
  silver_origin: string
  identificador: string
  valor:         number
}

export type Cobertura = {
  total_rows:       number
  rows_por_source:  Record<string, number>
  valor_por_source: Record<string, number>
  top_pendentes:    PendenteEntry[]
}

export type DataQuality = {
  silvers_d1:           Record<string, number>
  silvers_d0:           Record<string, number>
  silvers_divergentes:  string[]
  comparable:           boolean
  reason:               string | null
}

export type BalanceteResponse = {
  fundo_id:                   string
  data_d_zero:                string  // ISO date
  data_d_minus_1:             string
  nodes:                      CosifNode[]
  classe_breakdown_por_cosif: Record<string, ClasseBreakdown[]>
  rows_por_cosif:             Record<string, CosifRowDiff[]>
  reconciliacao:              Reconciliacao
  cobertura:                  Cobertura
  data_quality:               DataQuality
}

// Raw shapes — Decimal serializado como string pelo Pydantic
type CosifNodeRaw = Omit<CosifNode, "d_minus_1" | "d_zero" | "delta" | "delta_pct"> & {
  d_minus_1: number | string
  d_zero:    number | string
  delta:     number | string
  delta_pct: number | string
}

type ClasseBreakdownRaw = Omit<ClasseBreakdown, "d_minus_1" | "d_zero" | "delta"> & {
  d_minus_1: number | string
  d_zero:    number | string
  delta:     number | string
}

type ReconciliacaoRaw = {
  [K in keyof Reconciliacao]: number | string
}

type PendenteEntryRaw = {
  silver_origin: string
  identificador: string
  valor:         number | string
}

type CoberturaRaw = {
  total_rows:       number
  rows_por_source:  Record<string, number>
  valor_por_source: Record<string, number | string>
  top_pendentes:    PendenteEntryRaw[]
}

type BalanceteResponseRaw = {
  fundo_id:                   string
  data_d_zero:                string
  data_d_minus_1:             string
  nodes:                      CosifNodeRaw[]
  classe_breakdown_por_cosif: Record<string, ClasseBreakdownRaw[]>
  rows_por_cosif:             Record<string, CosifRowDiffRaw[]>
  reconciliacao:              ReconciliacaoRaw
  cobertura:                  CoberturaRaw
  data_quality:               DataQuality  // ja vem como JSON simples (sem Decimal)
}

function _coerceCosifNode(n: CosifNodeRaw): CosifNode {
  return {
    ...n,
    d_minus_1: Number(n.d_minus_1),
    d_zero:    Number(n.d_zero),
    delta:     Number(n.delta),
    delta_pct: Number(n.delta_pct),
  }
}

function _coerceClasseBreakdown(b: ClasseBreakdownRaw): ClasseBreakdown {
  return {
    classe:    b.classe,
    d_minus_1: Number(b.d_minus_1),
    d_zero:    Number(b.d_zero),
    delta:     Number(b.delta),
  }
}

function _coerceReconciliacao(r: ReconciliacaoRaw): Reconciliacao {
  const out: Partial<Reconciliacao> = {}
  for (const k of Object.keys(r) as (keyof Reconciliacao)[]) {
    out[k] = Number(r[k]) as never
  }
  return out as Reconciliacao
}

function _coerceCobertura(c: CoberturaRaw): Cobertura {
  const valor: Record<string, number> = {}
  for (const [k, v] of Object.entries(c.valor_por_source)) valor[k] = Number(v)
  return {
    total_rows:       c.total_rows,
    rows_por_source:  c.rows_por_source,
    valor_por_source: valor,
    top_pendentes:    c.top_pendentes.map((p) => ({
      silver_origin: p.silver_origin,
      identificador: p.identificador,
      valor:         Number(p.valor),
    })),
  }
}

function _coerceBalanceteResponse(r: BalanceteResponseRaw): BalanceteResponse {
  const breakdown: Record<string, ClasseBreakdown[]> = {}
  for (const [k, v] of Object.entries(r.classe_breakdown_por_cosif)) {
    breakdown[k] = v.map(_coerceClasseBreakdown)
  }
  const rowsPorCosif: Record<string, CosifRowDiff[]> = {}
  for (const [k, v] of Object.entries(r.rows_por_cosif)) {
    rowsPorCosif[k] = v.map(_coerceCosifRowDiff)
  }
  return {
    fundo_id:                   r.fundo_id,
    data_d_zero:                r.data_d_zero,
    data_d_minus_1:             r.data_d_minus_1,
    nodes:                      r.nodes.map(_coerceCosifNode),
    classe_breakdown_por_cosif: breakdown,
    rows_por_cosif:             rowsPorCosif,
    reconciliacao:              _coerceReconciliacao(r.reconciliacao),
    cobertura:                  _coerceCobertura(r.cobertura),
    data_quality:               r.data_quality,
  }
}

// ── Drill-down de rows silver por conta COSIF (diff D-1 vs D0) ─────────────

export type CosifRowStatus = "novo" | "removido" | "alterado" | "inalterado"

export type CosifRowDiff = {
  silver_origin:         string
  codigo:                string | null
  nome:                  string
  valor_d_minus_1:       number
  valor_d_zero:          number
  delta:                 number
  quantidade_d_minus_1:  number | null
  quantidade_d_zero:     number | null
  indexador:             string | null
  cosif_source:          CosifSource
  status:                CosifRowStatus
  /** Emitente (renda fixa) ou instituicao gestora (cota fundo). */
  contraparte:           string | null
}

export type CosifRowsResponse = {
  fundo_id:               string
  data_d_zero:            string  // ISO date
  data_d_minus_1:         string
  cosif_codigo:           string
  cosif_nome:             string
  total_valor_d_minus_1:  number
  total_valor_d_zero:     number
  total_delta:            number
  rows:                   CosifRowDiff[]
}

type CosifRowDiffRaw = Omit<
  CosifRowDiff,
  "valor_d_minus_1" | "valor_d_zero" | "delta" | "quantidade_d_minus_1" | "quantidade_d_zero"
> & {
  valor_d_minus_1:      number | string
  valor_d_zero:         number | string
  delta:                number | string
  quantidade_d_minus_1: number | string | null
  quantidade_d_zero:    number | string | null
}

type CosifRowsResponseRaw = {
  fundo_id:               string
  data_d_zero:            string
  data_d_minus_1:         string
  cosif_codigo:           string
  cosif_nome:             string
  total_valor_d_minus_1:  number | string
  total_valor_d_zero:     number | string
  total_delta:            number | string
  rows:                   CosifRowDiffRaw[]
}

function _coerceQtde(q: number | string | null | undefined): number | null {
  if (q === null || q === undefined) return null
  return Number(q)
}

function _coerceCosifRowDiff(r: CosifRowDiffRaw): CosifRowDiff {
  return {
    silver_origin:        r.silver_origin,
    codigo:               r.codigo,
    nome:                 r.nome,
    valor_d_minus_1:      Number(r.valor_d_minus_1),
    valor_d_zero:         Number(r.valor_d_zero),
    delta:                Number(r.delta),
    quantidade_d_minus_1: _coerceQtde(r.quantidade_d_minus_1),
    quantidade_d_zero:    _coerceQtde(r.quantidade_d_zero),
    indexador:            r.indexador,
    cosif_source:         r.cosif_source,
    status:               r.status,
    contraparte:          r.contraparte,
  }
}

function _coerceCosifRowsResponse(r: CosifRowsResponseRaw): CosifRowsResponse {
  return {
    fundo_id:               r.fundo_id,
    data_d_zero:            r.data_d_zero,
    data_d_minus_1:         r.data_d_minus_1,
    cosif_codigo:           r.cosif_codigo,
    cosif_nome:             r.cosif_nome,
    total_valor_d_minus_1:  Number(r.total_valor_d_minus_1),
    total_valor_d_zero:     Number(r.total_valor_d_zero),
    total_delta:            Number(r.total_delta),
    rows:                   r.rows.map(_coerceCosifRowDiff),
  }
}

export const controladoria = {
  cotaSubVariacaoDiaria: async (
    fundoId: string,
    data: string,           // YYYY-MM-DD
    dataAnterior?: string,  // YYYY-MM-DD opcional (override de D-1)
  ): Promise<VariacaoDiariaResponse> => {
    const params = new URLSearchParams({ fundo_id: fundoId, data })
    if (dataAnterior) params.set("data_anterior", dataAnterior)
    const raw = await apiClient.get<VariacaoDiariaResponse>(
      `/controladoria/cota-sub/variacao-diaria?${params.toString()}`,
    )
    return _coerceVariacao(raw)
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

  cotaSubBalanco: async (
    fundoId: string,
    data: string,           // YYYY-MM-DD
    dataAnterior?: string,  // YYYY-MM-DD opcional (override de D-1)
  ): Promise<BalancoResponse> => {
    const params = new URLSearchParams({ fundo_id: fundoId, data })
    if (dataAnterior) params.set("data_anterior", dataAnterior)
    const raw = await apiClient.get<BalancoResponseRaw>(
      `/controladoria/cota-sub/balanco?${params.toString()}`,
    )
    return {
      ...raw,
      rows: raw.rows.map(_coerceBalanceRow),
    }
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

  cotaSubBalanceteDiario: async (
    fundoId: string,
    data: string,
    dataAnterior?: string,
  ): Promise<BalanceteResponse> => {
    const params = new URLSearchParams({ fundo_id: fundoId, data })
    if (dataAnterior) params.set("data_anterior", dataAnterior)
    const raw = await apiClient.get<BalanceteResponseRaw>(
      `/controladoria/cota-sub/balancete-diario?${params.toString()}`,
    )
    return _coerceBalanceteResponse(raw)
  },

  cotaSubBalanceteCosifRows: async (
    fundoId: string,
    data: string,
    cosifCodigo: string,
  ): Promise<CosifRowsResponse> => {
    const params = new URLSearchParams({ fundo_id: fundoId, data })
    const raw = await apiClient.get<CosifRowsResponseRaw>(
      `/controladoria/cota-sub/balancete-diario/cosif/${encodeURIComponent(cosifCodigo)}/rows?${params.toString()}`,
    )
    return _coerceCosifRowsResponse(raw)
  },

  cotaSubExplicacao: async (
    fundoId: string,
    data: string,
    opts?: {
      dataAnterior?: string
      thresholdBrl?: number
      topN?:         number
    },
  ): Promise<ExplicacaoVariacaoResponse> => {
    const params = new URLSearchParams({ fundo_id: fundoId, data })
    if (opts?.dataAnterior) params.set("data_anterior", opts.dataAnterior)
    if (opts?.thresholdBrl !== undefined) params.set("threshold_brl", String(opts.thresholdBrl))
    if (opts?.topN !== undefined) params.set("top_n", String(opts.topN))
    const raw = await apiClient.get<ExplicacaoVariacaoResponse>(
      `/controladoria/cota-sub/explicacao?${params.toString()}`,
    )
    return _coerceExplicacao(raw)
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
