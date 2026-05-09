"use client"

import { format, formatDistanceToNowStrict } from "date-fns"
import { ptBR } from "date-fns/locale"

import { Badge } from "@/components/tremor/Badge"
import { Tooltip } from "@/components/tremor/Tooltip"

// Janela de tolerancia: ate `freq * DELAY_FACTOR` consideramos "no prazo".
// Espelha a regra do backend (/system/sync-health) — manter sincronizado.
const DELAY_FACTOR = 1.5

/**
 * Render "ha X" (tooltip do timestamp absoluto) ou "—" quando nulo.
 *
 * Quando `freqMinutes` e fornecida, exibe badge "Atrasado" em ambar caso
 * `now - iso > freqMinutes * 1.5`. Sem `freqMinutes`, comportamento legado
 * (so o relativo).
 */
export function LastSyncCell({
  iso,
  freqMinutes,
}: {
  iso: string | null
  freqMinutes?: number | null
}) {
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

  const isDelayed =
    freqMinutes !== null &&
    freqMinutes !== undefined &&
    Date.now() - d.getTime() > freqMinutes * DELAY_FACTOR * 60_000

  return (
    <div className="flex items-center gap-2">
      <Tooltip content={absoluto} side="top">
        <span className="cursor-default text-gray-700 dark:text-gray-300">
          {relativo}
        </span>
      </Tooltip>
      {isDelayed && (
        <Tooltip
          content={`Esperado a cada ${freqMinutes} min — ultima carga passou da janela de tolerancia.`}
          side="top"
        >
          <Badge variant="warning">Atrasado</Badge>
        </Tooltip>
      )}
    </div>
  )
}
