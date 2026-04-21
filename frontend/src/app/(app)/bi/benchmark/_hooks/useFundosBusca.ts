"use client"

import { useQuery } from "@tanstack/react-query"

import { biBenchmark, type FundoRow } from "@/lib/api-client"

//
// useFundosBusca — query real pro endpoint /bi/benchmark/fundos.
// `termo` deve ja vir debounced (debounce vive na borda URL: o consumer
// escreve ?q= com 300ms; este hook apenas consome o valor ja estavel).
// React Query cacheia por termo => trocar de tab e voltar nao refaz request.
//

export type FundoLista = FundoRow

export function useFundosBusca(termo: string) {
  const t = termo.trim()
  const q = useQuery({
    queryKey: ["bi", "benchmark", "fundos", t],
    queryFn: () => biBenchmark.fundos(t ? { busca: t } : {}),
    staleTime: 60_000,
  })

  return {
    fundos: q.data?.data.fundos ?? [],
    total: q.data?.data.total ?? 0,
    competencia: q.data?.data.competencia ?? null,
    loading: q.isFetching,
    error: q.error,
  }
}

//
// cnpjDigits — normaliza CNPJ (remove pontos, barras, hifens) pra usar como
// chave de URL/selecao. Backend retorna "26.208.328/0001-91"; URL usa
// "26208328000191".
//
export function cnpjDigits(cnpj: string): string {
  return cnpj.replace(/\D/g, "")
}
