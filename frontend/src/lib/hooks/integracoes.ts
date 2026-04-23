"use client"

/**
 * React Query hooks do modulo integracoes.
 * Espelham os endpoints em backend/app/modules/integracoes/routers/sources.py.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  integracoes,
  type ConfigUpdatePayload,
  type Environment,
  type SourceTypeId,
} from "@/lib/api-client"

const KEYS = {
  list: (env: Environment) => ["integracoes", "sources", env] as const,
  detail: (st: SourceTypeId, env: Environment) =>
    ["integracoes", "source", st, env] as const,
  runs: (st: SourceTypeId, limit: number) =>
    ["integracoes", "runs", st, limit] as const,
}

export function useSources(environment: Environment = "production") {
  return useQuery({
    queryKey: KEYS.list(environment),
    queryFn: () => integracoes.listSources(environment),
  })
}

export function useSource(
  sourceType: SourceTypeId | null,
  environment: Environment = "production",
) {
  return useQuery({
    queryKey: sourceType
      ? KEYS.detail(sourceType, environment)
      : ["integracoes", "source", "none"],
    queryFn: () => integracoes.getSource(sourceType!, environment),
    enabled: !!sourceType,
  })
}

export function useUpdateSourceConfig(sourceType: SourceTypeId) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: ConfigUpdatePayload) =>
      integracoes.updateConfig(sourceType, payload),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["integracoes"] })
      qc.setQueryData(KEYS.detail(sourceType, data.environment), data)
    },
  })
}

export function useSetSourceEnabled(sourceType: SourceTypeId) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: { enabled: boolean; environment?: Environment }) =>
      integracoes.setEnabled(
        sourceType,
        vars.enabled,
        vars.environment ?? "production",
      ),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["integracoes"] })
      qc.setQueryData(KEYS.detail(sourceType, data.environment), data)
    },
  })
}

export function useTestSource(sourceType: SourceTypeId) {
  return useMutation({
    mutationFn: (environment: Environment = "production") =>
      integracoes.test(sourceType, environment),
  })
}

export function useSyncSource(sourceType: SourceTypeId) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (environment: Environment = "production") =>
      integracoes.sync(sourceType, environment),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["integracoes"] })
    },
  })
}

export function useSourceRuns(sourceType: SourceTypeId | null, limit = 50) {
  return useQuery({
    queryKey: sourceType
      ? KEYS.runs(sourceType, limit)
      : ["integracoes", "runs", "none"],
    queryFn: () => integracoes.runs(sourceType!, limit),
    enabled: !!sourceType,
  })
}
