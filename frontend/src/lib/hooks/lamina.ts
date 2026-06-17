"use client"

/**
 * React Query hooks -- Controladoria > Fechamento Mensal > Lamina do Fundo.
 * Espelha backend/app/modules/controladoria/api/lamina.py.
 *
 * `fundoId` omitido => backend resolve o FIDC do tenant. A competencia e
 * sempre fechada (regra no service); o seletor lista so meses fechados.
 */

import { useQuery } from "@tanstack/react-query"

import {
  controladoria,
  type LaminaCompetenciasResponse,
  type LaminaResponse,
} from "@/lib/api-client"

const KEYS = {
  competencias: (fundoId?: string) =>
    ["controladoria", "lamina", "competencias", fundoId ?? null] as const,
  lamina: (fundoId?: string, competencia?: string) =>
    ["controladoria", "lamina", fundoId ?? null, competencia ?? null] as const,
}

const STALE = 10 * 60 * 1000 // dado de competencia fechada e estavel

export function useLaminaCompetencias(fundoId?: string) {
  return useQuery<LaminaCompetenciasResponse>({
    queryKey: KEYS.competencias(fundoId),
    queryFn: () => controladoria.laminaCompetencias(fundoId),
    staleTime: STALE,
  })
}

export function useLamina(competencia?: string | null, fundoId?: string) {
  return useQuery<LaminaResponse>({
    queryKey: KEYS.lamina(fundoId, competencia ?? undefined),
    queryFn: () =>
      controladoria.lamina({
        fundoId,
        competencia: competencia ?? undefined,
      }),
    staleTime: STALE,
  })
}
