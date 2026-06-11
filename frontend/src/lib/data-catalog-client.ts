// Client do Catálogo de datasets (admin/mantenedor) — Fase F (o tronco).
// Navega provedor → API/endpoint → dataset; cura nome/public_code/habilitar/
// markup; cria a 1ª versão do Contrato de campos.
// Backend protege com require_system_maintainer (HTTP 403).

import { apiClient } from "@/lib/api-client"

export type CatalogContractRef = {
  status: "active" | "none"
  version: number | null
  provider: string | null
  api_endpoint: string | null
  dataset_code: string | null
  n_campos: number | null
  n_novos: number | null
}

export type CatalogDatasetRow = {
  dataset_id: string
  provider_slug: string
  provider_api: string
  provider_dataset_code: string
  provider_query_name: string | null
  public_code: string | null
  display_name_pt_br: string | null
  categoria_ui: string | null
  enabled_for_sale: boolean
  current_cost_brl: number | null
  /** Custo editável quando o vendor não tem sync de preços. */
  cost_editable: boolean
  markup_pct: number | null
  mode: "marketplace" | "adapter"
  suggested_public_code: string
  suggested_name: string
  contract: CatalogContractRef
}

export type CatalogApiGroup = {
  api: string
  total: number
  datasets: CatalogDatasetRow[]
}

export type CatalogProviderGroup = {
  provider_slug: string
  provider_name: string
  total: number
  enabled_count: number
  with_contract_count: number
  apis: CatalogApiGroup[]
}

export type DatasetCurationPayload = {
  public_code?: string | null
  display_name_pt_br?: string | null
  categoria_ui?: string | null
  enabled_for_sale?: boolean | null
  markup_pct?: number | null
  current_cost_brl?: number | null
}

export type CreatedContract = {
  provider: string
  api_endpoint: string
  dataset_code: string
  public_code: string
  version: number
  n_campos: number
  already_existed: boolean
}

type ListParams = {
  provider?: string
  search?: string
  only_enabled?: boolean
  only_without_contract?: boolean
}

export const dataCatalog = {
  list: (params: ListParams = {}) => {
    const q = new URLSearchParams()
    if (params.provider) q.set("provider", params.provider)
    if (params.search) q.set("search", params.search)
    if (params.only_enabled) q.set("only_enabled", "true")
    if (params.only_without_contract) q.set("only_without_contract", "true")
    const qs = q.toString()
    return apiClient.get<CatalogProviderGroup[]>(
      `/admin/data-catalog${qs ? `?${qs}` : ""}`,
    )
  },
  curate: (datasetId: string, patch: DatasetCurationPayload) =>
    apiClient.patch<CatalogDatasetRow>(
      `/admin/data-catalog/datasets/${datasetId}`,
      patch,
    ),
  createContract: (datasetId: string) =>
    apiClient.post<CreatedContract>(
      `/admin/data-catalog/datasets/${datasetId}/create-contract`,
      {},
    ),
}
