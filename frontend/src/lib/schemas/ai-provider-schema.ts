// src/lib/schemas/ai-provider-schema.ts
//
// Schemas zod compartilhados para o form de credenciais LLM (admin IA).
// Espelha `app/shared/ai/schemas/ai.py::ProviderCredential{Create,Update}` no backend.

import { z } from "zod"

// ───────────────────────────────────────────────────────────────────────────
// Provider enum espelhado de backend/app/core/enums.py::AIProvider
// ───────────────────────────────────────────────────────────────────────────

export const AI_PROVIDERS = ["openai", "anthropic"] as const
export type AIProviderId = (typeof AI_PROVIDERS)[number]

export const AI_PROVIDER_LABEL: Record<AIProviderId, string> = {
  openai: "OpenAI",
  anthropic: "Anthropic",
}

// ───────────────────────────────────────────────────────────────────────────
// Schema base — campos comuns entre criar e editar.
// ───────────────────────────────────────────────────────────────────────────

const aliasSchema = z
  .string()
  .min(2, "Alias precisa ter ao menos 2 caracteres.")
  .max(64, "Alias muito longo (max 64).")
  .regex(
    /^[a-z0-9-_]+$/i,
    "Use apenas letras, numeros, hifen e underline (sem espaco).",
  )

const apiKeyOptionalSchema = z
  .string()
  .max(512, "API key suspeita: muito longa.")
  .optional()
  .refine(
    (v) => !v || v.length >= 8,
    "API key precisa ter ao menos 8 caracteres.",
  )

const orgIdSchema = z
  .string()
  .max(128, "Org id muito longo.")
  .optional()

const notesSchema = z
  .string()
  .max(512, "Notas muito longas (max 512).")
  .optional()

// ───────────────────────────────────────────────────────────────────────────
// Schema de CRIACAO — api_key obrigatoria.
// ───────────────────────────────────────────────────────────────────────────

export const providerCreateSchema = z.object({
  provider: z.enum(AI_PROVIDERS),
  alias: aliasSchema,
  api_key: z
    .string()
    .min(8, "API key precisa ter ao menos 8 caracteres.")
    .max(512, "API key suspeita: muito longa."),
  org_id: orgIdSchema,
  zdr_enabled: z.boolean(),
  notes: notesSchema,
})

export type ProviderCreateValues = z.infer<typeof providerCreateSchema>

// ───────────────────────────────────────────────────────────────────────────
// Schema de EDICAO — api_key opcional (mantem mascara se vazio).
//
// `provider` e imutavel apos criacao (mudar provider de uma credencial
// existente nao faz sentido — crie uma nova). UI desabilita o campo;
// o schema simplesmente ignora.
// ───────────────────────────────────────────────────────────────────────────

export const providerUpdateSchema = z.object({
  api_key: apiKeyOptionalSchema,
  org_id: orgIdSchema,
  zdr_enabled: z.boolean(),
  active: z.boolean(),
  notes: notesSchema,
})

export type ProviderUpdateValues = z.infer<typeof providerUpdateSchema>

// ───────────────────────────────────────────────────────────────────────────
// Helper: payload final para PUT — remove api_key se vazia (mantem persistido).
// ───────────────────────────────────────────────────────────────────────────

export function buildUpdatePayload(values: ProviderUpdateValues): {
  api_key?: string
  org_id?: string | null
  zdr_enabled: boolean
  active: boolean
  notes?: string | null
} {
  const out: ReturnType<typeof buildUpdatePayload> = {
    zdr_enabled: values.zdr_enabled,
    active: values.active,
  }
  if (values.api_key && values.api_key.trim().length > 0) {
    out.api_key = values.api_key.trim()
  }
  if (values.org_id !== undefined) {
    out.org_id = values.org_id.trim() || null
  }
  if (values.notes !== undefined) {
    out.notes = values.notes.trim() || null
  }
  return out
}
