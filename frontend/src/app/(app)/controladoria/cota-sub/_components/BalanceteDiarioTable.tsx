"use client"

/**
 * BalanceteDiarioTable — Z3 da pagina Cota Sub.
 *
 * Tabela hierarquica D-1 vs D0 espelhando a arvore COSIF do balancete
 * oficial. Substitui a `BalanceTable` no fluxo "Eventos do dia" — modelo
 * agnostico multi-tenant: classificacao do silver em conta COSIF em runtime
 * (override -> regra -> pendente).
 *
 * Backend: GET /controladoria/cota-sub/balancete-diario (BalanceteResponse).
 *
 * Click numa conta analitica (sem subRows OU nivel >= 4) -> dispara
 * `onSelect(node)` para abrir o `CosifDrillSheet`. Modo "auditoria avancada"
 * liga os grupos de compensacao 3/9.
 */

import * as React from "react"
import {
  type ColumnDef,
  type ExpandedState,
  createColumnHelper,
} from "@tanstack/react-table"

import { cx } from "@/lib/utils"
import { Badge } from "@/components/tremor/Badge"
import { Card } from "@/components/tremor/Card"
import { Switch } from "@/components/tremor/Switch"
import { DataTable } from "@/design-system/components/DataTable"
import { tableTokens } from "@/design-system/tokens/table"

import type { CosifSource } from "@/lib/api-client"
import {
  type CosifNodeUI,
  buildCosifTree,
  defaultExpandedCodigos,
  sourceBadge,
} from "../_lib/cosif"

import type { CosifNode } from "@/lib/api-client"

// ─────────────────────────────────────────────────────────────────────────────
// Formatters
// ─────────────────────────────────────────────────────────────────────────────

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const fmtPct = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})

function formatValue(v: number | null): string {
  if (v == null) return ""
  if (v === 0) return "—"
  if (v < 0) return `(${fmtBRL.format(Math.abs(v))})`
  return fmtBRL.format(v)
}

function formatDelta(v: number | null): string {
  if (v == null) return ""
  if (v === 0) return "—"
  const sign = v > 0 ? "+" : ""
  return sign + fmtBRL.format(v)
}

function formatDeltaPct(v: number | null): string {
  if (v == null) return ""
  if (!isFinite(v)) return "—"
  if (v === 0) return "—"
  const sign = v > 0 ? "+" : ""
  return `${sign}${fmtPct.format(v)}%`
}

/** ISO yyyy-MM-dd → "DD/MM/YY". */
function fmtDateShort(iso?: string): string {
  if (!iso) return ""
  const [y, m, d] = iso.split("-")
  if (!y || !m || !d) return iso
  return `${d}/${m}/${y.slice(2)}`
}

// ─────────────────────────────────────────────────────────────────────────────
// Source badge — mapping de cosif_source para Tremor Badge variant
// ─────────────────────────────────────────────────────────────────────────────

