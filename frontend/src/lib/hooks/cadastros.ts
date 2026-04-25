"use client"

/**
 * React Query hooks do modulo cadastros.
 * Espelham os endpoints em backend/app/modules/cadastros/api/.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  cadastros,
  type UACreatePayload,
  type UAListFilters,
  type UAUpdatePayload,
} from "@/lib/api-client"

const KEYS = {
  uas: (filters: UAListFilters) => ["cadastros", "uas", filters] as const,
  ua: (id: string) => ["cadastros", "ua", id] as const,
}

export function useUAs(filters: UAListFilters = {}) {
  return useQuery({
    queryKey: KEYS.uas(filters),
    queryFn: () => cadastros.listUAs(filters),
  })
}

export function useUA(id: string | null) {
  return useQuery({
    queryKey: id ? KEYS.ua(id) : ["cadastros", "ua", "none"],
    queryFn: () => cadastros.getUA(id!),
    enabled: !!id,
  })
}

export function useCreateUA() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: UACreatePayload) => cadastros.createUA(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cadastros", "uas"] })
    },
  })
}

export function useUpdateUA(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: UAUpdatePayload) => cadastros.updateUA(id, payload),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["cadastros", "uas"] })
      qc.setQueryData(KEYS.ua(id), data)
    },
  })
}

export function useDeleteUA() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => cadastros.deleteUA(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cadastros", "uas"] })
    },
  })
}
