// src/app/(app)/bi/operacoes3/_components/TabelaCedentesMtd.tsx
//
// Tabela narrativa de cedentes MTD — L3 da pagina /bi/operacoes3.
//
// Responde "quem entrou/saiu/cresceu/caiu este mes":
//   - Recorrentes: cedentes que tinham historia antes do MTD
//   - Novos: 1a operacao historica do cedente caiu dentro do MTD
//   - Sumidos: tinham op no mes anterior MTD mas zero no MTD corrente
//     (volume_mtd = "—", delta = -100%)
//
// Filtros locais:
//   - Status (SegmentSwitch): Todos | Recorrente | Novo | Sumido
//   - UA: usa o filtro global da pagina (sem filtro local pra evitar dupla)
//
// Sort default: Volume MTD desc (sumidos no fim — null sort grouping).

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import type { ColumnDef } from "@tanstack/react-table"

import { Card } from "@/components/tremor/Card"
import {
  CurrencyCell,
  DataTable,
  SegmentSwitch,
  type SegmentDef,
} from "@/design-system/components"
import { cardTokens } from "@/design-system/tokens/card"
import { tableTokens } from "@/design-system/tokens/table"
import { biOperacoes2 } from "@/lib/api-client"
import type { Operacoes2CedenteMtdItem } from "@/lib/api-client"
import { useBiFilters } from "@/lib/hooks/useBiFilters"
import { cx } from "@/lib/utils"

const fmtPct1 = (v: number) => `${v.toFixed(1).replace(".", ",")}%`
const fmtPct2 = (v: number) => `${v.toFixed(2).replace(".", ",")}%`
const fmtInt = new Intl.NumberFormat("pt-BR")

function fmtDate(iso: string | null): string {
  if (!iso) return "—"
  const [y, m, d] = iso.split("-").map(Number)
  if (!y || !m || !d) return iso
  return `${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")}/${y}`
}

// ─── Status filter ─────────────────────────────────────────────────────────

type StatusFilter = "todos" | "recorrente" | "novo" | "sumido"

const STATUS_OPTIONS: SegmentDef<StatusFilter>[] = [
  { value: "todos", label: "Todos" },
  { value: "recorrente", label: "Recorrentes" },
  { value: "novo", label: "Novos" },
  { value: "sumido", label: "Sumidos" },
]

// ─── Cell helpers ──────────────────────────────────────────────────────────

function DeltaCell({ pct }: { pct: number | null }) {
  if (pct == null) {
    return <span className={cx(tableTokens.cellMuted, "tabular-nums")}>—</span>
  }
  const isUp = pct >= 0
  return (
    <span className={cx(
      "font-medium",
      isUp ? tableTokens.cellNumberPositive : tableTokens.cellNumberNegative,
    )}>
      {isUp ? "+" : ""}
      {fmtPct1(pct)}
    </span>
  )
}

function StatusBadge({ status }: { status: Operacoes2CedenteMtdItem["status"] }) {
  if (status === "novo") {
    // MOTIVO: "novo" e informativo (chegada), nao success/warning/danger —
    // compoe tableTokens.badge + tone blue (mesmo precedente do
    // "enviado_nao_confirmado" da conciliacao).
    return (
      <span className={cx(tableTokens.badge, "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300")}>
        novo
      </span>
    )
  }
  if (status === "sumido") {
    return <span className={tableTokens.badgeDanger}>sumido</span>
  }
  return <span className={tableTokens.badgeNeutral}>recorrente</span>
}

// ─── Componente principal ─────────────────────────────────────────────────

