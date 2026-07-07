"use client"

/**
 * React Query hooks da gestao de coletores (Strata Collector).
 * Espelha backend/app/modules/integracoes/routers/coletores.py
 * (require_module INTEGRACOES/ADMIN — 403 esconde a tela via sidebar).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  coletores,
  type ColetorCreatePayload,
  type ColetorRead,
  type ColetorUpdatePayload,
} from "@/lib/api-client"

const KEY = ["integracoes", "coletores"] as const

export function useColetores() {
  return useQuery({
    queryKey: KEY,
    queryFn: () => coletores.list(),
    // Heartbeat (last_seen_at) e o feedback vivo da tela — refetch curto.
    refetchInterval: 60 * 1000,
    staleTime: 30 * 1000,
  })
}

export function useCreateColetor() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: ColetorCreatePayload) => coletores.create(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function useUpdateColetor() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ColetorUpdatePayload }) =>
      coletores.update(id, payload),
    onSuccess: (updated: ColetorRead) => {
      qc.invalidateQueries({ queryKey: KEY })
      qc.setQueryData<ColetorRead[]>(KEY, (prev) =>
        prev?.map((c) => (c.id === updated.id ? updated : c)) ?? prev,
      )
    },
  })
}

export function useRotateColetor() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => coletores.rotate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function useRevokeColetor() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => coletores.revoke(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}
