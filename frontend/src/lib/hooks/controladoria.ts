"use client"

/**
 * React Query hooks do modulo Controladoria.
 * Espelha endpoints em backend/app/modules/controladoria/api/.
 */

import { useQuery } from "@tanstack/react-query"

import {
  controladoria,
  type DreBaseFilters,
  type DreDrillFornecedoresFilters,
  type DrePivotFilters,
} from "@/lib/api-client"

const KEYS = {
  variacaoDiaria: (fundoId: string, data: string, dataAnterior?: string) =>
    ["controladoria", "cota-sub", "variacao-diaria", fundoId, data, dataAnterior ?? null] as const,
  balanco: (fundoId: string, data: string, dataAnterior?: string) =>
    ["controladoria", "cota-sub", "balanco", fundoId, data, dataAnterior ?? null] as const,
  balanceteDiario: (fundoId: string, data: string, dataAnterior?: string) =>
    ["controladoria", "cota-sub", "balancete-diario", fundoId, data, dataAnterior ?? null] as const,
  cosifRows: (fundoId: string, data: string, cosifCodigo: string) =>
    ["controladoria", "cota-sub", "cosif-rows", fundoId, data, cosifCodigo] as const,
  variacoesDia: (fundoId: string, data: string, dataAnterior?: string) =>
    ["controladoria", "cota-sub", "variacoes-dia", fundoId, data, dataAnterior ?? null] as const,
  datasDisponiveis: (fundoId: string) =>
    ["controladoria", "cota-sub", "datas-disponiveis", fundoId] as const,

  dreCompetencias: (f: DreBaseFilters) =>
    ["controladoria", "dre", "competencias", f] as const,
  drePivot: (f: DrePivotFilters) =>
    ["controladoria", "dre", "pivot", f] as const,
  dreFornecedores: (f: DreDrillFornecedoresFilters) =>
    ["controladoria", "dre", "fornecedores", f] as const,
}

export function useDatasDisponiveis(
  fundoId: string | null | undefined,
) {
  // Datas em que a QiTech publicou snapshot da UA. Usado pelo Calendar para
  // impedir selecao de dias sem dados (fim de semana, feriado, falha ETL).
  // staleTime longo porque ETL nao roda toda hora.
  const enabled = !!fundoId
  return useQuery({
    queryKey: KEYS.datasDisponiveis(fundoId ?? ""),
    queryFn: () => controladoria.cotaSubDatasDisponiveis(fundoId!),
    enabled,
    staleTime: 60 * 60 * 1000,  // 1 hora
  })
}

export function useVariacaoDiaria(
  fundoId: string | null | undefined,
  data: string | null | undefined,
  dataAnterior?: string | null,
) {
  const enabled = !!fundoId && !!data
  return useQuery({
    queryKey: KEYS.variacaoDiaria(fundoId ?? "", data ?? "", dataAnterior ?? undefined),
    queryFn: () => controladoria.cotaSubVariacaoDiaria(
      fundoId!,
      data!,
      dataAnterior ?? undefined,
    ),
    enabled,
    staleTime: 5 * 60 * 1000,  // 5 min — dia anterior nao muda
  })
}

export function useBalanco(
  fundoId: string | null | undefined,
  data: string | null | undefined,
  dataAnterior?: string | null,
) {
  const enabled = !!fundoId && !!data
  return useQuery({
    queryKey: KEYS.balanco(fundoId ?? "", data ?? "", dataAnterior ?? undefined),
    queryFn: () => controladoria.cotaSubBalanco(
      fundoId!,
      data!,
      dataAnterior ?? undefined,
    ),
    enabled,
    staleTime: 5 * 60 * 1000,
  })
}

export function useVariacoesDia(
  fundoId: string | null | undefined,
  data: string | null | undefined,
  dataAnterior?: string | null,
) {
  const enabled = !!fundoId && !!data
  return useQuery({
    queryKey: KEYS.variacoesDia(fundoId ?? "", data ?? "", dataAnterior ?? undefined),
    queryFn: () => controladoria.cotaSubVariacoesDia(
      fundoId!,
      data!,
      dataAnterior ?? undefined,
    ),
    enabled,
    staleTime: 5 * 60 * 1000,
  })
}

export function useBalanceteDiario(
  fundoId: string | null | undefined,
  data: string | null | undefined,
  dataAnterior?: string | null,
) {
  const enabled = !!fundoId && !!data
  return useQuery({
    queryKey: KEYS.balanceteDiario(fundoId ?? "", data ?? "", dataAnterior ?? undefined),
    queryFn: () => controladoria.cotaSubBalanceteDiario(
      fundoId!,
      data!,
      dataAnterior ?? undefined,
    ),
    enabled,
    staleTime: 5 * 60 * 1000,
  })
}

export function useCosifRows(
  fundoId: string | null | undefined,
  data: string | null | undefined,
  cosifCodigo: string | null | undefined,
) {
  // Drill-down do CosifDrillSheet — so dispara quando o user clica numa
  // conta com codigo. Bucket pendente (codigo=null) nao tem rows endpoint.
  const enabled = !!fundoId && !!data && !!cosifCodigo
  return useQuery({
    queryKey: KEYS.cosifRows(fundoId ?? "", data ?? "", cosifCodigo ?? ""),
    queryFn: () => controladoria.cotaSubBalanceteCosifRows(
      fundoId!,
      data!,
      cosifCodigo!,
    ),
    enabled,
    staleTime: 5 * 60 * 1000,
  })
}

// ── DRE — Demonstrativo do Resultado do Exercicio ──────────────────────────
// Le silver wh_dre_mensal. fundoId aqui e INT (Bitfin), NAO UUID.

export function useDreCompetencias(filters: DreBaseFilters = {}) {
  return useQuery({
    queryKey: KEYS.dreCompetencias(filters),
    queryFn:  () => controladoria.dreCompetenciasDisponiveis(filters),
    staleTime: 30 * 60 * 1000,  // ETL Bitfin nao roda toda hora
  })
}

export function useDrePivot(filters: DrePivotFilters | null | undefined) {
  return useQuery({
    queryKey: KEYS.drePivot(filters ?? ({} as DrePivotFilters)),
    queryFn:  () => controladoria.drePivot(filters!),
    enabled:  !!filters?.competenciaDe && !!filters?.competenciaAte,
    staleTime: 5 * 60 * 1000,
  })
}

export function useDreFornecedores(
  filters: DreDrillFornecedoresFilters | null | undefined,
) {
  return useQuery({
    queryKey: KEYS.dreFornecedores(filters ?? ({} as DreDrillFornecedoresFilters)),
    queryFn:  () => controladoria.dreDrillFornecedores(filters!),
    enabled:
      !!filters?.grupoDre && !!filters?.competenciaDe && !!filters?.competenciaAte,
    staleTime: 5 * 60 * 1000,
  })
}
