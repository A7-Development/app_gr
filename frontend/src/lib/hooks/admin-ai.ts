"use client"

/**
 * React Query hooks da gestao admin de IA (system maintainer).
 * Espelha endpoints em backend/app/modules/admin/api/.
 *
 * Todos os endpoints retornam 403 se o usuario nao for do tenant
 * mantenedor (ver core/system_maintainer_guard.py). UI esconde a
 * navegacao para usuarios sem permissao via `tenant.is_system_maintainer`
 * em /auth/me.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  adminAI,
  type AIAgentConfigRead,
  type AIAgentConfigUpdatePayload,
  type AIPersonaCreatePayload,
  type AIPersonaDetail,
  type AIPersonaUpdatePayload,
  type AIPromptCreatePayload,
  type AIPromptDetail,
  type AIPromptUpdatePayload,
  type AIProviderCredentialCreatePayload,
  type AIProviderCredentialRead,
  type AIProviderCredentialUpdatePayload,
} from "@/lib/api-client"

const KEYS = {
  providers: ["admin", "ai", "providers"] as const,
  prompts: (includeArchived: boolean) =>
    ["admin", "ai", "prompts", { includeArchived }] as const,
  prompt: (id: string) => ["admin", "ai", "prompt", id] as const,
  agents: ["admin", "ai", "agents"] as const,
  agentModels: ["admin", "ai", "agents", "models"] as const,
}

// ───────────────────────────────────────────────────────────────────────────
// Listagem
// ───────────────────────────────────────────────────────────────────────────

export function useProviders() {
  return useQuery({
    queryKey: KEYS.providers,
    queryFn: () => adminAI.providers.list(),
    staleTime: 30 * 1000,
  })
}

// ───────────────────────────────────────────────────────────────────────────
// Mutacoes — invalidam cache de listagem ao concluir.
// ───────────────────────────────────────────────────────────────────────────

export function useCreateProvider() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: AIProviderCredentialCreatePayload) =>
      adminAI.providers.create(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEYS.providers }),
  })
}

export function useUpdateProvider() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string
      payload: AIProviderCredentialUpdatePayload
    }) => adminAI.providers.update(id, payload),
    onSuccess: (updated: AIProviderCredentialRead) => {
      qc.invalidateQueries({ queryKey: KEYS.providers })
      // Atualiza otimisticamente o cache (UX mais responsiva).
      qc.setQueryData<AIProviderCredentialRead[]>(KEYS.providers, (prev) =>
        prev?.map((p) => (p.id === updated.id ? updated : p)) ?? prev,
      )
    },
  })
}

export function useDeleteProvider() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => adminAI.providers.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEYS.providers }),
  })
}

// ───────────────────────────────────────────────────────────────────────────
// Prompts
// ───────────────────────────────────────────────────────────────────────────

export function usePrompts(opts: { includeArchived?: boolean } = {}) {
  const includeArchived = opts.includeArchived ?? false
  return useQuery({
    queryKey: KEYS.prompts(includeArchived),
    queryFn: () => adminAI.prompts.list(includeArchived),
    staleTime: 30 * 1000,
  })
}

export function usePromptDetail(id: string | null) {
  return useQuery({
    queryKey: KEYS.prompt(id ?? ""),
    queryFn: () => adminAI.prompts.get(id!),
    enabled: !!id,
    staleTime: 30 * 1000,
  })
}

export function useCreatePrompt() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: AIPromptCreatePayload) =>
      adminAI.prompts.create(payload),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["admin", "ai", "prompts"] }),
  })
}

export function useUpdatePrompt() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: AIPromptUpdatePayload }) =>
      adminAI.prompts.update(id, payload),
    onSuccess: (created: AIPromptDetail) => {
      qc.invalidateQueries({ queryKey: ["admin", "ai", "prompts"] })
      qc.invalidateQueries({ queryKey: KEYS.prompt(created.id) })
    },
  })
}

export function useActivatePromptVersion() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ name, versionId }: { name: string; versionId: string }) =>
      adminAI.prompts.activate(name, versionId),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["admin", "ai", "prompts"] }),
  })
}

export function useArchivePrompt() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => adminAI.prompts.archive(id),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["admin", "ai", "prompts"] }),
  })
}

export function usePreviewPrompt() {
  return useMutation({
    mutationFn: ({ id, context }: { id: string; context: Record<string, string> }) =>
      adminAI.prompts.preview(id, context),
  })
}

// ───────────────────────────────────────────────────────────────────────────
// Personas (F2.c.1 — CLAUDE.md §19.12)
// ───────────────────────────────────────────────────────────────────────────

const PERSONA_KEYS = {
  list: (includeArchived: boolean) =>
    ["admin", "ai", "personas", { includeArchived }] as const,
  detail: (id: string) => ["admin", "ai", "personas", id] as const,
}

export function usePersonas(opts: { includeArchived?: boolean } = {}) {
  const includeArchived = opts.includeArchived ?? false
  return useQuery({
    queryKey: PERSONA_KEYS.list(includeArchived),
    queryFn: () => adminAI.personas.list(includeArchived),
    staleTime: 30 * 1000,
  })
}

export function usePersonaDetail(id: string | null) {
  return useQuery({
    queryKey: PERSONA_KEYS.detail(id ?? ""),
    queryFn: () => adminAI.personas.get(id!),
    enabled: !!id,
    staleTime: 30 * 1000,
  })
}

export function useCreatePersona() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: AIPersonaCreatePayload) =>
      adminAI.personas.create(payload),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["admin", "ai", "personas"] }),
  })
}

export function useUpdatePersona() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string
      payload: AIPersonaUpdatePayload
    }) => adminAI.personas.update(id, payload),
    onSuccess: (created: AIPersonaDetail) => {
      qc.invalidateQueries({ queryKey: ["admin", "ai", "personas"] })
      qc.invalidateQueries({ queryKey: PERSONA_KEYS.detail(created.id) })
    },
  })
}

export function useActivatePersonaVersion() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ name, versionId }: { name: string; versionId: string }) =>
      adminAI.personas.activate(name, versionId),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["admin", "ai", "personas"] }),
  })
}

export function useArchivePersona() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => adminAI.personas.archive(id),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["admin", "ai", "personas"] }),
  })
}

// ───────────────────────────────────────────────────────────────────────────
// Specialist Agents — model override por agente
// ───────────────────────────────────────────────────────────────────────────

export function useAdminAgents() {
  return useQuery({
    queryKey: KEYS.agents,
    queryFn: () => adminAI.agents.list(),
    staleTime: 30 * 1000,
  })
}

export function useAdminAgentModels() {
  return useQuery({
    queryKey: KEYS.agentModels,
    queryFn: () => adminAI.agents.listModels(),
    // Lista curada — muda raramente. Pode cachear bem.
    staleTime: 15 * 60 * 1000,
  })
}

export function useUpdateAdminAgent() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      agentName,
      payload,
    }: {
      agentName: string
      payload: AIAgentConfigUpdatePayload
    }) => adminAI.agents.update(agentName, payload),
    onSuccess: (updated: AIAgentConfigRead) => {
      // Atualiza otimisticamente o cache da listagem.
      qc.setQueryData<AIAgentConfigRead[]>(KEYS.agents, (prev) =>
        prev?.map((a) => (a.agent_name === updated.agent_name ? updated : a)) ??
        prev,
      )
    },
  })
}