export function TabelaCedentesMtd() {
  const { filtersWithFocus } = useBiFilters()
  const [statusFilter, setStatusFilter] = React.useState<StatusFilter>("todos")

  const q = useQuery({
    queryKey: ["bi", "operacoes3", "cedentes-mtd", filtersWithFocus],
    queryFn: () => biOperacoes2.cedentesMtd(filtersWithFocus),
  })

  const cedentes = q.data?.data.cedentes ?? []
  const total = q.data?.data.total ?? 0

  const rows = React.useMemo(() => {
    if (statusFilter === "todos") return cedentes
    return cedentes.filter((c) => c.status === statusFilter)
  }, [cedentes, statusFilter])

  const columns = React.useMemo<ColumnDef<Operacoes2CedenteMtdItem, unknown>[]>(
    () => [
      {
        accessorKey: "cedente_nome",
        header: "Cedente",
        size: 280,
        cell: ({ row }) => (
          <div
            className={cx(tableTokens.cellText, "block w-full truncate")}
            title={row.original.cedente_nome}
          >
            {row.original.cedente_nome}
          </div>
        ),
      },
      {
        accessorKey: "volume_mtd",
        header: () => <div className="text-right">Volume MTD</div>,
        size: 110,
        cell: ({ row }) =>
          row.original.volume_mtd == null ? (
            <div className={cx(tableTokens.cellMuted, "text-right tabular-nums")}>
              —
            </div>
          ) : (
            <CurrencyCell value={row.original.volume_mtd} />
          ),
      },
      {
        accessorKey: "delta_vs_mes_ant_pct",
        header: () => <div className="text-right">Δ vs mês ant.</div>,
        size: 100,
        cell: ({ row }) => (
          <div className="text-right">
            <DeltaCell pct={row.original.delta_vs_mes_ant_pct} />
          </div>
        ),
      },
      {
        accessorKey: "status",
        header: "Status",
        size: 100,
        cell: ({ row }) => <StatusBadge status={row.original.status} />,
      },
      {
        accessorKey: "n_op",
        header: () => <div className="text-right">#Op</div>,
        size: 60,
        cell: ({ row }) => (
          <div className={cx(tableTokens.cellNumber, "text-right")}>
            {row.original.n_op != null ? fmtInt.format(row.original.n_op) : "—"}
          </div>
        ),
      },
      {
        accessorKey: "dias_mtd",
        header: () => <div className="text-right">Dias MTD</div>,
        size: 70,
        cell: ({ row }) => (
          <div className={cx(tableTokens.cellNumber, "text-right")}>
            {row.original.dias_mtd != null
              ? fmtInt.format(row.original.dias_mtd)
              : "—"}
          </div>
        ),
      },
      {
        accessorKey: "taxa_media",
        header: () => <div className="text-right">Taxa</div>,
        size: 70,
        cell: ({ row }) => (
          <div className={cx(tableTokens.cellNumber, "text-right")}>
            {row.original.taxa_media != null
              ? fmtPct2(row.original.taxa_media)
              : "—"}
          </div>
        ),
      },
      {
        accessorKey: "primeira_op",
        header: "1ª op",
        size: 95,
        cell: ({ row }) => (
          <div className={cx(tableTokens.cellSecondary, "tabular-nums")}>
            {fmtDate(row.original.primeira_op)}
          </div>
        ),
      },
      {
        accessorKey: "ultima_op",
        header: "Última op",
        size: 95,
        cell: ({ row }) => (
          <div className={cx(tableTokens.cellSecondary, "tabular-nums")}>
            {fmtDate(row.original.ultima_op)}
          </div>
        ),
      },
    ],
    [],
  )

  return (
    <Card className="flex flex-col p-0">
      <div className={cx(cardTokens.header, "flex items-center justify-between gap-3")}>
        <div className="flex flex-col">
          <h3 className={cardTokens.headerTitle}>
            Tabela narrativa · cedentes MTD
          </h3>
          <p className={cx(cardTokens.headerSubtitle, "mt-0.5")}>
            {q.isLoading
              ? "Carregando…"
              : `${fmtInt.format(total)} ${total === 1 ? "cedente" : "cedentes"}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] uppercase tracking-wider text-gray-500 dark:text-gray-400">
            Status
          </span>
          <SegmentSwitch
            options={STATUS_OPTIONS}
            value={statusFilter}
            onChange={setStatusFilter}
            ariaLabel="Filtro de status do cedente"
          />
        </div>
      </div>

      <div className={cardTokens.body}>
        {q.isError ? (
          <p className="py-8 text-center text-sm text-gray-500 dark:text-gray-400">
            Não foi possível carregar a tabela de cedentes.
          </p>
        ) : (
          <DataTable
            data={rows}
            columns={columns}
            density="compact"
            showDensityToggle={false}
            showColumnManager={false}
            loading={q.isLoading}
          />
        )}
      </div>
    </Card>
  )
}
