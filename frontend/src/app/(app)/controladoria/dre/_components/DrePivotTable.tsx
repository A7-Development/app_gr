"use client"

/**
 * DrePivotTable — protagonista da pagina DRE (Z4 hero).
 *
 * Tabela hierarquica grupo > subgrupo > descricao pivotada por competencia.
 * Cada celula = contribuicao liquida da linha ao resultado naquela
 * competencia (positivo quando receita liquida, negativo quando despesa /
 * PDD / comissao). Soma das linhas = resultado liquido do periodo.
 *
 * DRE classica e UMA view consolidada — sem toggle de medida. Analises
 * paralelas (por produto, por cliente, etc) entram como rotas/L3 separadas.
 *
 * Backend: GET /controladoria/dre/pivot (DrePivotResponse).
 *
 * Click numa linha de descricao -> dispara `onDrillFornecedor(row)` para
 * abrir o FornecedoresDrillSheet.
 */

import * as React from "react"
import {
  type ColumnDef,
  type ExpandedState,
  createColumnHelper,
} from "@tanstack/react-table"

import { cx } from "@/lib/utils"
import { Card } from "@/components/tremor/Card"
import { DataTable } from "@/design-system/components/DataTable"
import { tableTokens } from "@/design-system/tokens/table"

import type {
  DreFornecedorNode,
  DreGrupo,
  DrePivotResponse,
} from "@/lib/api-client"

// ─────────────────────────────────────────────────────────────────────────────
// Formatters
// ─────────────────────────────────────────────────────────────────────────────

const fmtBRLCompact = new Intl.NumberFormat("pt-BR", {
  notation: "compact",
  style: "currency",
  currency: "BRL",
  minimumFractionDigits: 0,
  maximumFractionDigits: 1,
})

