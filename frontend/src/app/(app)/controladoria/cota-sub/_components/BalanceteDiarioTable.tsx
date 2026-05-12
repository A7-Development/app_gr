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
import { RiInformationLine } from "@remixicon/react"

import { cx } from "@/lib/utils"
import { Card } from "@/components/tremor/Card"
import { Switch } from "@/components/tremor/Switch"
import { DataTable } from "@/design-system/components/DataTable"
import { tableTokens } from "@/design-system/tokens/table"

import {
  type CosifNodeUI,
  buildCosifTree,
  defaultExpandedCodigos,
} from "../_lib/cosif"

import type { ClasseBreakdown, CosifNode, CosifRowDiff } from "@/lib/api-client"

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
  if (row._isResultRow) {
    return cx(
      "!border-l-0 !cursor-default",
      "bg-gray-100 dark:bg-gray-900",
      "font-semibold",
    )
  }
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
// Contraparte chip — paper row badge (emitente / gestor)
// ─────────────────────────────────────────────────────────────────────────────
//
// Substituiu o chip de status (novo/alterado/removido) que era redundante
// com os deltas. Agora carrega a CONTRAPARTE — emitente do papel (renda fixa,
// ex.: SYSTEMPA, SYLVIOSA, METALYSE) ou gestor do fundo (cota fundo, ex.:
// ITAU). Visual neutro porque e identificacao, nao estado.

const fmtQtde = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 4,
})

