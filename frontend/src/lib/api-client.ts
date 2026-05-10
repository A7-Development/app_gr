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

export const apiClient = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body),
  delete: <T>(path: string) => request<T>("DELETE", path),
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

export type MeResponse = {
  user: { id: string; email: string; name: string }
  tenant: { id: string; slug: string; name: string; is_system_maintainer: boolean }
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

export async function login(email: string, password: string): Promise<LoginResponse> {
  const res = await apiClient.post<LoginResponse>("/auth/login", {
    email,
    password,
  })
  setToken(res.access_token)
  return res
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

export type OperacoesResumo = {
  total_operacoes: KPI
  volume_bruto: KPI
  ticket_medio: KPI
  taxa_media: KPI
  prazo_medio: KPI
  receita_contratada: KPI
  takeaway_pt: string | null
}

//
// L3 Volume — schema rico (responde 8 perguntas-chave do diretor de FIDC).
//

export type PointDim = {
  periodo: string
  categoria_id: string
  categoria: string
  valor: number
}

export type CategoryValueDelta = {
  categoria: string
  categoria_id: string | null
  valor: number
  quantidade: number | null
  /** Variacao % vs periodo imediatamente anterior (mesmo tamanho). */
  delta_pct: number | null
  // Campos opcionais — populados apenas em `por_produto` (L3 Volume).
  /** Taxa de juros media ponderada por volume (% a.m.). */
  taxa_media_pct?: number | null
  /** Prazo medio real ponderado por volume (dias). */
  prazo_medio_dias?: number | null
  /** Serie semanal (~13 pts) de volume dos ultimos 90 dias. */
  tendencia_90d?: Point[]
  /** Variacao % dos ultimos 90d vs 90d anteriores. */
  tendencia_90d_delta_pct?: number | null
}

export type TopCedenteItem = {
  ranking: number
  cedente_id: number
  nome: string
  volume: number
  delta_pct: number | null
}

export type VolumeResumoDeltas = {
  // Volume
  volume_total: number
  /** Delta vs periodo imediatamente anterior (mesmo tamanho do filtro). */
  volume_delta_pct: number | null
  volume_sparkline_12m: Point[]

  // Ticket por operacao (volume / n_operacoes)
  ticket_medio: number
  ticket_delta_pct: number | null
  ticket_sparkline_12m: Point[]

  // Ticket por titulo (volume / soma_quantidade_titulos)
  ticket_medio_titulo: number
  ticket_medio_titulo_delta_pct: number | null
  ticket_medio_titulo_sparkline_12m: Point[]

  // Produto lider — sigla e ID estavel; `nome` e o label amigavel.
  produto_lider_sigla: string
  produto_lider_nome: string | null
  produto_lider_pct: number
  produto_lider_delta_pp: number | null
  produto_lider_sparkline_12m: Point[]

  /** Label PT-BR com o range comparado (ex.: "vs mai/24 a abr/25"). */
  comparacao_label_pt: string
}

export type SeriesEVolume = {
  /** Chart principal modo "Total" — serie mensal consolidada. */
  evolucao: Point[]
  /** Chart principal modo "Por produto" — serie stacked. */
  evolucao_por_produto: PointDim[]
  /** Chart principal modo "Por UA" — serie stacked. */
  evolucao_por_ua: PointDim[]

  /** Decomposicao com delta vs periodo anterior. */
  por_produto: CategoryValueDelta[]
  por_ua: CategoryValueDelta[]
  /** Top N cedentes (Onda 2 — vazio por enquanto). */
  top_cedentes: TopCedenteItem[]

  /** KPIs de contexto (§1 da aba). */
  resumo: VolumeResumoDeltas

  /** Overlays pareadas ponto a ponto com `evolucao`. */
  evolucao_taxa_media: Point[]
  evolucao_prazo_medio: Point[]
  evolucao_ticket_medio: Point[]
}
export type SeriesETaxa = {
  evolucao: Point[]
  por_produto: CategoryValue[]
  por_modalidade: CategoryValue[]
}
export type SeriesEPrazo = {
  evolucao: Point[]
  por_produto: CategoryValue[]
}
export type SeriesETicket = {
  evolucao: Point[]
  por_produto: CategoryValue[]
  por_cedente_top: CategoryValue[]
}
export type SeriesEReceita = {
  evolucao: Point[]
  por_componente: CategoryValue[]
  por_produto: CategoryValue[]
}
export type SeriesEDiaUtil = {
  por_dia_util: Point[]
  por_dia_semana: CategoryValue[]
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

export const biOperacoes = {
  resumo: (f: BIFilters) =>
    apiClient.get<BIResponse<OperacoesResumo>>(
      `/bi/operacoes/resumo${filtersToQueryString(f)}`,
    ),
  volume: (f: BIFilters) =>
    apiClient.get<BIResponse<SeriesEVolume>>(
      `/bi/operacoes/volume${filtersToQueryString(f)}`,
    ),
  taxa: (f: BIFilters) =>
    apiClient.get<BIResponse<SeriesETaxa>>(
      `/bi/operacoes/taxa${filtersToQueryString(f)}`,
    ),
  prazo: (f: BIFilters) =>
    apiClient.get<BIResponse<SeriesEPrazo>>(
      `/bi/operacoes/prazo${filtersToQueryString(f)}`,
    ),
  ticket: (f: BIFilters) =>
    apiClient.get<BIResponse<SeriesETicket>>(
      `/bi/operacoes/ticket${filtersToQueryString(f)}`,
    ),
  receita: (f: BIFilters) =>
    apiClient.get<BIResponse<SeriesEReceita>>(
      `/bi/operacoes/receita${filtersToQueryString(f)}`,
    ),
  diaUtil: (f: BIFilters) =>
    apiClient.get<BIResponse<SeriesEDiaUtil>>(
      `/bi/operacoes/dia-util${filtersToQueryString(f)}`,
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
  outro_ativo: number       // (I.4)
  pdd_aprox: number         // (I.2.a.11) redutor ja contido em dc_risco
  ativo_total: number       // (I)
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

  // Override do tenant (null se nunca foi persistida linha em TSEC)
  enabled: boolean | null
  schedule_kind: ScheduleKind | null
  schedule_value: string | null
  last_sync_started_at: string | null
  last_sync_finished_at: string | null
  last_sync_status: "ok" | "erro" | "em_progresso" | null
  last_sync_error: string | null
  unidade_administrativa_id: string | null
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
