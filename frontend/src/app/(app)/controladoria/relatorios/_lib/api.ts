// src/app/(app)/controladoria/relatorios/_lib/api.ts
//
// Cliente HTTP do catalogo de relatorios (Controladoria L2).
// Espelha schemas em backend/app/modules/controladoria/schemas/reports.py.

import { apiClient, downloadBlob } from "@/lib/api-client"
import type { ReportCategoryId } from "@/design-system/tokens/report-category"

export type ReportRefreshKind = "daily" | "interval" | "on_demand_async"
export type ReportPermission = "none" | "read" | "write" | "admin"

export type AdministradoraId = "admin:qitech"
// Quando Kanastra/BTG entrarem, adicionar | "admin:kanastra" | "admin:btg"

export type ReportCard = {
  slug: string
  name: string
  description: string
  category: ReportCategoryId
  administradora: AdministradoraId
  endpoint_name: string
  canonical_table: string
  refresh_kind: ReportRefreshKind
  has_date_filter: boolean
  has_fund_filter: boolean
  default_permission: ReportPermission
}

export type CatalogResponse = {
  reports: ReportCard[]
  total: number
}

export type ProvenanceMetadata = {
  source_type: AdministradoraId
  adapter_version: string | null
  last_ingested_at: string | null
  trust_level: string | null
}

export type RowsResponse = {
  rows: Record<string, unknown>[]
  total: number
  page: number
  page_size: number
  provenance: ProvenanceMetadata
}

export type RowsParams = {
  fundo_id?: string
  periodo_inicio?: string
  periodo_fim?: string
  page?: number
  page_size?: number
}

// ─── Bundle agregado do slug `qitech-estoque-carteira` ────────────────
//
// Endpoint dedicado para a detail page rica (DashboardBiPadrao). Tabela
// paginada de recebiveis continua via `relatorios.rows()` generico acima.
// Backend: `app/modules/controladoria/api/qitech_estoque_carteira.py`.

export type CarteiraKpis = {
  valor_nominal_total: string | number
  valor_presente_total: string | number
  valor_aquisicao_total: string | number
  valor_pdd_total: string | number
  qtd_titulos: number
  pct_vencido: number
  pdd_medio_pct: number
  concentracao_top1_sacados_pct: number
  concentracao_top5_sacados_pct: number
  concentracao_top1_cedentes_pct: number
  concentracao_top5_cedentes_pct: number
}

export type CarteiraBreakdownItem = {
  chave: string
  label: string
  valor_nominal: string | number
  // Populado APENAS em `por_faixa_pdd` (decomposicao real de valor_pdd_total
  // por faixa Bacen 2682). Soma das barras casa com `kpis.valor_pdd_total`.
  // Demais breakdowns vem com null/undefined.
  valor_pdd?: string | number | null
  qtd_titulos: number
  pct_do_total: number
}

export type CarteiraBundle = {
  data_referencia: string | null
  fundo_doc: string | null
  fundo_nome: string | null
  kpis: CarteiraKpis
  por_faixa_pdd: CarteiraBreakdownItem[]
  top_sacados: CarteiraBreakdownItem[]
  top_cedentes: CarteiraBreakdownItem[]
  por_originador: CarteiraBreakdownItem[]
  por_produto: CarteiraBreakdownItem[]
  por_situacao: CarteiraBreakdownItem[]
  por_coobrigacao: CarteiraBreakdownItem[]
  provenance: ProvenanceMetadata
  is_empty: boolean
}

export type CarteiraBundleParams = {
  fundo_id?: string
  data_referencia?: string  // YYYY-MM-DD
}

