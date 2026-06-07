// Client da curadoria de Contratos de Dados (admin/mantenedor) — Fase 5.
// Backend protege com require_system_maintainer (HTTP 403).

import { apiClient } from "@/lib/api-client"

export type DataContractField = {
  field_path: string
  public_label: string | null
  description: string | null
  semantic_type: string
  categoria_ui: string | null
  sensibilidade: string
  eh_fato: string
  to_silver: boolean
  silver_target: string | null
  on_screen: boolean
  screen_order: number | null
  to_tool: boolean
  to_agent: boolean
  to_check: boolean
  status: string
  novo: boolean
  valor_exemplo: string | null
}

export type DataContractListItem = {
  contract_id: string
  provider: string
  api_endpoint: string
  dataset_code: string
  public_code: string | null
  version: number
  status: string
  n_campos: number
}

export type DataContractDetail = {
  contract_id: string
  provider: string
  api_endpoint: string
  dataset_code: string
  public_code: string | null
  version: number
  status: string
  campos: DataContractField[]
  n_novos: number
}

/** Estado de UM campo enviado ao salvar (a UI manda o conjunto completo). */
export type FieldSaveSpec = {
  field_path: string
  public_label: string | null
  description: string | null
  semantic_type: string
  categoria_ui: string | null
  sensibilidade: string
  eh_fato: string
  to_silver: boolean
  silver_target: string | null
  on_screen: boolean
  screen_order: number | null
  to_tool: boolean
  to_agent: boolean
  to_check: boolean
}

export const dataContracts = {
  list: () => apiClient.get<DataContractListItem[]>("/admin/data-contracts"),
  detail: (provider: string, api: string, dataset: string) =>
    apiClient.get<DataContractDetail>(
      `/admin/data-contracts/${provider}/${api}/${dataset}`,
    ),
  saveNewVersion: (
    provider: string,
    api: string,
    dataset: string,
    fields: FieldSaveSpec[],
  ) =>
    apiClient.post<DataContractDetail>(
      `/admin/data-contracts/${provider}/${api}/${dataset}/new-version`,
      { fields },
    ),
}
