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
  detail: string

  constructor(status: number, detail: string) {
    super(`API ${status}: ${detail}`)
    this.name = "ApiError"
    this.status = status
    this.detail = detail
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
    let detail = res.statusText
    try {
      const err = (await res.json()) as { detail?: string }
      if (err.detail) detail = err.detail
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

export type MeResponse = {
  user: { id: string; email: string; name: string }
  tenant: { id: string; slug: string; name: string }
  enabled_modules: string[]
  user_permissions: Record<string, "none" | "read" | "write" | "admin">
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
  last_ingested_at: string | null
  last_source_updated_at: string | null
  trust_level: "high" | "medium" | "low"
  ingested_by_version: string
  row_count: number
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
  volume_mom_pct: number | null
  volume_yoy_pct: number | null
  volume_sparkline_12m: Point[]

  // Ticket por operacao (volume / n_operacoes)
  ticket_medio: number
  ticket_mom_pct: number | null
  ticket_sparkline_12m: Point[]

  // Ticket por titulo (volume / soma_quantidade_titulos)
  ticket_medio_titulo: number
  ticket_medio_titulo_mom_pct: number | null
  ticket_medio_titulo_sparkline_12m: Point[]

  // Operacoes
  n_operacoes: number
  n_operacoes_mom_pct: number | null
  n_operacoes_sparkline_12m: Point[]

  // Produto lider
  produto_lider_sigla: string
  produto_lider_pct: number
  produto_lider_delta_pp: number | null
  produto_lider_sparkline_12m: Point[]
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
  /** Quantidade de competencias mais recentes (L3 Evolucao). */
  meses?: number
  /** Busca por nome ou CNPJ (ILIKE parcial) — usado na L3 Fundos. */
  busca?: string
}

function benchmarkQS(f: BenchmarkFilters): string {
  const p = new URLSearchParams()
  if (f.competencia) p.set("competencia", f.competencia)
  if (f.meses !== undefined) p.set("meses", String(f.meses))
  if (f.busca && f.busca.trim()) p.set("busca", f.busca.trim())
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

export const biBenchmark = {
  resumo: (f: BenchmarkFilters = {}) =>
    apiClient.get<BIResponse<BenchmarkResumo>>(
      `/bi/benchmark/resumo${benchmarkQS(f)}`,
    ),
  pdd: (f: BenchmarkFilters = {}) =>
    apiClient.get<BIResponse<PDDDistribuicao>>(
      `/bi/benchmark/pdd${benchmarkQS(f)}`,
    ),
  evolucao: (f: BenchmarkFilters = {}) =>
    apiClient.get<BIResponse<BenchmarkEvolucao>>(
      `/bi/benchmark/evolucao${benchmarkQS(f)}`,
    ),
  fundos: (f: BenchmarkFilters = {}) =>
    apiClient.get<BIResponse<FundosLista>>(
      `/bi/benchmark/fundos${benchmarkQS(f)}`,
    ),
  comparativo: (a: ComparativoArgs) =>
    apiClient.get<BIResponse<ComparativoResponse>>(
      `/bi/benchmark/comparativo${comparativoQS(a)}`,
    ),
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

export const biMetadata = {
  uas: () => apiClient.get<UAOption[]>("/bi/metadata/uas"),
  produtos: () => apiClient.get<ProdutoOption[]>("/bi/metadata/produtos"),
  dataMinima: () => apiClient.get<DataMinimaResponse>("/bi/metadata/data-minima"),
}