const fmtMonthShort = (iso: string): string => {
  const [, m] = iso.split("-")
  const labels = ["", "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
  const idx = Number(m)
  return labels[idx] ?? iso
}

function formatValor(v: number): string {
  if (v === 0) return "—"
  if (v < 0) return `(${fmtBRLCompact.format(Math.abs(v))})`
  return fmtBRLCompact.format(v)
}

// ─────────────────────────────────────────────────────────────────────────────
// Row tree — flat shape consumido pela DataTable
// ─────────────────────────────────────────────────────────────────────────────

type CellByCompetencia = Record<string, number>

type Row = {
  id:       string
  kind:     "grupo" | "subgrupo" | "descricao" | "fornecedor"
  label:    string
  /** Identificacao secundaria (CPF/CNPJ) — so usado em rows de fornecedor. */
  sublabel?: string
  /** Resultado por competencia (chave = YYYY-MM-DD). */
  valores:  CellByCompetencia
  /** Resultado total no periodo inteiro. */
  totalResultado: number
  grupoDre: string
  subgrupo?:  string
  descricao?: string
  subRows?: Row[]
}

/**
 * Decide se uma descricao deve expandir pra mostrar fornecedores.
 *
 * Regra: expande quando ha **pelo menos 1 fornecedor identificado** (com
 * `fornecedor` OU `fornecedorDocumento` nao-null). Descricoes onde todos
 * fornecedores sao "Sem identificacao" (vide RECEITA_OPERACIONAL, PDD,
 * COMISSAO no silver) ficam como folha — expandir mostraria so uma linha
 * trivial "Sem identificacao" igual ao total da descricao.
 */
function hasIdentifiedFornecedor(fornecedores: DreFornecedorNode[]): boolean {
  return fornecedores.some((f) => f.fornecedor != null || f.fornecedorDocumento != null)
}

function fornecedorLabel(f: DreFornecedorNode): string {
  if (f.fornecedor) return f.fornecedor
  if (f.fornecedorDocumento) return f.fornecedorDocumento
  return "Sem identificacao"
}

function toCellMap(valores: { competencia: string; resultado: number }[]): CellByCompetencia {
  const m: CellByCompetencia = {}
  for (const v of valores) m[v.competencia] = v.resultado
  return m
}

function buildTree(pivot: DrePivotResponse): Row[] {
  return pivot.grupos.map((g) => buildGrupoRow(g))
}

function buildGrupoRow(g: DreGrupo): Row {
  return {
    id:             `g:${g.grupoDre}`,
    kind:           "grupo",
    label:          g.grupoDre,
    valores:        toCellMap(g.valores),
    totalResultado: g.totais.resultado,
    grupoDre:       g.grupoDre,
    subRows:        g.subgrupos.map((s) => ({
      id:             `g:${g.grupoDre}|s:${s.subgrupo}`,
      kind:           "subgrupo" as const,
      label:          s.subgrupo,
      valores:        toCellMap(s.valores),
      totalResultado: s.totais.resultado,
      grupoDre:       g.grupoDre,
      subgrupo:       s.subgrupo,
      subRows:        s.descricoes.map((d) => {
        const expand = hasIdentifiedFornecedor(d.fornecedores)
        return {
          id:             `g:${g.grupoDre}|s:${s.subgrupo}|d:${d.descricao}`,
          kind:           "descricao" as const,
          label:          d.descricao,
          valores:        toCellMap(d.valores),
          totalResultado: d.totais.resultado,
          grupoDre:       g.grupoDre,
          subgrupo:       s.subgrupo,
          descricao:      d.descricao,
          subRows:        expand
            ? d.fornecedores.map((f, idx) => ({
                id:             `g:${g.grupoDre}|s:${s.subgrupo}|d:${d.descricao}|f:${f.fornecedorDocumento ?? f.fornecedor ?? `sem-id-${idx}`}`,
                kind:           "fornecedor" as const,
                label:          fornecedorLabel(f),
                sublabel:       f.fornecedorDocumento ?? undefined,
                valores:        toCellMap(f.valores),
                totalResultado: f.totais.resultado,
                grupoDre:       g.grupoDre,
                subgrupo:       s.subgrupo,
                descricao:      d.descricao,
              }))
            : undefined,
        }
      }),
    })),
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Styling por nivel (mesmo padrao do BalanceteDiarioTable)
// ─────────────────────────────────────────────────────────────────────────────

function rowClass(row: Row): string {
  if (row.kind === "grupo") {
    return cx(
      "!border-l-0 bg-gray-50 dark:bg-gray-900/60",
      "border-y border-y-gray-200 dark:border-y-gray-800",
    )
  }
  if (row.kind === "subgrupo") {
    return "!border-l-0"
  }
  return ""
}

// ─────────────────────────────────────────────────────────────────────────────
// Columns factory — 1 coluna fixa "Linha" + N colunas (1 por competencia) +
// coluna "Total" no fim.
// ─────────────────────────────────────────────────────────────────────────────

const col = createColumnHelper<Row>()

function valorClass(v: number): string {
  if (v === 0) return tableTokens.cellNumberSecondary
  if (v < 0)  return tableTokens.cellNumberNegative
  return tableTokens.cellNumber
}

function buildColumns(opts: {
  competencias: string[]
}): ColumnDef<Row, unknown>[] {
  const { competencias } = opts

  const labelCol = col.accessor("label", {
    id:     "label",
    header: "Linha",
    size:   320,
    cell:   (info) => {
      const row = info.row.original
      const isStrong = row.kind === "grupo" || row.kind === "subgrupo"
      // Fornecedor: nome + chip com CPF/CNPJ (quando ha documento)
      if (row.kind === "fornecedor") {
        return (
          <span
            title={`${row.label}${row.sublabel ? ` · ${row.sublabel}` : ""}`}
            className={cx(
              "flex max-w-full items-center gap-1.5 truncate whitespace-nowrap",
              tableTokens.cellSecondary,
            )}
          >
            <span className="truncate">{row.label}</span>
            {row.sublabel && (
              <span
                className={cx(
                  "shrink-0 rounded px-1.5 text-[10px] font-medium tabular-nums",
                  "bg-gray-100 text-gray-500",
                  "dark:bg-gray-800 dark:text-gray-400",
                )}
              >
                {row.sublabel}
              </span>
            )}
          </span>
        )
      }
      return (
        <span
          title={row.label}
          className={cx(
            "block max-w-full truncate whitespace-nowrap",
            isStrong ? tableTokens.cellStrong : tableTokens.cellText,
          )}
        >
          {row.label}
        </span>
      )
    },
  }) as ColumnDef<Row, unknown>

  const compCols: ColumnDef<Row, unknown>[] = competencias.map((c) => {
    const year = c.split("-")[0]
    const header = `${fmtMonthShort(c)}/${year.slice(2)}`
    return col.display({
      id:     `c:${c}`,
      header: () => <span className="block text-right">{header}</span>,
      size:   100,
      meta:   { align: "right" },
      cell:   (info) => {
        const row = info.row.original
        const v = row.valores[c] ?? 0
        return (
          <div className={cx("text-right", valorClass(v), row.kind === "grupo" && "font-semibold")}>
            {formatValor(v)}
          </div>
        )
      },
    }) as ColumnDef<Row, unknown>
  })

  const totalCol = col.display({
    id:     "total",
    header: () => <span className="block text-right">Total</span>,
    size:   120,
    meta:   { align: "right" },
    cell:   (info) => {
      const row = info.row.original
      const v = row.totalResultado
      return (
        <div className={cx("text-right font-semibold", valorClass(v))}>
          {formatValor(v)}
        </div>
      )
    },
  }) as ColumnDef<Row, unknown>

  return [labelCol, ...compCols, totalCol]
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export type DrePivotTableProps = {
  pivot?:    DrePivotResponse
  loading?:  boolean
}

export function DrePivotTable({ pivot, loading }: DrePivotTableProps) {
  const tree = React.useMemo<Row[]>(
    () => (pivot ? buildTree(pivot) : []),
    [pivot],
  )

  const columns = React.useMemo(
    () => buildColumns({ competencias: pivot?.competencias ?? [] }),
    [pivot],
  )

  // Default: grupos expandidos, subgrupos colapsados (200+ descricoes ficaria
  // ruidoso se tudo aberto). Recalcula quando a arvore muda.
  const defaultExpanded = React.useMemo<ExpandedState>(() => {
    if (!pivot) return {}
    const exp: Record<string, boolean> = {}
    for (const g of pivot.grupos) {
      exp[`g:${g.grupoDre}`] = true
    }
    return exp
  }, [pivot])

  // Rodape: resultado liquido por competencia + total do periodo. Linha fixa
  // fora da DataTable pra ficar sempre visivel quando virem 100+ descricoes
  // expandidas.
  const totalCells = pivot?.valoresTotal ?? []
  const totalResultado = pivot?.totais.resultado ?? 0

  return (
    <Card className="flex flex-col gap-3 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm text-gray-900 dark:text-gray-50">
          Demonstrativo do Resultado
        </h3>
        {pivot && (
          <span className="rounded-full border border-gray-200 bg-gray-50 px-1.5 text-[11px] text-gray-500 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400">
            {pivot.grupos.length} grupos · {pivot.competencias.length} meses
          </span>
        )}
        <span className="ml-auto text-[11px] text-gray-500 dark:text-gray-400">
          Valores em R$ — receita liquida positiva, despesa/PDD/comissao negativa
        </span>
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
        renderEmpty={() => (
          <div className="flex flex-col items-center justify-center gap-1 py-12 text-center">
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {loading ? "Carregando..." : "Sem dados de DRE no periodo selecionado"}
            </p>
          </div>
        )}
      />

      {totalCells.length > 0 && (
        <div className="overflow-x-auto rounded-sm border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900/60">
          <table className="w-full">
            <tbody>
              <tr>
                <td
                  className={cx("px-3 py-2 align-middle", tableTokens.cellStrong)}
                  style={{ width: 320 }}
                >
                  Resultado liquido do periodo
                </td>
                {totalCells.map((c) => (
                  <td
                    key={c.competencia}
                    className={cx("px-2 py-2 text-right font-semibold", valorClass(c.resultado))}
                    style={{ width: 100 }}
                  >
                    {formatValor(c.resultado)}
                  </td>
                ))}
                <td
                  className={cx(
                    "px-3 py-2 text-right font-semibold",
                    valorClass(totalResultado),
                  )}
                  style={{ width: 120 }}
                >
                  {formatValor(totalResultado)}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}
