// src/lib/reports/registry.ts
//
// Mapa slug -> { columns, itemNoun }. Cada slug tem seu arquivo proprio
// em `src/lib/reports/<slug>.ts` que exporta colunas tipadas.
//
// Slugs nao listados aqui (16 hoje) caem no EmptyState "Colunas em breve" —
// preencher quando houver demanda real (followup do plano em
// ~/.claude/plans/shimmering-snuggling-snail.md).

import type { ColumnDef } from "@tanstack/react-table"

import * as carteira from "./qitech-estoque-carteira"

export type ReportRegistryEntry = {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  columns: ColumnDef<any, unknown>[]
  itemNoun: { singular: string; plural: string }
}

const REGISTRY: Record<string, ReportRegistryEntry> = {
  "qitech-estoque-carteira": {
    columns: carteira.columns,
    itemNoun: carteira.itemNoun,
  },
}

export function getReportEntry(slug: string): ReportRegistryEntry | null {
  return REGISTRY[slug] ?? null
}

export function isReportImplemented(slug: string): boolean {
  return slug in REGISTRY
}
