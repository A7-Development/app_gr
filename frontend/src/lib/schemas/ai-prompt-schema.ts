// src/lib/schemas/ai-prompt-schema.ts
//
// Schemas zod para o admin de prompts (DB-backed, CLAUDE.md sec 19.4 v2).
// Espelha `app/shared/ai/schemas/ai.py::Prompt{Create,Update}` no backend.

import { z } from "zod"

export const CACHE_STRATEGIES = ["none", "after_system"] as const
export type CacheStrategy = (typeof CACHE_STRATEGIES)[number]

// Naming convention: <categoria>.<nome>  (ex.: chat.fidc_geral, insight.carteira_3bullets).
// Letras minusculas, numeros, underline; UM ponto separando.
const NAME_REGEX = /^[a-z0-9_]+\.[a-z0-9_]+$/

// ───────────────────────────────────────────────────────────────────────────
// CREATE — cria nova familia (vira v1).
// ───────────────────────────────────────────────────────────────────────────

export const promptCreateSchema = z.object({
  name: z
    .string()
    .min(3, "Nome muito curto.")
    .max(128, "Nome muito longo.")
    .regex(NAME_REGEX, "Use formato 'categoria.nome' (minusculas, sem espaco)."),
  system_text: z.string().min(10, "System text precisa ter ao menos 10 caracteres."),
  user_context_template: z.string().optional(),
  assistant_prime: z.string().optional(),
  model: z.string().min(1).max(64),
  fallback_model: z.string().max(64).optional(),
  temperature: z.number().min(0).max(2),
  max_tokens: z.number().int().min(1).max(128_000),
  cache_strategy: z.enum(CACHE_STRATEGIES),
  description: z.string().max(2000).optional(),
})

export type PromptCreateValues = z.infer<typeof promptCreateSchema>

// ───────────────────────────────────────────────────────────────────────────
// UPDATE — cria nova VERSAO copiando atual + patches.
// Todos os campos sao opcionais; ausentes herdam do prompt base.
// ───────────────────────────────────────────────────────────────────────────

export const promptUpdateSchema = z.object({
  system_text: z
    .string()
    .min(10, "System text precisa ter ao menos 10 caracteres.")
    .optional(),
  user_context_template: z.string().optional(),
  assistant_prime: z.string().optional(),
  model: z.string().max(64).optional(),
  fallback_model: z.string().max(64).optional(),
  temperature: z.number().min(0).max(2).optional(),
  max_tokens: z.number().int().min(1).max(128_000).optional(),
  cache_strategy: z.enum(CACHE_STRATEGIES).optional(),
  description: z.string().max(2000).optional(),
})

export type PromptUpdateValues = z.infer<typeof promptUpdateSchema>

// ───────────────────────────────────────────────────────────────────────────
// Helper: payload final p/ UPDATE — remove strings vazias (mantem valor anterior).
// ───────────────────────────────────────────────────────────────────────────

export function buildUpdatePayload(values: PromptUpdateValues): PromptUpdateValues {
  const out: PromptUpdateValues = {}
  if (values.system_text?.trim()) out.system_text = values.system_text
  if (values.user_context_template !== undefined) {
    out.user_context_template = values.user_context_template.trim() || undefined
  }
  if (values.assistant_prime !== undefined) {
    out.assistant_prime = values.assistant_prime.trim() || undefined
  }
  if (values.model?.trim()) out.model = values.model.trim()
  if (values.fallback_model !== undefined) {
    out.fallback_model = values.fallback_model.trim() || undefined
  }
  if (values.temperature !== undefined) out.temperature = values.temperature
  if (values.max_tokens !== undefined) out.max_tokens = values.max_tokens
  if (values.cache_strategy !== undefined) out.cache_strategy = values.cache_strategy
  if (values.description !== undefined) {
    out.description = values.description.trim() || undefined
  }
  return out
}
