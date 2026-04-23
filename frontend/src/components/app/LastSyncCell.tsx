"use client"

import { format, formatDistanceToNowStrict } from "date-fns"
import { ptBR } from "date-fns/locale"

import { Tooltip } from "@/components/tremor/Tooltip"

/** Render "ha X" (com tooltip do timestamp absoluto) ou "—" quando nulo. */
export function LastSyncCell({ iso }: { iso: string | null }) {
  if (!iso) {
    return <span className="text-gray-400 dark:text-gray-600">—</span>
  }
  const d = new Date(iso)
  const relativo = formatDistanceToNowStrict(d, {
    addSuffix: true,
    locale: ptBR,
  })
  const absoluto = format(d, "dd 'de' MMM 'de' yyyy 'as' HH:mm", {
    locale: ptBR,
  })
  return (
    <Tooltip content={absoluto} side="top">
      <span className="cursor-default text-gray-700 dark:text-gray-300">
        {relativo}
      </span>
    </Tooltip>
  )
}
