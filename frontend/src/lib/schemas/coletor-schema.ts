import { z } from "zod"

import type {
  ColetorCreatePayload,
  ColetorRead,
  ColetorWatchConfig,
} from "@/lib/api-client"

/**
 * Schema do form de coletor (Strata Collector). Espelha a validacao do
 * backend (WatchItem/WatchConfigIn em routers/coletores.py) — o que passa
 * aqui passa la.
 */

export const watchSchema = z.object({
  path: z
    .string()
    .trim()
    .min(1, "Informe a pasta no servidor do cliente.")
    .max(512),
  glob: z.string().trim().max(64),
  source_label: z
    .string()
    .trim()
    .min(1, "Informe o rotulo da esteira.")
    .max(64)
    .regex(
      /^[a-z0-9_]+$/,
      "Somente minusculas, numeros e _ (ex.: cobranca_cnab).",
    ),
  zip: z.boolean(),
})

export const coletorFormSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "De um nome ao coletor (ex.: Servidor Bitfin).")
    .max(120),
  // Registrado com { valueAsNumber: true } no form — chega aqui como number.
  scan_interval_minutes: z
    .number("Use um numero inteiro de minutos.")
    .int("Use um numero inteiro de minutos.")
    .min(1, "Minimo 1 minuto.")
    .max(1440, "Maximo 1440 (1 dia)."),
  watches: z.array(watchSchema),
})

export type WatchValues = z.infer<typeof watchSchema>
export type ColetorFormValues = z.infer<typeof coletorFormSchema>

export const WATCH_DEFAULTS: WatchValues = {
  path: "",
  glob: "*",
  source_label: "",
  zip: false,
}

export const COLETOR_FORM_DEFAULTS: ColetorFormValues = {
  name: "",
  scan_interval_minutes: 5,
  watches: [WATCH_DEFAULTS],
}

export function toWatchConfig(values: ColetorFormValues): ColetorWatchConfig {
  return {
    scan_interval_minutes: values.scan_interval_minutes,
    watches: values.watches.map((w) => ({
      path: w.path.trim(),
      glob: w.glob.trim() || "*",
      source_label: w.source_label.trim(),
      ...(w.zip ? { container: "zip" as const } : {}),
    })),
  }
}

export function toCreatePayload(values: ColetorFormValues): ColetorCreatePayload {
  return {
    name: values.name.trim(),
    watch_config: toWatchConfig(values),
  }
}

export function fromColetor(coletor: ColetorRead): ColetorFormValues {
  const config = coletor.watch_config ?? {}
  return {
    name: coletor.name,
    scan_interval_minutes: config.scan_interval_minutes ?? 5,
    watches: (config.watches ?? []).map((w) => ({
      path: w.path,
      glob: w.glob ?? "*",
      source_label: w.source_label,
      zip: w.container === "zip",
    })),
  }
}
