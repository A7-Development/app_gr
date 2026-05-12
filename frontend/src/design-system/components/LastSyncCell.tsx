"use client"

import { RiLoader4Line } from "@remixicon/react"
import { format, formatDistanceToNowStrict } from "date-fns"
import { ptBR } from "date-fns/locale"

import { Badge } from "@/components/tremor/Badge"
import { Tooltip } from "@/components/tremor/Tooltip"

// Janela de tolerancia: ate `freq * DELAY_FACTOR` consideramos "no prazo".
// Espelha a regra do backend (/system/sync-health) — manter sincronizado.
const DELAY_FACTOR = 1.5

type SyncStatus = "ok" | "erro" | "em_progresso" | null

/**
 * Renderiza estado do ultimo sync com semantica explicita.
 *
 * Dois modos:
 * - **Legado** (`iso`): exibe "ha X" usando o timestamp passado.
 * - **Stateful** (`startedAt`/`finishedAt`/`status`): renderiza por status —
 *   "ha X" (ok), "Sincronizando..." (em_progresso), "Falhou ha X" (erro).
 *   Quando ambos existem o stateful tem prioridade.
 *
 * `freqMinutes`: quando setado, adiciona badge "Atrasado" se a ultima sync
 * (com sucesso) passou de `freqMinutes * 1.5`.
 */
export function LastSyncCell({
  iso,
  startedAt,
  finishedAt,
  status,
  errorMessage,
  freqMinutes,
}: {
  iso?: string | null
  startedAt?: string | null
  finishedAt?: string | null
  status?: SyncStatus
  errorMessage?: string | null
  freqMinutes?: number | null
}) {
  if (status !== undefined) {
    return (
      <StatefulCell
        startedAt={startedAt ?? null}
        finishedAt={finishedAt ?? null}
        status={status}
        errorMessage={errorMessage ?? null}
        freqMinutes={freqMinutes ?? null}
      />
    )
  }
  return <LegacyCell iso={iso ?? null} freqMinutes={freqMinutes ?? null} />
}

function LegacyCell({
  iso,
  freqMinutes,
}: {
  iso: string | null
  freqMinutes: number | null
}) {
  if (!iso) {
    return <span className="text-gray-400 dark:text-gray-600">—</span>
  }
  const d = new Date(iso)
  const relativo = formatDistanceToNowStrict(d, { addSuffix: true, locale: ptBR })
  const absoluto = format(d, "dd 'de' MMM 'de' yyyy 'as' HH:mm", { locale: ptBR })
  const isDelayed =
    freqMinutes !== null &&
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

function StatefulCell({
  startedAt,
  finishedAt,
  status,
  errorMessage,
  freqMinutes,
}: {
  startedAt: string | null
  finishedAt: string | null
  status: SyncStatus
  errorMessage: string | null
  freqMinutes: number | null
}) {
  if (status === null) {
    return <span className="text-gray-400 dark:text-gray-600">—</span>
  }

  if (status === "em_progresso") {
    return (
      <div className="flex items-center gap-2 text-gray-700 dark:text-gray-300">
        <RiLoader4Line className="size-3.5 animate-spin text-blue-500" aria-hidden />
        <span>Sincronizando…</span>
        {finishedAt && (
          <span className="text-xs text-gray-500 dark:text-gray-400">
            (última: {formatDistanceToNowStrict(new Date(finishedAt), { addSuffix: true, locale: ptBR })})
          </span>
        )}
      </div>
    )
  }

  if (status === "erro") {
    const refIso = finishedAt ?? startedAt
    if (!refIso) {
      return (
        <Tooltip content={errorMessage ?? "Erro sem detalhe"} side="top">
          <span className="cursor-default text-red-600 dark:text-red-400">
            Falhou
          </span>
        </Tooltip>
      )
    }
    const d = new Date(refIso)
    const relativo = formatDistanceToNowStrict(d, { addSuffix: true, locale: ptBR })
    const absoluto = format(d, "dd 'de' MMM 'de' yyyy 'as' HH:mm", { locale: ptBR })
    const tooltipContent = errorMessage
      ? `${absoluto}\n\n${errorMessage}`
      : absoluto
    return (
      <Tooltip content={tooltipContent} side="top">
        <span className="cursor-default text-red-600 dark:text-red-400">
          Falhou {relativo}
        </span>
      </Tooltip>
    )
  }

  // status === "ok"
  const refIso = finishedAt ?? startedAt
  if (!refIso) {
    return <span className="text-gray-400 dark:text-gray-600">—</span>
  }
  const d = new Date(refIso)
  const relativo = formatDistanceToNowStrict(d, { addSuffix: true, locale: ptBR })
  const absoluto = format(d, "dd 'de' MMM 'de' yyyy 'as' HH:mm", { locale: ptBR })
  const isDelayed =
    freqMinutes !== null &&
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
