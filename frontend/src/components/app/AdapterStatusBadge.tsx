import * as React from "react"

import { Badge } from "@/components/tremor/Badge"

/** Status do adapter para o tenant.
 * - `nao_configurado`: sem `tenant_source_config` persistido (secrets vazios)
 * - `desabilitado`: persistido mas `enabled=false`
 * - `habilitado`: `enabled=true` (sem verdict de saude ainda)
 * - `ok`: ultimo ping/sync retornou OK
 * - `erro`: ultimo ping/sync retornou erro
 */
export type AdapterStatus =
  | "nao_configurado"
  | "desabilitado"
  | "habilitado"
  | "ok"
  | "erro"

const COPY: Record<
  AdapterStatus,
  { label: string; variant: "default" | "neutral" | "success" | "warning" | "error" }
> = {
  nao_configurado: { label: "Nao configurado", variant: "neutral" },
  desabilitado: { label: "Desabilitado", variant: "warning" },
  habilitado: { label: "Habilitado", variant: "default" },
  ok: { label: "OK", variant: "success" },
  erro: { label: "Erro", variant: "error" },
}

export function AdapterStatusBadge({ status }: { status: AdapterStatus }) {
  const copy = COPY[status]
  return <Badge variant={copy.variant}>{copy.label}</Badge>
}

/** Deriva status a partir do estado bruto do backend. */
export function statusFrom(configured: boolean, enabled: boolean): AdapterStatus {
  if (!configured) return "nao_configurado"
  if (!enabled) return "desabilitado"
  return "habilitado"
}
