"use client"

import { format, formatDistanceToNowStrict } from "date-fns"
import { ptBR } from "date-fns/locale"

import { Tooltip } from "@/components/tremor/Tooltip"

type NextSyncSource = "state_machine" | "schedule" | "manual_only" | null

/**
 * Renderiza proximo sync agendado de um endpoint.
 *
 * Tres estados:
 * - `iso` no futuro: "em X minutos/horas/dias" + tooltip com timestamp absoluto.
 * - `iso` no passado (ou agora): "agora" (sistema vai pegar no proximo tick).
 *   Acontece pra interval ja vencido ou daily_at cuja hora ja passou hoje sem sync.
 * - `iso === null`: "Sob demanda" (on_demand) ou "—" (sem agendamento).
 *
 * `source` diferencia state machine (cadencia adaptativa) de schedule fixo —
 * tooltip explica.
 */
export function NextSyncCell({
  iso,
  source,
}: {
  iso?: string | null
  source?: NextSyncSource
}) {
  if (!iso) {
    if (source === "manual_only") {
      return (
        <Tooltip
          content="Endpoint configurado como 'Sob demanda' — só sincroniza via 'Sincronizar agora'."
          side="top"
        >
          <span className="cursor-default text-gray-500 dark:text-gray-400">
            Sob demanda
          </span>
        </Tooltip>
      )
    }
    return <span className="text-gray-400 dark:text-gray-600">—</span>
  }

  const d = new Date(iso)
  const now = Date.now()
  const isPastOrNow = d.getTime() <= now

  const absoluto = format(d, "dd 'de' MMM 'de' yyyy 'as' HH:mm", {
    locale: ptBR,
  })
  const sourceHint =
    source === "state_machine"
      ? "Cadência adaptativa (state machine — varia por estado de tolerância)."
      : source === "schedule"
        ? "Horário fixo do agendamento."
        : null
  const tooltipContent = sourceHint ? `${absoluto}\n\n${sourceHint}` : absoluto

  if (isPastOrNow) {
    return (
      <Tooltip content={tooltipContent} side="top">
        <span className="cursor-default text-blue-700 dark:text-blue-300">
          agora
        </span>
      </Tooltip>
    )
  }

  const relativo = formatDistanceToNowStrict(d, {
    addSuffix: true,
    locale: ptBR,
  })
  return (
    <Tooltip content={tooltipContent} side="top">
      <span className="cursor-default text-gray-700 dark:text-gray-300">
        {relativo}
      </span>
    </Tooltip>
  )
}
