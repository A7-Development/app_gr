// src/app/(app)/bi/operacoes4/_components/MovementStack.tsx
//
// L5 direita — 3 MovementCards empilhados verticalmente: Novos no mes,
// Sumidos, Top Movers. Deriva tudo client-side a partir do payload de
// `/bi/operacoes2/cedentes-mtd` (campo `status` e ordenacao por volume
// + delta).
//
// Top Movers = top 3 cedentes recorrentes por |delta_vs_mes_ant_pct|. Sem
// MovementCards quando cedentesMtd ainda nao carregou.

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"

import { biOperacoes2 } from "@/lib/api-client"
import type { BIFilters, Operacoes2CedenteMtdItem } from "@/lib/api-client"

import { MovementCard, type MovementItem } from "./charts/MovementCard"

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 1,
})

function deriveBlocks(cedentes: Operacoes2CedenteMtdItem[]): {
  novos: { count: number; items: MovementItem[] }
  sumidos: { count: number; items: MovementItem[] }
  movers: { count: number; items: MovementItem[] }
} {
  const novos = cedentes.filter((c) => c.status === "novo")
  const sumidos = cedentes.filter((c) => c.status === "sumido")
  const recorrentes = cedentes.filter(
    (c) =>
      c.status === "recorrente" &&
      c.delta_vs_mes_ant_pct !== null &&
      c.volume_mtd !== null,
  )

  // Top movers — top 3 por |delta|
  const sortedMovers = [...recorrentes].sort(
    (a, b) => Math.abs(b.delta_vs_mes_ant_pct ?? 0) - Math.abs(a.delta_vs_mes_ant_pct ?? 0),
  )

  return {
    novos: {
      count: novos.length,
      items: novos
        .sort((a, b) => (b.volume_mtd ?? 0) - (a.volume_mtd ?? 0))
        .slice(0, 3)
        .map((c) => ({
          primaryLabel: c.cedente_nome,
          valueLabel: fmtBRL.format(c.volume_mtd ?? 0),
        })),
    },
    sumidos: {
      count: sumidos.length,
      items: sumidos.slice(0, 3).map((c) => ({
        primaryLabel: c.cedente_nome,
        valueLabel: "—",
      })),
    },
    movers: {
      count: sortedMovers.length,
      items: sortedMovers.slice(0, 3).map((c) => {
        const delta = c.delta_vs_mes_ant_pct ?? 0
        return {
          primaryLabel: c.cedente_nome,
          valueLabel: fmtBRL.format(c.volume_mtd ?? 0),
          deltaLabel: `${delta > 0 ? "+" : ""}${delta.toFixed(0).replace(".", ",")}%`,
          tone: (delta >= 0 ? "pos" : "neg") as "pos" | "neg",
        }
      }),
    },
  }
}

export type MovementCategoria = "novos" | "sumidos" | "movers"

export function MovementStack({
  filters,
  onCardClick,
}: {
  filters: BIFilters
  onCardClick?: (
    categoria: MovementCategoria,
    items: Operacoes2CedenteMtdItem[],
  ) => void
}) {
  const q = useQuery({
    queryKey: ["bi", "operacoes4", "cedentes-mtd", filters],
    queryFn: () => biOperacoes2.cedentesMtd(filters),
  })

  // Memoiza o array — `q.data?.data.cedentes ?? []` cria nova referencia
  // a cada render, o que dispararia useMemo abaixo sem necessidade.
  const cedentes = React.useMemo(
    () => q.data?.data.cedentes ?? [],
    [q.data],
  )

  const blocks = React.useMemo(() => deriveBlocks(cedentes), [cedentes])

  // Listas completas (sem cap) — alimentam o drill quando o card e clicado.
  const fullLists = React.useMemo(() => {
    const novos = cedentes.filter((c) => c.status === "novo")
    const sumidos = cedentes.filter((c) => c.status === "sumido")
    const recorrentes = cedentes.filter(
      (c) =>
        c.status === "recorrente" &&
        c.delta_vs_mes_ant_pct !== null &&
        c.volume_mtd !== null,
    )
    const movers = [...recorrentes].sort(
      (a, b) =>
        Math.abs(b.delta_vs_mes_ant_pct ?? 0) -
        Math.abs(a.delta_vs_mes_ant_pct ?? 0),
    )
    return { novos, sumidos, movers }
  }, [cedentes])

  return (
    <div className="flex h-full flex-col gap-3">
      <MovementCard
        eyebrow="NOVOS NO MÊS"
        count={blocks.novos.count}
        items={blocks.novos.items}
        caption={
          blocks.novos.count > 3
            ? `+${blocks.novos.count - 3} cedente${blocks.novos.count - 3 > 1 ? "s" : ""} não exibido${blocks.novos.count - 3 > 1 ? "s" : ""}`
            : undefined
        }
        onClick={
          onCardClick ? () => onCardClick("novos", fullLists.novos) : undefined
        }
      />
      <MovementCard
        eyebrow="SUMIDOS"
        count={blocks.sumidos.count}
        items={blocks.sumidos.items}
        onClick={
          onCardClick
            ? () => onCardClick("sumidos", fullLists.sumidos)
            : undefined
        }
      />
      <MovementCard
        eyebrow="TOP MOVERS"
        count={blocks.movers.count}
        items={blocks.movers.items}
        onClick={
          onCardClick
            ? () => onCardClick("movers", fullLists.movers)
            : undefined
        }
      />
    </div>
  )
}
