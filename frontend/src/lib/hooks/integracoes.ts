"use client"

/**
 * React Query hooks do modulo integracoes.
 * Espelham os endpoints em backend/app/modules/integracoes/routers/sources.py.
 *
 * Multi-UA (Phase F): hooks de detail/test/sync/setEnabled aceitam `uaId`
 * opcional pra selecionar a credencial da UA especifica. Sem `uaId`, casa
 * a linha legacy (UA=NULL) — mantem retrocompat ate todos os call sites
 * informarem UA explicitamente.
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
  detail: (st: SourceTypeId, env: Environment, ua?: string | null) =>
    ["integracoes", "source", st, env, ua ?? null] as const,
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
  uaId?: string | null,
) {
  return useQuery({
    queryKey: sourceType
      ? KEYS.detail(sourceType, environment, uaId)
      : ["integracoes", "source", "none"],
    queryFn: () => integracoes.getSource(sourceType!, environment, uaId),
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
      qc.setQueryData(
        KEYS.detail(sourceType, data.environment, data.unidade_administrativa_id),
        data,
      )
    },
  })
}

export function useSetSourceEnabled(sourceType: SourceTypeId) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: {
      enabled: boolean
      environment?: Environment
      uaId?: string | null
    }) =>
      integracoes.setEnabled(
        sourceType,
        vars.enabled,
        vars.environment ?? "production",
        vars.uaId,
      ),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["integracoes"] })
      qc.setQueryData(
        KEYS.detail(sourceType, data.environment, data.unidade_administrativa_id),
        data,
      )
    },
  })
}

export function useTestSource(sourceType: SourceTypeId) {
  return useMutation({
    mutationFn: (vars: {
      environment?: Environment
      uaId?: string | null
    }) =>
      integracoes.test(
        sourceType,
        vars.environment ?? "production",
        vars.uaId,
      ),
  })
}

export function useSyncSource(sourceType: SourceTypeId) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: {
      environment?: Environment
      uaId?: string | null
    }) =>
      integracoes.sync(
        sourceType,
        vars.environment ?? "production",
        vars.uaId,
      ),
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
