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
