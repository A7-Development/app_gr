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
  type EndpointConfigPayload,
  type EndpointDetail,
  type Environment,
  type SourceTypeId,
} from "@/lib/api-client"

const KEYS = {
  list: (env: Environment) => ["integracoes", "sources", env] as const,
  detail: (st: SourceTypeId, env: Environment, ua?: string | null) =>
    ["integracoes", "source", st, env, ua ?? null] as const,
  runs: (st: SourceTypeId, limit: number) =>
    ["integracoes", "runs", st, limit] as const,
  endpoints: (st: SourceTypeId, env: Environment, ua?: string | null) =>
    ["integracoes", "endpoints", st, env, ua ?? null] as const,
  coverage: (st: SourceTypeId, rangeDays: number, ua?: string | null) =>
    ["integracoes", "coverage", st, rangeDays, ua ?? null] as const,
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

// ───────────────────────────────────────────────────────────────────────────
// Endpoints (cadência fina) — CLAUDE.md §13
// ───────────────────────────────────────────────────────────────────────────

export function useSourceEndpoints(
  sourceType: SourceTypeId | null,
  environment: Environment = "production",
  uaId?: string | null,
) {
  return useQuery({
    queryKey: sourceType
      ? KEYS.endpoints(sourceType, environment, uaId)
      : ["integracoes", "endpoints", "none"],
    queryFn: () => integracoes.listEndpoints(sourceType!, environment, uaId),
    enabled: !!sourceType,
    // Polling combinado: 5s enquanto houver sync em curso (badge "Em curso"
    // transita pra OK/Erro sozinho), 30s caso contrario (captura sync
    // disparado pelo scheduler sem interacao do usuario). Aba sem foco
    // nao polla (refetchIntervalInBackground default false).
    refetchInterval: (query) => {
      const rows = query.state.data as EndpointDetail[] | undefined
      const hasInProgress = rows?.some(
        (e) => e.last_sync_status === "em_progresso",
      )
      return hasInProgress ? 5_000 : 30_000
    },
  })
}

export function useUpdateEndpoint(sourceType: SourceTypeId) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: {
      endpointName: string
      payload: EndpointConfigPayload
    }) => integracoes.updateEndpoint(sourceType, vars.endpointName, vars.payload),
    onSuccess: () => {
      // Invalida toda a árvore de endpoints — listagem e detail são
      // recarregados (last_sync_* pode mudar pra qualquer linha de TSEC).
      qc.invalidateQueries({ queryKey: ["integracoes", "endpoints", sourceType] })
    },
  })
}

export function useSyncEndpoint(sourceType: SourceTypeId) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: {
      endpointName: string
      environment?: Environment
      uaId?: string | null
    }) =>
      integracoes.syncEndpoint(
        sourceType,
        vars.endpointName,
        vars.environment ?? "production",
        vars.uaId,
      ),
    // Optimistic: pinta a row como "em_progresso" no clique, sem esperar
    // o backend gravar TSEC + o poll de 30s rebater. Janela cega entre
    // POST in-flight e proximo poll caia para zero.
    onMutate: async (vars) => {
      const env = vars.environment ?? "production"
      const key = KEYS.endpoints(sourceType, env, vars.uaId)
      await qc.cancelQueries({ queryKey: key })
      const previous = qc.getQueryData<EndpointDetail[]>(key)
      const nowIso = new Date().toISOString()
      qc.setQueryData<EndpointDetail[]>(key, (old) =>
        old?.map((e) =>
          e.name === vars.endpointName
            ? {
                ...e,
                last_sync_status: "em_progresso",
                last_sync_started_at: nowIso,
                last_sync_error: null,
              }
            : e,
        ),
      )
      return { previous, key }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous && ctx?.key) {
        qc.setQueryData(ctx.key, ctx.previous)
      }
    },
    onSettled: (_data, _err, vars) => {
      const env = vars.environment ?? "production"
      qc.invalidateQueries({
        queryKey: KEYS.endpoints(sourceType, env, vars.uaId),
      })
      qc.invalidateQueries({ queryKey: KEYS.runs(sourceType, 50) })
    },
  })
}

export function useSourceCoverage(
  sourceType: SourceTypeId | null,
  rangeDays: number = 90,
  uaId?: string | null,
) {
  return useQuery({
    queryKey: sourceType
      ? KEYS.coverage(sourceType, rangeDays, uaId)
      : ["integracoes", "coverage", "none"],
    queryFn: () => integracoes.coverage(sourceType!, { rangeDays, uaId }),
    enabled: !!sourceType,
    staleTime: 5 * 60_000, // 5min — cobertura nao muda em segundos
  })
}
