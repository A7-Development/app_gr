"use client"

/**
 * React Query hooks do modulo Controladoria.
 * Espelha endpoints em backend/app/modules/controladoria/api/.
 */

import { useQuery } from "@tanstack/react-query"

import { controladoria } from "@/lib/api-client"

const KEYS = {
  variacaoDiaria: (fundoId: string, data: string, dataAnterior?: string) =>
    ["controladoria", "cota-sub", "variacao-diaria", fundoId, data, dataAnterior ?? null] as const,
  balanco: (fundoId: string, data: string, dataAnterior?: string) =>
    ["controladoria", "cota-sub", "balanco", fundoId, data, dataAnterior ?? null] as const,
  variacoesDia: (fundoId: string, data: string, dataAnterior?: string) =>
    ["controladoria", "cota-sub", "variacoes-dia", fundoId, data, dataAnterior ?? null] as const,
  datasDisponiveis: (fundoId: string) =>
    ["controladoria", "cota-sub", "datas-disponiveis", fundoId] as const,
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
