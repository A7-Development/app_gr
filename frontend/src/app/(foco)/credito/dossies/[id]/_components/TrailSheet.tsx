// TrailSheet — trilha de auditoria da análise (handoff frame A4).
// Sheet lateral cronológico: mesmos glifos de proveniência da margem do
// documento ("a trilha é a margem do documento, desenrolada no tempo").
// Filtros: tudo / IA / ajustes. Cada evento = glifo + frase (ator em bold)
// + meta "§seção · hora · detalhe". Tudo gera evento — consulta, conclusão,
// homologação, ajuste, substituição de documento, falha, reabertura.

"use client"

import * as React from "react"
import { RiHistoryLine } from "@remixicon/react"

import { DrillDownSheet } from "@/design-system/components/DrillDownSheet"
import { PROVENANCE_ICON } from "@/design-system/components"
import { provenanceTokens, type ProvenanceOrigin } from "@/design-system/tokens/provenance"
import { cx } from "@/lib/utils"

export type TrailEvent = {
  id: string
  /** Origem do evento (define o glifo). */
  origin: ProvenanceOrigin
  /** Frase do evento — ator em <strong>. */
  phrase: React.ReactNode
  /** Meta: "§2 Faturamento · 14:18 · 12 valores, 1 ajuste". */
  meta: string
  /** ISO — ordena decrescente. */
  at: string
  /** Estação que produziu — clicar navega até ela. */
  stationId?: string
}

type Filter = "tudo" | "ia" | "ajustes"

export function TrailSheet({
  open,
  onClose,
  events,
  onGoToStation,
}: {
  open: boolean
  onClose: () => void
  events: TrailEvent[]
  onGoToStation?: (stationId: string) => void
}) {
  const [filter, setFilter] = React.useState<Filter>("tudo")

  const filtered = React.useMemo(() => {
    const sorted = [...events].sort((a, b) => (a.at < b.at ? 1 : -1))
    if (filter === "ia") return sorted.filter((e) => e.origin === "agente")
    if (filter === "ajustes") return sorted.filter((e) => e.origin === "analista")
    return sorted
  }, [events, filter])

  return (
    <DrillDownSheet open={open} onClose={onClose} size="md" title="Trilha de auditoria">
      <div className="flex h-full flex-col">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-100 px-4 py-2.5 dark:border-gray-900">
          <span className="flex items-center gap-1.5 text-xs font-semibold text-gray-900 dark:text-gray-50">
            <RiHistoryLine className="size-3.5" aria-hidden />
            Trilha · {events.length} eventos
          </span>
          <span className="flex items-center gap-1 text-[11px] text-gray-400">
            filtrar:
            {(["tudo", "ia", "ajustes"] as const).map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setFilter(f)}
                className={cx(
                  "rounded px-1.5 py-0.5 transition-colors duration-100",
                  filter === f
                    ? "bg-gray-100 font-semibold text-gray-700 dark:bg-gray-800 dark:text-gray-300"
                    : "hover:text-gray-600 dark:hover:text-gray-300",
                )}
              >
                {f === "ia" ? "IA" : f}
              </button>
            ))}
          </span>
        </div>

        {/* Lista cronológica */}
        <div className="flex-1 overflow-y-auto px-4 py-3">
          {filtered.length === 0 ? (
            <p className="py-8 text-center text-[12px] text-gray-400">
              Nenhum evento {filter !== "tudo" ? "neste filtro" : "ainda"}.
            </p>
          ) : (
            filtered.map((e, i) => {
              const t = provenanceTokens[e.origin]
              const Icon = PROVENANCE_ICON[e.origin]
              const last = i === filtered.length - 1
              const body = (
                <>
                  <span className="relative flex w-5 shrink-0 justify-center pt-0.5">
                    <Icon className="size-[13px]" style={{ color: t.color }} aria-hidden />
                    {!last && (
                      <span
                        className="absolute bottom-0 left-1/2 top-5 w-px -translate-x-1/2 bg-gray-100 dark:bg-gray-900"
                        aria-hidden
                      />
                    )}
                  </span>
                  <span className="min-w-0 flex-1 pb-3">
                    <span className="block text-xs leading-normal text-gray-700 dark:text-gray-300">
                      {e.phrase}
                    </span>
                    <span className="mt-px block text-[11px] text-gray-400 dark:text-gray-500">
                      {e.meta}
                    </span>
                  </span>
                </>
              )
              if (e.stationId && onGoToStation) {
                return (
                  <button
                    key={e.id}
                    type="button"
                    onClick={() => {
                      onGoToStation(e.stationId!)
                      onClose()
                    }}
                    className="-mx-1.5 grid w-[calc(100%+12px)] grid-cols-[20px_1fr] gap-2.5 rounded px-1.5 text-left transition-colors duration-100 hover:bg-gray-50 dark:hover:bg-gray-900"
                  >
                    {body}
                  </button>
                )
              }
              return (
                <div key={e.id} className="grid grid-cols-[20px_1fr] gap-2.5">
                  {body}
                </div>
              )
            })
          )}
        </div>
      </div>
    </DrillDownSheet>
  )
}
