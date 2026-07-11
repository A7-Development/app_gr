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

// ── Curadoria de liquidações + modelo de detecção ──────────────────────────

import {
  riscoCedentes,
  riscoCuradoriaLiquidacoes,
  type CuradoriaLiquidacoesFilters,
} from "@/lib/api-client"

const KEY_CURADORIA = ["risco", "curadoria-liquidacoes"] as const
const KEY_MODELOS = ["risco", "deteccao-modelos"] as const

export function useCuradoriaLiquidacoes(filters: CuradoriaLiquidacoesFilters) {
  return useQuery({
    queryKey: [...KEY_CURADORIA, filters],
    queryFn: () => riscoCuradoriaLiquidacoes.list(filters),
    staleTime: 30 * 1000,
    placeholderData: (prev) => prev, // paginação sem "flash" de loading
  })
}

export function useTagLiquidacao() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      liquidacaoId,
      tag,
      nota,
    }: {
      liquidacaoId: string
      tag: "fraude" | "ok" | "neutro"
      nota?: string | null
    }) => riscoCuradoriaLiquidacoes.tag(liquidacaoId, tag, nota),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY_CURADORIA })
    },
  })
}

export function useDeteccaoModelos() {
  return useQuery({
    queryKey: KEY_MODELOS,
    queryFn: () => riscoCuradoriaLiquidacoes.modelos(),
    staleTime: 30 * 1000,
  })
}

export function useTreinarModelo() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (nome: string) => riscoCuradoriaLiquidacoes.treinar(nome),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY_MODELOS }),
  })
}

export function useAtivarVersaoModelo() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ nome, versao }: { nome: string; versao: number }) =>
      riscoCuradoriaLiquidacoes.ativarVersao(nome, versao),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY_MODELOS })
      qc.invalidateQueries({ queryKey: KEY_CURADORIA })
    },
  })
}

export function usePontuarAgora() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (nome: string) => riscoCuradoriaLiquidacoes.pontuarAgora(nome),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY_CURADORIA }),
  })
}

export function useMemoriaLiquidacao(liquidacaoId: string | null) {
  return useQuery({
    queryKey: [...KEY_CURADORIA, "memoria", liquidacaoId],
    queryFn: () => riscoCuradoriaLiquidacoes.detalhe(liquidacaoId as string),
    enabled: liquidacaoId !== null,
    staleTime: 60 * 1000,
  })
}

export function useCedentesRisco(tendenciaDias = 30) {
  return useQuery({
    queryKey: ["risco", "cedentes", tendenciaDias],
    queryFn: () => riscoCedentes.list(tendenciaDias),
    staleTime: 60 * 1000,
  })
}

// ── Padrões de liquidação (perfil determinístico) ──────────────────────────

import { riscoPadroesLiquidacao, type JanelaLiquidacao } from "@/lib/api-client"

export function usePadroesLiquidacao(janela: JanelaLiquidacao = "30d") {
  return useQuery({
    queryKey: ["risco", "padroes-liquidacao", janela],
    queryFn: () => riscoPadroesLiquidacao.perfil(janela),
    staleTime: 60 * 1000,
    placeholderData: (prev) => prev, // troca de janela sem "flash" de loading
  })
}

// ── Rating de integridade de liquidação ─────────────────────────────────────

import { riscoRatingLiquidacao } from "@/lib/api-client"

export function useRatingLiquidacao() {
  return useQuery({
    queryKey: ["risco", "rating-liquidacao"],
    queryFn: () => riscoRatingLiquidacao.cedentes(),
    staleTime: 60 * 1000,
  })
}

export function useRatingLiquidacaoPares(cedenteDocumento: string | null) {
  return useQuery({
    queryKey: ["risco", "rating-liquidacao", "pares", cedenteDocumento],
    queryFn: () => riscoRatingLiquidacao.pares(cedenteDocumento as string),
    enabled: cedenteDocumento !== null,
    staleTime: 60 * 1000,
  })
}
