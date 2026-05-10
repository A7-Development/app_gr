// src/app/(app)/controladoria/relatorios/_lib/api.ts
//
// Cliente HTTP do catalogo de relatorios (Controladoria L2).
// Espelha schemas em backend/app/modules/controladoria/schemas/reports.py.

import { apiClient } from "@/lib/api-client"
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
}
