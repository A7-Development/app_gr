// Schemas Zod para forms de admin/ia/mcp (Fase 3 — copiloto-mcp).
//
// Servidor MCP = primitivo da camada agentica (CLAUDE.md §19): catalogo
// DB-first versionado (mcp_server + mcp_server_active). Espelha
// McpServerCreate / McpServerUpdate do backend.
//
// Campos "texto" do form (auth_header_map_text, allowed_tools_text) sao
// convertidos pros shapes canonicos nos builders abaixo.

import { z } from "zod"

import type {
  AIMcpServerCreatePayload,
  AIMcpServerUpdatePayload,
} from "@/lib/api-client"

const NAME_REGEX = /^[a-z0-9_-]+$/
const UUID_REGEX =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/** true se o texto e vazio OU um objeto JSON {string: string}. */
function isEmptyOrHeaderMapJson(value: string): boolean {
  const trimmed = value.trim()
  if (!trimmed) return true
  try {
    const parsed: unknown = JSON.parse(trimmed)
    if (
      typeof parsed !== "object" ||
      parsed === null ||
      Array.isArray(parsed)
    ) {
      return false
    }
    return Object.values(parsed as Record<string, unknown>).every(
      (v) => typeof v === "string",
    )
  } catch {
    return false
  }
}

const sharedFields = {
  url: z
    .string()
    .min(1, "URL obrigatoria.")
    .max(512, "Maximo 512 caracteres."),
  transport: z.enum(["http", "stdio"]),
  // "" = cross-modulo (vira null no payload).
  module: z.string().max(32).optional(),
  credential_id: z
    .string()
    .trim()
    .refine(
      (v) => v === "" || UUID_REGEX.test(v),
      "Informe um UUID valido (ou deixe vazio).",
    ),
  auth_header_map_text: z
    .string()
    .refine(
      isEmptyOrHeaderMapJson,
      'JSON invalido — use um objeto {"Header": "valor"}.',
    ),
  // Um nome de tool por linha.
  allowed_tools_text: z.string(),
  mode: z.enum(["ephemeral", "materialized"]),
  cost_hint: z.enum(["cheap", "medium", "expensive"]),
  max_calls_per_turn: z
    .number("Informe um numero.")
    .int("Use um inteiro.")
    .min(1, "Minimo 1.")
    .max(100, "Maximo 100."),
  tool_result_max_chars: z
    .number("Informe um numero.")
    .int("Use um inteiro.")
    .min(100, "Minimo 100.")
    .max(1_000_000, "Maximo 1.000.000."),
  description: z.string().optional(),
}

export const mcpServerCreateSchema = z.object({
  name: z
    .string()
    .min(1, "Nome obrigatorio.")
    .max(64, "Maximo 64 caracteres.")
    .regex(
      NAME_REGEX,
      "Use minusculas, digitos, underscore e hifen. Ex: 'bigdatacorp'.",
    ),
  ...sharedFields,
})

export const mcpServerUpdateSchema = z.object(sharedFields)

export type McpServerCreateValues = z.infer<typeof mcpServerCreateSchema>
export type McpServerUpdateValues = z.infer<typeof mcpServerUpdateSchema>

/** Converte o textarea (uma tool por linha) em string[] | null (null = todas). */
function parseAllowedTools(text: string): string[] | null {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of text.split(/\r?\n/)) {
    const trimmed = raw.trim()
    if (trimmed && !seen.has(trimmed)) {
      seen.add(trimmed)
      out.push(trimmed)
    }
  }
  return out.length > 0 ? out : null
}

function parseHeaderMap(text: string): Record<string, string> | null {
  const trimmed = text.trim()
  if (!trimmed) return null
  // Ja validado pelo schema — parse seguro.
  return JSON.parse(trimmed) as Record<string, string>
}

function sharedPayload(
  values: McpServerUpdateValues,
): Omit<AIMcpServerCreatePayload, "name"> {
  return {
    url: values.url.trim(),
    transport: values.transport,
    module: values.module?.trim() || null,
    credential_id: values.credential_id.trim() || null,
    auth_header_map: parseHeaderMap(values.auth_header_map_text),
    allowed_tools: parseAllowedTools(values.allowed_tools_text),
    mode: values.mode,
    cost_hint: values.cost_hint,
    max_calls_per_turn: values.max_calls_per_turn,
    tool_result_max_chars: values.tool_result_max_chars,
    description: values.description?.trim() || null,
  }
}

export function buildCreatePayload(
  values: McpServerCreateValues,
): AIMcpServerCreatePayload {
  return {
    name: values.name.trim(),
    ...sharedPayload(values),
  }
}

export function buildUpdatePayload(
  values: McpServerUpdateValues,
): AIMcpServerUpdatePayload {
  // O form de edicao carrega TODOS os campos preenchidos a partir da versao
  // base — enviamos o shape completo (o backend cria nova versao).
  return sharedPayload(values)
}
