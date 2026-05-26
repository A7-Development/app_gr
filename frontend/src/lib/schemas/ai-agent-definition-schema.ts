// Schemas Zod para forms de admin/ia/agents (F2.c.3).
//
// Agent Definition = composto persona + expertises + prompt + modelo
// (CLAUDE.md §19.12). Schema espelha AgentDefinitionCreate /
// AgentDefinitionUpdate do backend.

import { z } from "zod"

import type {
  AIAgentDefinitionCreatePayload,
  AIAgentDefinitionUpdatePayload,
} from "@/lib/api-client"

const NAME_REGEX = /^[a-z0-9]+(\.[a-z0-9_]+)*$/
const MODULE_REGEX = /^[a-z0-9_]+$/

export const agentDefinitionCreateSchema = z.object({
  name: z
    .string()
    .min(1, "Nome obrigatorio.")
    .max(128, "Maximo 128 caracteres.")
    .regex(
      NAME_REGEX,
      "Use formato canonico: minusculas, pontos e underscores. Ex: 'credito.analista_dossie'.",
    ),
  module: z
    .string()
    .min(1, "Modulo obrigatorio.")
    .max(32, "Maximo 32 caracteres.")
    .regex(
      MODULE_REGEX,
      "Use minusculas e underscores. Ex: 'credito', 'controladoria', 'risco'.",
    ),
  persona_id: z.string().uuid().nullable().optional(),
  expertise_ids: z.array(z.string().uuid()).optional(),
  prompt_name: z
    .string()
    .min(1, "Prompt obrigatorio.")
    .max(128, "Maximo 128 caracteres."),
  model: z.string().max(64).nullable().optional(),
  fallback_model: z.string().max(64).nullable().optional(),
  temperature: z.number().min(0).max(2).nullable().optional(),
  max_tokens: z.number().int().min(1).max(200000).nullable().optional(),
  cross_module: z.boolean().optional(),
  // null = herda default do CATALOG (spec.tools); [] = sem tools; [...] = override.
  allowed_tools: z.array(z.string()).nullable().optional(),
  credit_hint: z.number().int().min(0).nullable().optional(),
})

export const agentDefinitionUpdateSchema = z.object({
  persona_id: z.string().uuid().nullable().optional(),
  expertise_ids: z.array(z.string().uuid()).optional(),
  prompt_name: z.string().min(1).max(128).optional(),
  model: z.string().max(64).nullable().optional(),
  fallback_model: z.string().max(64).nullable().optional(),
  temperature: z.number().min(0).max(2).nullable().optional(),
  max_tokens: z.number().int().min(1).max(200000).nullable().optional(),
  cross_module: z.boolean().optional(),
  allowed_tools: z.array(z.string()).nullable().optional(),
  credit_hint: z.number().int().min(0).nullable().optional(),
})

export type AgentDefinitionCreateValues = z.infer<
  typeof agentDefinitionCreateSchema
>
export type AgentDefinitionUpdateValues = z.infer<
  typeof agentDefinitionUpdateSchema
>

// Modulos canonicos (CLAUDE.md §11.1).
export const MODULE_OPTIONS = [
  "bi",
  "cadastros",
  "operacoes",
  "credito",
  "controladoria",
  "risco",
  "integracoes",
  "laboratorio",
  "admin",
] as const

export function buildCreatePayload(
  values: AgentDefinitionCreateValues,
): AIAgentDefinitionCreatePayload {
  return {
    name: values.name.trim(),
    module: values.module.trim(),
    persona_id: values.persona_id ?? null,
    expertise_ids: values.expertise_ids?.length
      ? values.expertise_ids
      : null,
    prompt_name: values.prompt_name.trim(),
    model: values.model?.trim() || null,
    fallback_model: values.fallback_model?.trim() || null,
    temperature: values.temperature ?? null,
    max_tokens: values.max_tokens ?? null,
    cross_module: values.cross_module ?? false,
    // null = herda do CATALOG; [] (override ligado, nada escolhido) preservado.
    allowed_tools: values.allowed_tools ?? null,
    credit_hint: values.credit_hint ?? null,
  }
}

export function buildUpdatePayload(
  values: AgentDefinitionUpdateValues,
): AIAgentDefinitionUpdatePayload {
  const payload: AIAgentDefinitionUpdatePayload = {}
  if (values.persona_id !== undefined) payload.persona_id = values.persona_id
  if (values.expertise_ids !== undefined)
    payload.expertise_ids = values.expertise_ids
  if (values.prompt_name !== undefined)
    payload.prompt_name = values.prompt_name.trim()
  if (values.model !== undefined) payload.model = values.model
  if (values.fallback_model !== undefined)
    payload.fallback_model = values.fallback_model
  if (values.temperature !== undefined) payload.temperature = values.temperature
  if (values.max_tokens !== undefined) payload.max_tokens = values.max_tokens
  if (values.cross_module !== undefined)
    payload.cross_module = values.cross_module
  // null = herda da base; [] = zera; [...] = override. Enviado as-is.
  if (values.allowed_tools !== undefined)
    payload.allowed_tools = values.allowed_tools
  if (values.credit_hint !== undefined) payload.credit_hint = values.credit_hint
  return payload
}