export const relatorios = {
  catalog: async (params?: { category?: ReportCategoryId }): Promise<CatalogResponse> => {
    const search = new URLSearchParams()
    if (params?.category) search.set("category", params.category)
    const qs = search.toString()
    return apiClient.get<CatalogResponse>(
      `/controladoria/relatorios/catalog${qs ? `?${qs}` : ""}`,
    )
  },

  rows: async (slug: string, params?: RowsParams): Promise<RowsResponse> => {
    const search = new URLSearchParams()
    if (params?.fundo_id) search.set("fundo_id", params.fundo_id)
    if (params?.periodo_inicio) search.set("periodo_inicio", params.periodo_inicio)
    if (params?.periodo_fim) search.set("periodo_fim", params.periodo_fim)
    if (params?.page) search.set("page", String(params.page))
    if (params?.page_size) search.set("page_size", String(params.page_size))
    const qs = search.toString()
    return apiClient.get<RowsResponse>(
      `/controladoria/relatorios/${encodeURIComponent(slug)}${qs ? `?${qs}` : ""}`,
    )
  },

  qitechEstoqueCarteiraBundle: async (
    params?: CarteiraBundleParams,
  ): Promise<CarteiraBundle> => {
    const search = new URLSearchParams()
    if (params?.fundo_id) search.set("fundo_id", params.fundo_id)
    if (params?.data_referencia) search.set("data_referencia", params.data_referencia)
    const qs = search.toString()
    return apiClient.get<CarteiraBundle>(
      `/controladoria/relatorios/padronizados/qitech-estoque-carteira/bundle${qs ? `?${qs}` : ""}`,
    )
  },

  /** Baixa XLSX (native types — numbers/dates) com os mesmos filtros do
   * bundle. Trigger automatico do download do browser via Blob/anchor.
   * Backend serializa via openpyxl write_only mode (memory-friendly). */
  qitechEstoqueCarteiraExportXlsx: async (
    params?: CarteiraBundleParams,
  ): Promise<void> => {
    const search = new URLSearchParams()
    if (params?.fundo_id) search.set("fundo_id", params.fundo_id)
    if (params?.data_referencia) search.set("data_referencia", params.data_referencia)
    const qs = search.toString()
    const blob = await apiClient.getBlob(
      `/controladoria/relatorios/padronizados/qitech-estoque-carteira/export.xlsx${qs ? `?${qs}` : ""}`,
    )
    const datePart = params?.data_referencia ?? "ultimo"
    downloadBlob(blob, `carteira-${datePart}.xlsx`)
  },
}

// ─── QiTech jobs assincronos (dispatch + lista) ───────────────────────
//
// Espelha `backend/app/modules/integracoes/routers/qitech_jobs.py`. Endpoints
// vivem em `/integracoes/qitech/jobs/*` — separados do catalogo controladoria
// porque sao infraestrutura (disparo de POST + webhook), nao consulta de
// relatorio. Mantemos o cliente aqui pra reuso pela pagina Carteira (botao
// "Solicitar novo snapshot") sem inflar `api-client.ts`.

export type QitechJobStatus =
  | "WAITING"
  | "PROCESSING"
  | "SUCCESS"
  | "ERROR"
  | "EXPIRED"

export type QitechJob = {
  id: string
  report_type: string
  cnpj_fundo: string
  reference_date: string
  environment: "production" | "sandbox"
  qitech_job_id: string
  qitech_webhook_id: number | null
  status: QitechJobStatus
  result_file_link: string | null
  triggered_by: string
  error_message: string | null
  created_at: string
  completed_at: string | null
}

export type DispatchFidcEstoquePayload = {
  cnpj_fundo: string
  reference_date: string  // YYYY-MM-DD
  environment?: "production" | "sandbox"
}

export const qitechJobs = {
  dispatchFidcEstoque: async (
    payload: DispatchFidcEstoquePayload,
  ): Promise<QitechJob> => {
    return apiClient.post<QitechJob>(
      "/integracoes/qitech/jobs/fidc-estoque/dispatch",
      { environment: "production", ...payload },
    )
  },

  list: async (filters?: {
    report_type?: string
    status?: QitechJobStatus
    cnpj_fundo?: string
    limit?: number
  }): Promise<QitechJob[]> => {
    const search = new URLSearchParams()
    if (filters?.report_type) search.set("report_type", filters.report_type)
    if (filters?.status) search.set("status", filters.status)
    if (filters?.cnpj_fundo) search.set("cnpj_fundo", filters.cnpj_fundo)
    if (filters?.limit) search.set("limit", String(filters.limit))
    const qs = search.toString()
    return apiClient.get<QitechJob[]>(
      `/integracoes/qitech/jobs${qs ? `?${qs}` : ""}`,
    )
  },
}
