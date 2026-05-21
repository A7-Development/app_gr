// Schemas Zod para forms de admin/ia/personas (F2.c.1).
//
// Persona = papel reutilizavel injetado no system prompt (CLAUDE.md §19.12).
// Versionamento: edicao cria nova versao; active pointer seleciona qual
// roda. Schema espelha PersonaCreate / PersonaUpdate do backend
// (app/shared/ai/schemas/persona.py).

import { z } from "zod"

import type {
  AIPersonaCreatePayload,
  AIPersonaUpdatePayload,
} from "@/lib/api-client"

// Restringe `name` a slug-like: lowercase + dots + underscores + alnum.
// Ex: "credito.analista_financial", "controladoria.controller_senior".
const NAME_REGEX = /^[a-z0-9]+(\.[a-z0-9_]+)*$/

export const personaCreateSchema = z.object({
  name: z
    .string()
    .min(1, "Nome obrigatorio.")
    .max(128, "Maximo 128 caracteres.")
    .regex(
      NAME_REGEX,
      "Use formato canonico: minusculas, pontos e underscores. Ex: 'credito.analista_financial'.",
    ),
  display_name: z
    .string()
    .min(1, "Nome de exibicao obrigatorio.")
    .max(200, "Maximo 200 caracteres."),
  role_block: z
    .string()
    .min(1, "Texto da persona obrigatorio.")
    .max(20000, "Texto excede 20k caracteres — considere migrar pra expertise."),
  description: z.string().max(2000).optional().or(z.literal("")),
  expertise_domains: z.array(z.string().max(64)).max(20).optional(),
})

export const personaUpdateSchema = z.object({
  display_name: z.string().min(1).max(200).optional(),
  role_block: z.string().min(1).max(20000).optional(),
  description: z.string().max(2000).optional().or(z.literal("")),
  expertise_domains: z.array(z.string().max(64)).max(20).optional(),
})

export type PersonaCreateValues = z.infer<typeof personaCreateSchema>
export type PersonaUpdateValues = z.infer<typeof personaUpdateSchema>

/**
 * Convert form values to API payload — strips empty strings, normalizes arrays.
 */
export function buildCreatePayload(
  values: PersonaCreateValues,
): AIPersonaCreatePayload {
  return {
    name: values.name.trim(),
    display_name: values.display_name.trim(),
    role_block: values.role_block,
    description: values.description?.trim() || undefined,
    expertise_domains: values.expertise_domains?.length
      ? values.expertise_domains
      : undefined,
  }
}

export function buildUpdatePayload(
  values: PersonaUpdateValues,
): AIPersonaUpdatePayload {
  const payload: AIPersonaUpdatePayload = {}
  if (values.display_name !== undefined) {
    payload.display_name = values.display_name.trim()
  }
  if (values.role_block !== undefined) {
    payload.role_block = values.role_block
  }
  if (values.description !== undefined) {
    payload.description = values.description.trim() || undefined
  }
  if (values.expertise_domains !== undefined) {
    payload.expertise_domains = values.expertise_domains.length
      ? values.expertise_domains
      : undefined
  }
  return payload
}
