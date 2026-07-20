"use client"

/**
 * Hook para gerenciar favoritos de fundo (CVM) do usuario logado.
 *
 * - Unica query compartilhada (`["bi","benchmark","favoritos"]`) — qualquer
 *   FavoritoStar na pagina consome o mesmo cache.
 * - Toggle otimista: atualiza o cache localmente antes do 204 voltar,
 *   reverte no onError + toast pt-BR.
 * - CNPJ e sempre digits-only (o backend normaliza, aqui so reforca).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback, useMemo } from "react"
import { toast } from "sonner"

import { biBenchmark, type FavoritosLista } from "@/lib/api-client"

const QUERY_KEY = ["bi", "benchmark", "favoritos"] as const

function cnpjDigits(cnpj: string): string {
  return cnpj.replace(/\D/g, "")
}

export function useFavoritos() {
  const qc = useQueryClient()

  const query = useQuery({
    queryKey: QUERY_KEY,
    queryFn: () => biBenchmark.favoritos(),
    staleTime: 5 * 60_000,
  })

  const set = useMemo(
    () => new Set(query.data?.favoritos.map((f) => f.cnpj) ?? []),
    [query.data],
  )

  const isFavorito = useCallback((cnpj: string) => set.has(cnpjDigits(cnpj)), [set])

  const mutation = useMutation({
    mutationFn: async (cnpj: string) => {
      const digits = cnpjDigits(cnpj)
      if (set.has(digits)) {
        await biBenchmark.removerFavorito(digits)
      } else {
        await biBenchmark.adicionarFavorito(digits)
      }
    },
    onMutate: async (cnpj) => {
      const digits = cnpjDigits(cnpj)
      await qc.cancelQueries({ queryKey: QUERY_KEY })
      const prev = qc.getQueryData<FavoritosLista>(QUERY_KEY)
      if (prev) {
        const jaFavorito = prev.favoritos.some((f) => f.cnpj === digits)
        const next: FavoritosLista = jaFavorito
          ? {
              favoritos: prev.favoritos.filter((f) => f.cnpj !== digits),
              total: Math.max(0, prev.total - 1),
            }
          : {
              favoritos: [
                {
                  cnpj: digits,
                  denom_social: null,
                  created_at: new Date().toISOString(),
                },
                ...prev.favoritos,
              ],
              total: prev.total + 1,
            }
        qc.setQueryData<FavoritosLista>(QUERY_KEY, next)
      }
      return { prev }
    },
    onError: (_err, _cnpj, ctx) => {
      if (ctx?.prev) qc.setQueryData<FavoritosLista>(QUERY_KEY, ctx.prev)
      toast.error("Nao foi possivel atualizar favorito")
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEY })
    },
  })

  return {
    favoritos: query.data?.favoritos ?? [],
    total: query.data?.total ?? 0,
    isLoading: query.isLoading,
    isFavorito,
    toggle: mutation.mutate,
    isPending: mutation.isPending,
  }
}
