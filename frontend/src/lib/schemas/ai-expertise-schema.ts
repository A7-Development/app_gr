// Schemas Zod para forms de admin/ia/expertises (F2.c.2).
//
// Expertise = knowledge pack injetado no system prompt (CLAUDE.md §19.12).
// Define O QUE o agente sabe (embasamento teorico aplicado).
// Schema espelha ExpertiseCreate / ExpertiseUpdate do backend
// (app/shared/ai/schemas/expertise.py).

import { z } from "zod"

import type {
  AIExpertiseCreatePayload,
  AIExpertiseReference,
  AIExpertiseUpdatePayload,
} from "@/lib/api-client"

const NAME_REGEX = /^[a-z0-9]+(\.[a-z0-9_]+)*$/

const referenceSchema = z.object({
  url: z.string().min(1).max(500),
  label: z.string().min(1).max(200),
  kind: z.string().max(32).optional(),
})

export const expertiseCreateSchema = z.object({
  name: z
    .string()
    .min(1, "Nome obrigatorio.")
    .max(128, "Maximo 128 caracteres.")
    .regex(
      NAME_REGEX,
      "Use formato canonico: minusculas, pontos e underscores. Ex: 'contabilidade.fidc'.",
    ),
  display_name: z
    .string()
    .min(1, "Nome de exibicao obrigatorio.")
    .max(200, "Maximo 200 caracteres."),
  domain: z
    .string()
    .min(1, "Dominio obrigatorio.")
    .max(64, "Maximo 64 caracteres."),
  knowledge_text: z
    .string()
    .min(1, "Texto de conhecimento obrigatorio.")
    .max(50000, "Texto excede 50k caracteres — considere split em expertises menores."),
  reference_urls: z.array(referenceSchema).optional(),
})

export const expertiseUpdateSchema = z.object({
  display_name: z.string().min(1).max(200).optional(),
  domain: z.string().min(1).max(64).optional(),
  knowledge_text: z.string().min(1).max(50000).optional(),
  reference_urls: z.array(referenceSchema).optional(),
})

export type ExpertiseCreateValues = z.infer<typeof expertiseCreateSchema>
export type ExpertiseUpdateValues = z.infer<typeof expertiseUpdateSchema>

// Dominios sugeridos (free-form, mas com lista pra autocomplete).
export const DOMAIN_SUGGESTIONS = [
  "contabilidade",
  "credito",
  "risco",
  "regulatorio",
  "mercado",
  "compliance",
  "operacoes",
] as const

/**
 * Parse texto com 1 referencia por linha no formato `url | label` ou
 * `url | label | kind`. Linhas vazias ou mal-formadas sao puladas.
 */
export function parseReferencesInput(text: string): AIExpertiseReference[] {
  const out: AIExpertiseReference[] = []
  for (const raw of text.split("\n")) {
    const line = raw.trim()
    if (!line) continue
    const parts = line.split("|").map((p) => p.trim())
    if (parts.length < 2 || !parts[0] || !parts[1]) continue
    const ref: AIExpertiseReference = { url: parts[0], label: parts[1] }
    if (parts[2]) ref.kind = parts[2]
    out.push(ref)
  }
  return out
}

/**
 * Inverte parseReferencesInput — string `url | label | kind?` por linha.
 */
export function referencesToInput(
  refs: AIExpertiseReference[] | null | undefined,
): string {
  return (refs ?? [])
    .map((r) =>
      r.kind ? `${r.url} | ${r.label} | ${r.kind}` : `${r.url} | ${r.label}`,
    )
    .join("\n")
}

export function buildCreatePayload(
  values: ExpertiseCreateValues,
): AIExpertiseCreatePayload {
  return {
    name: values.name.trim(),
    display_name: values.display_name.trim(),
    domain: values.domain.trim(),
    knowledge_text: values.knowledge_text,
    reference_urls: values.reference_urls?.length
      ? values.reference_urls
      : undefined,
  }
}

export function buildUpdatePayload(
  values: ExpertiseUpdateValues,
): AIExpertiseUpdatePayload {
  const payload: AIExpertiseUpdatePayload = {}
  if (values.display_name !== undefined) {
    payload.display_name = values.display_name.trim()
  }
  if (values.domain !== undefined) {
    payload.domain = values.domain.trim()
  }
  if (values.knowledge_text !== undefined) {
    payload.knowledge_text = values.knowledge_text
  }
  if (values.reference_urls !== undefined) {
    payload.reference_urls = values.reference_urls.length
      ? values.reference_urls
      : undefined
  }
  return payload
}
