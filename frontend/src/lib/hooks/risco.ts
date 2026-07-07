"use client"

/**
 * React Query hooks do modulo Risco — contrato de liquidacao por produto.
 * Espelha backend/app/modules/risco/api/contratos_liquidacao.py
 * (require_module RISCO/READ na listagem, RISCO/WRITE ao definir).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  riscoContratosLiquidacao,
  type ContratoLiquidacaoUpdatePayload,
} from "@/lib/api-client"

const KEY = ["risco", "contratos-liquidacao"] as const

export function useContratosLiquidacao(janelaDias: number) {
  return useQuery({
    queryKey: [...KEY, janelaDias],
    queryFn: () => riscoContratosLiquidacao.list(janelaDias),
    staleTime: 30 * 1000,
  })
}

export function useDefinirContratoLiquidacao() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      sigla,
      payload,
    }: {
      sigla: string
      payload: ContratoLiquidacaoUpdatePayload
    }) => riscoContratosLiquidacao.definir(sigla, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY })
      qc.invalidateQueries({ queryKey: ["risco", "contratos-liquidacao-versoes"] })
    },
  })
}

export function useVersoesContratoLiquidacao(sigla: string | null) {
  return useQuery({
    queryKey: ["risco", "contratos-liquidacao-versoes", sigla],
    queryFn: () => riscoContratosLiquidacao.versoes(sigla as string),
    enabled: sigla !== null,
    staleTime: 30 * 1000,
  })
}
