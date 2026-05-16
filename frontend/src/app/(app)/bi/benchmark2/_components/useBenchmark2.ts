"use client"

import { useQuery } from "@tanstack/react-query"

import { biBenchmark, biBenchmark2 } from "@/lib/api-client"

export function useBenchmark2Fundos() {
  return useQuery({
    queryKey: ["bi", "benchmark2", "fundos"] as const,
    queryFn: () => biBenchmark2.fundos(),
    staleTime: 5 * 60 * 1000,
  })
}

// Ficha unitaria de um fundo no layout Lamina. Reusa o endpoint canonico
// `/bi/benchmark/fundo/{cnpj}` (que sera renomeado pra benchmark2 na Fase 4).
export function useBenchmark2Fundo(cnpj: string) {
  return useQuery({
    queryKey: ["bi", "benchmark2", "fundo", cnpj] as const,
    queryFn: () => biBenchmark.fundo(cnpj),
    staleTime: 5 * 60 * 1000,
    enabled: Boolean(cnpj),
  })
}