function ContrapartChip({ label }: { label: string }) {
  return (
    <span
      className={cx(
        "ml-2 inline-block rounded px-1.5 text-[10px] font-medium",
        "bg-gray-100 text-gray-600",
        "dark:bg-gray-800 dark:text-gray-400",
      )}
    >
      {label}
    </span>
  )
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
    header: () => (
      <span className="inline-flex items-center gap-1">
        Conta
        <span
          title={
            "Codigo COSIF (BACEN) — primeiro digito agrupa por macrogrupo:\n" +
            "  1, 2, 3  =  Ativo (3 = compensacao)\n" +
            "  4, 5, 9  =  Passivo (9 = compensacao)\n" +
            "  6        =  Patrimonio Liquido\n" +
            "  7, 8     =  Resultado (receitas / despesas)"
          }
          className="inline-flex cursor-help text-gray-400 dark:text-gray-600"
          aria-label="Significado dos codigos COSIF"
        >
          <RiInformationLine className="h-3.5 w-3.5" />
        </span>
      </span>
    ),
    size:   460,
    cell:   (info) => {
      const row = info.row.original
      const nome = info.getValue<string>()
      const baseTrunc = "block max-w-full truncate whitespace-nowrap"
      // Linha "Resultado do dia": label uppercase tracking, sem codigo.
      if (row._isResultRow) {
        return (
          <span
            title={row._resultLabel}
            className={cx(
              baseTrunc,
              "text-[11px] uppercase tracking-wide font-semibold",
              "text-gray-700 dark:text-gray-200",
            )}
          >
            {row._resultLabel}
          </span>
        )
      }
      // Linha de classe sintetica (Sr/Mez/Sub): sem codigo, sem chip.
      // Tipografia mais leve pra diferenciar de conta COSIF real.
      if (row._isClasseRow) {
        return (
          <span
            title={row._classeLabel}
            className={cx(
              baseTrunc,
              tableTokens.cellSecondary,
              "italic",
            )}
          >
            {row._classeLabel}
          </span>
        )
      }
      // Papel sintetico (silver row): codigo (se houver) + descricao + chip
      // de contraparte (emitente / gestor). Codigo em mono pra alinhar com
      // chip do COSIF analitico; descricao em texto normal.
      if (row._isPaperRow) {
        const codigo      = row._paperCodigo
        const desc        = row._paperNome ?? ""
        const contraparte = row._paperContraparte
        const fullTitle = [codigo, desc, contraparte].filter(Boolean).join(" · ")
        return (
          <span
            title={fullTitle}
            className={cx(baseTrunc, tableTokens.cellText)}
          >
            {codigo ? (
              <span
                className={cx(
                  "mr-2 inline-block font-mono text-[10px] tabular-nums",
                  "text-gray-400 dark:text-gray-600",
                )}
              >
                {codigo}
              </span>
            ) : null}
            {desc}
            {contraparte ? <ContrapartChip label={contraparte} /> : null}
          </span>
        )
      }
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
      if (row._isClasseRow) return null
      if (row._isPaperRow) return null
      if (row._isResultRow) return null
      if (row.nivel === 0 || row.nivel === 1) return null
      return (
        <span className={cx(tableTokens.cellSecondary, "font-mono")}>
          {v === "?" ? "—" : v}
        </span>
      )
    },
  }) as ColumnDef<CosifNodeUI, unknown>

  // Qtd — so faz sentido em paper rows. Demais retornam null (vazio).
  const qtdCol = col.display({
    id:     "qtd",
    header: "Qtd",
    size:   80,
    meta:   { align: "right" },
    cell:   (info) => {
      const row = info.row.original
      if (!row._isPaperRow) return null
      const q = row._paperQtdD0 ?? row._paperQtdD1
      if (q == null) return null
      return (
        <div
          style={{ textAlign: "right" }}
          className={cx(tableTokens.cellNumberSecondary)}
        >
          {fmtQtde.format(q)}
        </div>
      )
    },
  }) as ColumnDef<CosifNodeUI, unknown>

  // Idx — indexador do papel (CDI+X%, IPCA+Y%, etc).
  const idxCol = col.display({
    id:     "idx",
    header: "Idx",
    size:   100,
    cell:   (info) => {
      const row = info.row.original
      if (!row._isPaperRow) return null
      const idx = row._paperIndexador
      if (!idx) return null
      return (
        <span
          title={idx}
          className={cx(
            "block max-w-full truncate whitespace-nowrap",
            tableTokens.cellSecondary,
          )}
        >
          {idx}
        </span>
      )
    },
  }) as ColumnDef<CosifNodeUI, unknown>

  // Pivot-table behavior: quando um no sintetico esta expandido, esconde o
  // saldo dele (os filhos ja totalizam — exibir o agregado seria redundante
  // e visualmente confuso). Quando colapsado, o saldo volta a aparecer como
  // "subtotal" do grupo.
  function hidesAggregate(row: import("@tanstack/react-table").Row<CosifNodeUI>): boolean {
    if (!row.getCanExpand()) return false
    return row.getIsExpanded()
  }

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
      if (hidesAggregate(info.row)) return null
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
      if (hidesAggregate(info.row)) return null
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
      if (hidesAggregate(info.row)) return null
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
      if (hidesAggregate(info.row)) return null
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

  return [labelCol, naturezaCol, qtdCol, idxCol, d1Col, d0Col, deltaCol, deltaPctCol]
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export type BalanceteDiarioTableProps = {
  nodes:         readonly CosifNode[]
  /** Quebra Sr/Mez/Sub por COSIF — injetada como subRows sinteticas nas
   *  contas analiticas correspondentes (ex.: 6.1.1.70.30.001 Cotas Emitidas). */
  classeBreakdownPorCosif?: Record<string, readonly ClasseBreakdown[]>
  /** Diff papel-a-papel por conta analitica — injetado como folhas terminais
   *  na arvore COSIF. Drill substituiu o sheet lateral. */
  rowsPorCosif?: Record<string, readonly CosifRowDiff[]>
  /** Quando passado, injeta linha bold no rodape com o resultado do dia. */
  resultado?: {
    label?:     string
    d_minus_1: number
    d_zero:    number
    delta:     number
    delta_pct: number
  }
  data?:         string  // ISO D0
  dataAnterior?: string  // ISO D-1
  emptyMessage?: string
  /** Callback ao clicar numa conta analitica — abre o CosifDrillSheet
   *  (so com explicacoes, ja que papeis sao mostrados na propria tabela). */
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
  classeBreakdownPorCosif,
  rowsPorCosif,
  resultado,
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
    () => buildCosifTree(nodes, {
      incluirCompensacao,
      classeBreakdownPorCosif,
      rowsPorCosif,
      resultado,
    }),
    [nodes, incluirCompensacao, classeBreakdownPorCosif, rowsPorCosif, resultado],
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
      // Linhas sinteticas (classe Sr/Mez/Sub, papel individual, resultado)
      // sao terminais — sem drill proprio. So conta COSIF abre o sheet.
      if (row._isClasseRow || row._isPaperRow || row._isResultRow) return
      // Click abre drill em folhas analiticas (nivel >= 4) ou contas analiticas
      // que viraram nao-leaf so por causa de subRows sinteticas (classe/papel).
      const realSubRows = (row.subRows ?? []).filter(
        (s) => !s._isClasseRow && !s._isPaperRow,
      )
      const isLeaf = realSubRows.length === 0
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
