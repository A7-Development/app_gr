"use client"

//
// Badges compartilhados entre a lista (/admin/ia/agents) e o cockpit
// (/admin/ia/agents/[id]). Extraidos da page.tsx na promocao para rota.
//

import { Badge } from "@/components/tremor/Badge"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

// Cor por modulo — espelha avatars de modulo (CLAUDE.md §11.6).
const MODULE_TONES: Record<string, { bg: string; fg: string }> = {
  bi: { bg: "bg-gray-100 dark:bg-gray-800", fg: "text-gray-700 dark:text-gray-300" },
  cadastros: { bg: "bg-blue-50 dark:bg-blue-500/10", fg: "text-blue-700 dark:text-blue-300" },
  operacoes: { bg: "bg-emerald-50 dark:bg-emerald-500/10", fg: "text-emerald-700 dark:text-emerald-300" },
  credito: { bg: "bg-indigo-50 dark:bg-indigo-500/10", fg: "text-indigo-700 dark:text-indigo-300" },
  controladoria: { bg: "bg-teal-50 dark:bg-teal-500/10", fg: "text-teal-700 dark:text-teal-300" },
  risco: { bg: "bg-amber-50 dark:bg-amber-500/10", fg: "text-amber-700 dark:text-amber-300" },
  integracoes: { bg: "bg-red-50 dark:bg-red-500/10", fg: "text-red-700 dark:text-red-300" },
  laboratorio: { bg: "bg-violet-50 dark:bg-violet-500/10", fg: "text-violet-700 dark:text-violet-300" },
  admin: { bg: "bg-slate-50 dark:bg-slate-500/10", fg: "text-slate-700 dark:text-slate-300" },
}

export function ModuleBadge({ module }: { module: string }) {
  const tone = MODULE_TONES[module] ?? {
    bg: "bg-gray-100 dark:bg-gray-800",
    fg: "text-gray-700 dark:text-gray-300",
  }
  return (
    <span
      className={cx(tableTokens.badge, tone.bg, tone.fg)}
    >
      {module}
    </span>
  )
}

export function StatusBadge({
  active,
  archived,
}: {
  active: boolean
  archived: boolean
}) {
  if (archived) {
    return (
      <Badge variant="neutral" className={tableTokens.badge}>
        Arquivado
      </Badge>
    )
  }
  if (active) {
    return (
      <Badge variant="success" className={tableTokens.badge}>
        Ativo
      </Badge>
    )
  }
  return (
    <Badge variant="neutral" className={tableTokens.badge}>
      Inativo
    </Badge>
  )
}
