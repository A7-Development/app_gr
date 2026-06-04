"use client"

/**
 * React Query hooks da gestao admin de PROVEDORES DE DADOS (system maintainer).
 * Espelha backend/app/modules/admin/api/data_provider_credentials.py.
 * Endpoints retornam 403 se o usuario nao for do tenant mantenedor.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  adminDataProviders,
  type DataProviderCredentialCreatePayload,
  type DataProviderCredentialUpdatePayload,
} from "@/lib/api-client"

const KEYS = {
  providers: ["admin", "data", "providers"] as const,
  credentials: ["admin", "data", "credentials"] as const,
}

export function useDataProviders() {
  return useQuery({
    queryKey: KEYS.providers,
    queryFn: () => adminDataProviders.providers(),
    staleTime: 60 * 1000,
  })
}

export function useDataProviderCredentials() {
  return useQuery({
    queryKey: KEYS.credentials,
    queryFn: () => adminDataProviders.credentials.list(),
    staleTime: 30 * 1000,
  })
}

export function useCreateDataProviderCredential() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: DataProviderCredentialCreatePayload) =>
      adminDataProviders.credentials.create(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEYS.credentials }),
  })
}

export function useUpdateDataProviderCredential() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string
      payload: DataProviderCredentialUpdatePayload
    }) => adminDataProviders.credentials.update(id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEYS.credentials }),
  })
}

export function useDeleteDataProviderCredential() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => adminDataProviders.credentials.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEYS.credentials }),
  })
}