function SourceBadgeCell({ source }: { source: CosifSource }) {
  const { label, tone } = sourceBadge(source)
  const variant =
    tone === "blue"
      ? "default"
      : tone === "green"
        ? "success"
        : tone === "amber"
          ? "warning"
          : tone === "red"
            ? "error"
            : "neutral"
  return (
    <Badge variant={variant} className={cx("px-1.5 py-0.5 text-[10px] ring-0")}>
      {label}
    </Badge>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Row styling — section/total visuais por grupo top-level
// ─────────────────────────────────────────────────────────────────────────────
//
// Niveis na arvore COSIF: 1 = grupo (ATIVO/PASSIVO/PL), 2 = familia,
// 3 = conta sintetica, 4 = conta sintetica de 2o grau, 5 = analitica.
//
// - Nivel 1 (grupo top, ex.: "1 - CIRCULANTE E REALIZAVEL"): bg-gray-50,
//   borda em cima E embaixo, font-semibold. Visual de "section" — mesmo
//   estilo do BalanceTable existente.
// - Nivel 2 (familia, ex.: "1.1 - DISPONIBILIDADES"): font-semibold, sem bg.
// - Nivel 3+ (sintetica e analitica): font-normal, padding-left propagado
//   automaticamente pela DataTable.
// - Pendente (codigo=null, nivel=0): tratado como nivel 1 visualmente.

function rowClass(row: CosifNodeUI): string {
  if (row.nivel === 0 || row.nivel === 1) {
    return cx(
      "!border-l-0 bg-gray-50 dark:bg-gray-900/60",
      "border-y border-y-gray-200 dark:border-y-gray-800",
      // Section topo destacada
    )
  }
  if (row.nivel === 2) {
    return "!border-l-0"
  }
  return ""
}

// ─────────────────────────────────────────────────────────────────────────────
// Column factory
// ─────────────────────────────────────────────────────────────────────────────

const col = createColumnHelper<CosifNodeUI>()

type BuildColumnsOpts = {
  dataAnterior?: string
  data?:         string
  /** Quando false, headers de D-1 e Δ ganham asterisco + tooltip avisando
   *  que a comparacao pode estar distorcida (D-1 com snapshot parcial). */
  comparable?:   boolean
  unreliableReason?: string | null
}

function buildColumns(
  opts: BuildColumnsOpts,
): ColumnDef<CosifNodeUI, unknown>[] {
  const { dataAnterior, data, comparable = true, unreliableReason } = opts
  const asterisco = comparable ? "" : " *"
  const headerD1 = (dataAnterior ? fmtDateShort(dataAnterior) : "D-1") + asterisco
  const headerD0 = data         ? fmtDateShort(data)         : "D0"
  const headerDelta = "Δ" + asterisco
  const headerDeltaPct = "Δ %" + asterisco
  const unreliableTooltip = unreliableReason
    ?? "Comparacao pode estar distorcida — D-1 com snapshot parcial"

  const labelCol = col.accessor("nome", {
    id:     "label",
    header: "Conta",
    size:   460,
    cell:   (info) => {
      const row = info.row.original
      const nome = info.getValue<string>()
      const baseTrunc = "block max-w-full truncate whitespace-nowrap"
      // Niveis 0/1/2 -> semibold. Restante normal. Codigo COSIF prefixa
      // o nome em monoespacado para os niveis >= 2 (raiz nao precisa).
      const codigoChip =
        row.codigo && row.nivel >= 2 ? (
          <span
            className={cx(
              "mr-2 inline-block font-mono text-[10px] tabular-nums",
              "text-gray-400 dark:text-gray-600",
            )}
          >
            {row.codigo}
          </span>
        ) : null
      const isStrong = row.nivel <= 2
      return (
        <span
          title={`${row.codigo ? row.codigo + " — " : ""}${nome}`}
          className={cx(baseTrunc, isStrong ? tableTokens.cellStrong : tableTokens.cellText)}
        >
          {codigoChip}
          {nome}
        </span>
      )
    },
  }) as ColumnDef<CosifNodeUI, unknown>

  const naturezaCol = col.accessor("natureza", {
    id:     "natureza",
    header: "Nat.",
    size:   58,
    meta:   { align: "center" },
    cell:   (info) => {
      const v = info.getValue<"D" | "C" | "?">()
      const row = info.row.original
      if (row.nivel === 0 || row.nivel === 1) return null
      return (
        <span className={cx(tableTokens.cellSecondary, "font-mono")}>
          {v === "?" ? "—" : v}
        </span>
      )
    },
  }) as ColumnDef<CosifNodeUI, unknown>

  const d1Col = col.accessor("d_minus_1", {
    id:     "d_minus_1",
    header: () =>
      comparable ? (
        headerD1
      ) : (
        <span title={unreliableTooltip} className="cursor-help">
          {headerD1}
        </span>
      ),
    meta:   { align: "right" },
    size:   140,
    cell:   (info) => {
      const v = info.getValue<number>()
      const row = info.row.original
      const isStrong = row.nivel <= 2
      return (
        <div
          style={{ textAlign: "right" }}
          className={cx(
            v < 0 ? tableTokens.cellNumberSecondary : tableTokens.cellNumber,
            isStrong && "font-semibold",
          )}
        >
          {formatValue(v)}
        </div>
      )
    },
  }) as ColumnDef<CosifNodeUI, unknown>

  const d0Col = col.accessor("d_zero", {
    id:     "d_zero",
    header: headerD0,
    meta:   { align: "right" },
    size:   140,
    cell:   (info) => {
      const v = info.getValue<number>()
      const row = info.row.original
      const isStrong = row.nivel <= 2
      return (
        <div
          style={{ textAlign: "right" }}
          className={cx(
            v < 0 ? tableTokens.cellNumberSecondary : tableTokens.cellNumber,
            isStrong && "font-semibold",
          )}
        >
          {formatValue(v)}
        </div>
      )
    },
  }) as ColumnDef<CosifNodeUI, unknown>

  const deltaCol = col.accessor("delta", {
    id:     "delta",
    header: () =>
      comparable ? (
        "Δ"
      ) : (
        <span title={unreliableTooltip} className="cursor-help">
          {headerDelta}
        </span>
      ),
    meta:   { align: "right" },
    size:   140,
    cell:   (info) => {
      const v = info.getValue<number>()
      const row = info.row.original
      const isPos = v > 0
      const isNeg = v < 0
      const isStrong = row.nivel <= 2
      return (
        <div
          style={{ textAlign: "right" }}
          className={cx(
            isPos
              ? tableTokens.cellNumberPositive
              : isNeg
                ? tableTokens.cellNumberNegative
                : tableTokens.cellMuted + " tabular-nums",
            isStrong && "font-semibold",
          )}
        >
          {formatDelta(v)}
        </div>
      )
    },
  }) as ColumnDef<CosifNodeUI, unknown>

  const deltaPctCol = col.accessor("delta_pct", {
    id:     "delta_pct",
    header: () =>
      comparable ? (
        "Δ %"
      ) : (
        <span title={unreliableTooltip} className="cursor-help">
          {headerDeltaPct}
        </span>
      ),
    meta:   { align: "right" },
    size:   80,
    cell:   (info) => {
      const v = info.getValue<number>()
      const row = info.row.original
      const isPos = v > 0
      const isNeg = v < 0
      const isStrong = row.nivel <= 2
      return (
        <div
          style={{ textAlign: "right" }}
          className={cx(
            isPos
              ? tableTokens.cellNumberPositive
              : isNeg
                ? tableTokens.cellNumberNegative
                : tableTokens.cellMuted + " tabular-nums",
            isStrong && "font-semibold",
          )}
        >
          {formatDeltaPct(v)}
        </div>
      )
    },
  }) as ColumnDef<CosifNodeUI, unknown>

  const sourceCol = col.accessor("cosif_source", {
    id:     "cosif_source",
    header: "Origem",
    size:   90,
    meta:   { align: "center" },
    cell:   (info) => {
      const row = info.row.original
      // So renderiza badge em nos analiticos (com saldo proprio). Em nos
      // sinteticos a origem e agregacao de varios, nao tem sentido.
      if (row.nivel <= 2) return null
      if (!row.cosif_source) return null
      return (
        <div style={{ textAlign: "center" }}>
          <SourceBadgeCell source={row.cosif_source} />
        </div>
      )
    },
  }) as ColumnDef<CosifNodeUI, unknown>

  return [labelCol, naturezaCol, d1Col, d0Col, deltaCol, deltaPctCol, sourceCol]
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export type BalanceteDiarioTableProps = {
  nodes:         readonly CosifNode[]
  data?:         string  // ISO D0
  dataAnterior?: string  // ISO D-1
  emptyMessage?: string
  /** Callback ao clicar numa conta analitica — abre o CosifDrillSheet. */
  onSelectNode?: (node: CosifNodeUI) => void
  /** Override do titulo do card. */
  title?: string
  /** Quando false, headers D-1 / Δ / Δ% ganham asterisco + tooltip avisando. */
  comparable?:   boolean
  /** Mensagem detalhada do motivo (entra no tooltip). */
  unreliableReason?: string | null
}

export function BalanceteDiarioTable({
  nodes,
  data,
  dataAnterior,
  emptyMessage,
  onSelectNode,
  title = "Balancete patrimonial diario",
  comparable = true,
  unreliableReason,
}: BalanceteDiarioTableProps) {
  const [incluirCompensacao, setIncluirCompensacao] = React.useState(false)

  const tree = React.useMemo(
    () => buildCosifTree(nodes, { incluirCompensacao }),
    [nodes, incluirCompensacao],
  )

  // Default expanded: niveis 1-3 com filhos.
  const defaultExpanded = React.useMemo<ExpandedState>(() => {
    const codigos = defaultExpandedCodigos(tree, 3)
    const out: Record<string, boolean> = {}
    function walk(rows: CosifNodeUI[] | undefined, path: string[]): void {
      if (!rows) return
      rows.forEach((r, idx) => {
        const id = [...path, String(idx)].join(".")
        if (r.codigo && codigos.has(r.codigo)) out[id] = true
        // bucket "pendente" virtual (codigo=null) tambem inicia aberto
        if (r.codigo === null && r.subRows && r.subRows.length > 0) out[id] = true
        walk(r.subRows, [...path, String(idx)])
      })
    }
    walk(tree, [])
    return out
  }, [tree])

  const columns = React.useMemo(
    () => buildColumns({ dataAnterior, data, comparable, unreliableReason }),
    [dataAnterior, data, comparable, unreliableReason],
  )

  const handleRowClick = React.useCallback(
    (row: CosifNodeUI) => {
      // Click abre drill SO em folhas (nivel >= 3 sem children OU nivel >= 4).
      const isLeaf = !row.subRows || row.subRows.length === 0
      const isAnalytic = row.nivel >= 4 || (isLeaf && row.nivel >= 2)
      if (!isAnalytic) return
      onSelectNode?.(row)
    },
    [onSelectNode],
  )

  return (
    <Card className="flex flex-col gap-3 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm text-gray-900 dark:text-gray-50">{title}</h3>
        <span className="rounded-full border border-gray-200 bg-gray-50 px-1.5 text-[11px] text-gray-500 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400">
          {tree.reduce((s, r) => s + countRowsRecursive(r), 0)} contas
        </span>
        <div className="ml-auto flex items-center gap-2">
          <label className="flex cursor-pointer items-center gap-2 text-[12px] text-gray-600 dark:text-gray-400">
            <Switch
              checked={incluirCompensacao}
              onCheckedChange={setIncluirCompensacao}
            />
            Auditoria avancada (compensacao 3/9)
          </label>
        </div>
      </div>
      <DataTable
        data={tree}
        columns={columns}
        density="compact"
        showColumnManager={false}
        showDensityToggle={false}
        showExport={false}
        virtualize={false}
        enableExpanding
        getSubRows={(row) => row.subRows}
        defaultExpanded={defaultExpanded}
        expandedColumnId="label"
        rowClassName={rowClass}
        onRowClick={handleRowClick}
        renderEmpty={() => (
          <div className="flex flex-col items-center justify-center gap-1 py-12 text-center">
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Sem dados para a data selecionada
            </p>
            {emptyMessage && (
              <p className="text-xs text-gray-400 dark:text-gray-600">
                {emptyMessage}
              </p>
            )}
          </div>
        )}
      />
    </Card>
  )
}

function countRowsRecursive(r: CosifNodeUI): number {
  return 1 + (r.subRows?.reduce((s, c) => s + countRowsRecursive(c), 0) ?? 0)
}
