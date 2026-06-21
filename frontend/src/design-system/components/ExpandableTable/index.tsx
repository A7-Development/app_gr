// src/design-system/components/ExpandableTable/index.tsx
//
// ExpandableTable — membro "master-detail" da familia canonica de tabelas
// (handoff "Tabela canonica" v2). Mesma GRAMATICA visual do <DataTable>
// (header hairline 28px, linha 32px, tokens de celula, trilho azul) — mas
// cada linha EXPANDE para um painel de detalhe arbitrario (`renderRowDetail`),
// em vez de sub-linhas hierarquicas.
//
// Quando usar:
//   - Logs / execucoes onde a linha abre um detalhe livre (JSON, sub-lista,
//     explicacao). Ex.: historico de syncs, status de fontes (+endpoints),
//     versoes de agente. Substitui o <TableRoot> cru com expand inline.
//
// Quando NAO usar:
//   - Listagem simples sem detalhe -> <DataTable> (modo Exploracao).
//   - Arvore multi-nivel (mesma shape nos filhos) -> <DataTable enableExpanding>.
//   - CRUD com toolbar -> <DataTableShell>.

"use client"

import * as React from "react"
import { RiArrowRightSLine } from "@remixicon/react"

import { cx } from "@/lib/utils"
import { rowHeightClass, type DensityMode } from "@/design-system/tokens/spacing"
import { tableTokens } from "@/design-system/tokens/table"

export type ExpandableAlign = "left" | "right" | "center"

export type ExpandableColumn<T> = {
  /** Id estavel da coluna. */
  id: string
  /** Conteudo do header (string ou node). */
  header: React.ReactNode
  /** Alinhamento de header + celula. Default "left". */
  align?: ExpandableAlign
  /** Classe de largura Tailwind (ex.: "w-8", "w-40"). Opcional. */
  widthClass?: string
  /** Renderiza a celula. Use tableTokens.* para tipografia/cor. */
  cell: (row: T) => React.ReactNode
}

export type ExpandableTableProps<T> = {
  data: T[]
  columns: ExpandableColumn<T>[]
  /** Painel de detalhe exibido quando a linha esta expandida. */
  renderRowDetail: (row: T) => React.ReactNode
  /** Id estavel por linha (chave + estado de expansao). */
  getRowId: (row: T) => string
  /** Linha pode expandir? Default: todas. Quando false, a linha nao mostra
   *  chevron nem e clicavel-pra-expandir (ex.: fonte sem catalogo de endpoints). */
  canExpand?: (row: T) => boolean
  /** Altura de linha. Default "compact" (32px) — default da familia. */
  density?: DensityMode
  loading?: boolean
  skeletonRows?: number
  /** Texto quando data vazio (sem loading). */
  emptyText?: string
  /** Varias linhas abertas ao mesmo tempo (default) ou so uma. */
  multiOpen?: boolean
  /** Linha aberta por padrao (controla o estado inicial). */
  defaultOpenIds?: string[]
  /** Classe extra por linha (ex.: destaque condicional). */
  rowClassName?: (row: T) => string
}

function alignClass(a: ExpandableAlign | undefined): string {
  return a === "right" ? "text-right" : a === "center" ? "text-center" : "text-left"
}

export function ExpandableTable<T>({
  data,
  columns,
  renderRowDetail,
  getRowId,
  canExpand,
  density = "compact",
  loading = false,
  skeletonRows = 6,
  emptyText = "Sem registros.",
  multiOpen = true,
  defaultOpenIds,
  rowClassName,
}: ExpandableTableProps<T>) {
  const [open, setOpen] = React.useState<Set<string>>(
    () => new Set(defaultOpenIds ?? []),
  )

  const toggle = React.useCallback(
    (id: string) => {
      setOpen((prev) => {
        const next = new Set(multiOpen ? prev : [])
        if (prev.has(id)) next.delete(id)
        else next.add(id)
        return next
      })
    },
    [multiOpen],
  )

  const rowH = rowHeightClass(density)
  const totalCols = columns.length + 1 // +1 = coluna do chevron

  return (
    <div className="overflow-auto">
      <table className="w-full border-collapse text-[13px]">
        <thead className="bg-white dark:bg-gray-950">
          <tr>
            {/* Coluna do chevron (hairline) */}
            <th className="w-8 h-7 border-b border-gray-200 px-3 dark:border-gray-800" />
            {columns.map((col) => (
              <th
                key={col.id}
                className={cx(
                  "h-7 border-b border-gray-200 px-3 dark:border-gray-800",
                  tableTokens.header,
                  "text-gray-500 dark:text-gray-400 whitespace-nowrap select-none",
                  alignClass(col.align),
                  col.widthClass,
                )}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>

        <tbody>
          {loading &&
            Array.from({ length: skeletonRows }).map((_, i) => (
              <tr key={`sk-${i}`} className={cx(rowH, "border-b border-gray-100 dark:border-gray-900")}>
                <td colSpan={totalCols} className="px-3">
                  <div className="h-3 w-full animate-pulse rounded bg-gray-100 dark:bg-gray-900" />
                </td>
              </tr>
            ))}

          {!loading && data.length === 0 && (
            <tr>
              <td colSpan={totalCols} className="px-3 py-10 text-center">
                <span className={tableTokens.cellSecondary}>{emptyText}</span>
              </td>
            </tr>
          )}

          {!loading &&
            data.map((row) => {
              const id = getRowId(row)
              const expandable = canExpand ? canExpand(row) : true
              const isOpen = expandable && open.has(id)
              return (
                <React.Fragment key={id}>
                  <tr
                    data-expanded={isOpen}
                    onClick={expandable ? () => toggle(id) : undefined}
                    className={cx(
                      rowH,
                      "border-b border-gray-100 transition-colors duration-75 dark:border-gray-900",
                      expandable && "cursor-pointer",
                      isOpen
                        ? "border-l-2 border-l-blue-500 bg-gray-50 dark:bg-gray-900/50"
                        : "border-l-2 border-l-transparent hover:bg-gray-50 dark:hover:bg-gray-900/50",
                      rowClassName?.(row),
                    )}
                  >
                    <td className="px-3">
                      {expandable && (
                        <RiArrowRightSLine
                          className={cx(
                            "size-4 shrink-0 text-gray-400 transition-transform duration-100 dark:text-gray-500",
                            isOpen && "rotate-90",
                          )}
                          aria-hidden
                        />
                      )}
                    </td>
                    {columns.map((col) => (
                      <td key={col.id} className={cx("px-3", alignClass(col.align))}>
                        {col.cell(row)}
                      </td>
                    ))}
                  </tr>
                  {isOpen && (
                    <tr className="border-b border-gray-100 bg-gray-50 dark:border-gray-900 dark:bg-gray-900/40">
                      <td className="border-l-2 border-l-blue-500" />
                      <td colSpan={columns.length} className="px-3 py-3">
                        {renderRowDetail(row)}
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              )
            })}
        </tbody>
      </table>
    </div>
  )
}
