// DescriptorParityPanel — QA gated (?descriptor=1) do Passo 1 do wiring (Etapa 4).
//
// Busca o /descriptor (estações derivadas SERVER-SIDE) e compara, lado a lado,
// com as estações que o cockpit deriva client-side (buildEstacoes). Objetivo:
// provar que a derivação do backend bate com a atual ANTES do rewire de verdade.
// NÃO altera o rendering do cockpit — é um overlay de comparação.

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { RiLoader4Line } from "@remixicon/react"

import {
  DenseTable,
  type DenseColumn,
  type DenseRow,
} from "@/design-system/components/DenseTable"
import { tableTokens } from "@/design-system/tokens/table"
import { credito } from "@/lib/credito-client"
import { cx } from "@/lib/utils"

type ClientStation = { id: string; label: string; state: string }

type ServerStation = {
  id: string
  label: string
  state: string
  sections: unknown[]
  isRecommendedNext?: boolean
}

type ParityRow = {
  id: string
  c: ClientStation | undefined
  s: ServerStation | undefined
  ok: boolean
  labelOk: boolean
  stateOk: boolean
  present: boolean
}

// Painel de QA (dev-only) -> DenseTable. O ícone "=" (check/cross) vira texto
// "igual"/"difere"; a divergência no lado server, antes destacada em âmbar, fica
// indicada pelo resultado da coluna "=" (DenseTable só renderiza texto/número).
const PARITY_COLUMNS: DenseColumn[] = [
  { key: "id", label: "node id", format: "texto" },
  { key: "client", label: "client (label · state)", format: "texto" },
  { key: "server", label: "server (label · state)", format: "texto" },
  { key: "extra", label: "server extra", format: "texto" },
  { key: "eq", label: "=", format: "texto", align: "center" },
]

function parityRows(rows: ParityRow[]): DenseRow[] {
  return rows.map((r) => ({
    id: r.id,
    client: r.c ? `${r.c.label} · ${r.c.state}` : "—",
    server: r.s ? `${r.s.label} · ${r.s.state}` : "—",
    extra: r.s
      ? `${r.s.sections.length} seção(ões)${r.s.isRecommendedNext ? " · ★ próxima" : ""}`
      : "—",
    eq: r.ok ? "igual" : "difere",
  }))
}

export function DescriptorParityPanel({
  dossierId,
  clientStations,
}: {
  dossierId: string
  clientStations: ClientStation[]
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["credito", "descriptor", dossierId],
    queryFn: () => credito.dossies.descriptor(dossierId),
  })

  const serverStations = data?.stations ?? []
  const serverById = new Map(serverStations.map((s) => [s.id, s]))
  const clientById = new Map(clientStations.map((s) => [s.id, s]))
  const allIds = Array.from(
    new Set([...clientStations.map((s) => s.id), ...serverStations.map((s) => s.id)]),
  )

  let mismatches = 0
  const rows = allIds.map((id) => {
    const c = clientById.get(id)
    const s = serverById.get(id)
    const labelOk = (c?.label ?? null) === (s?.label ?? null)
    const stateOk = (c?.state ?? null) === (s?.state ?? null)
    const present = Boolean(c) && Boolean(s)
    const ok = present && labelOk && stateOk
    if (!ok) mismatches += 1
    return { id, c, s, ok, labelOk, stateOk, present }
  })

  return (
    <div className="mb-4 rounded-lg border border-dashed border-violet-300 bg-violet-50/40 p-3 dark:border-violet-700 dark:bg-violet-500/5">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-violet-700 dark:text-violet-300">
          QA · paridade /descriptor (server) × buildEstacoes (client)
        </span>
        {isLoading ? (
          <RiLoader4Line className="size-4 animate-spin text-violet-500" aria-hidden />
        ) : error ? (
          <span className={cx(tableTokens.badge, "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300")}>
            erro ao buscar
          </span>
        ) : (
          <span
            className={cx(
              tableTokens.badge,
              mismatches === 0
                ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
                : "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
            )}
          >
            {mismatches === 0 ? "paridade OK" : `${mismatches} divergência(s)`}
          </span>
        )}
        {data?.code && (
          <span className={tableTokens.cellSecondary}>· {data.code}</span>
        )}
      </div>

      {!isLoading && !error && (
        <DenseTable columns={PARITY_COLUMNS} rows={parityRows(rows)} />
      )}
    </div>
  )
}
