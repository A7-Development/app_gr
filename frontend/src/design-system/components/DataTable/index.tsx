// src/design-system/components/DataTable/index.tsx
// Production DataTable — TanStack Table v8 + TanStack Virtual.
// Adds: column manager, export menu, comfortable density, calculation footer,
//       bulk action animation, error state, loading skeleton.

"use client"

import * as React from "react"
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  getExpandedRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
  type RowSelectionState,
  type VisibilityState,
  type ExpandedState,
} from "@tanstack/react-table"
import { useVirtualizer } from "@tanstack/react-virtual"
import {
  RiArrowUpLine,
  RiArrowDownLine,
  RiArrowUpDownLine,
  RiSettings4Line,
  RiDownloadLine,
  RiArrowRightLine,
  RiErrorWarningLine,
  RiRefreshLine,
} from "@remixicon/react"
import { cx, focusRing } from "@/lib/utils"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/tremor/Popover"
import type { DensityMode } from "@/design-system/tokens/spacing"
import { rowHeightClass } from "@/design-system/tokens/spacing"

export interface DataTableProps<TData> {
  data:                TData[]
  columns:             ColumnDef<TData, unknown>[]
  density?:            DensityMode
  selectable?:         boolean
  onRowClick?:         (row: TData) => void
  renderBulkActions?:  (selectedRows: TData[], clearSelection: () => void) => React.ReactNode
  renderEmpty?:        (hasFilters: boolean) => React.ReactNode
  globalFilter?:       string
  renderFooter?:       (data: TData[]) => React.ReactNode
  className?:          string
  virtualize?:         boolean
  showDensityToggle?:  boolean
  showColumnManager?:  boolean
  /**
   * Estado inicial de visibilidade das colunas (por column id).
   * Ex.: `{ source: false }` esconde a coluna "source" por padrao —
   * usuario pode reativar via ColumnManager se ela estiver disponivel.
   * Default: `{}` (todas visiveis).
   */
  initialColumnVisibility?: VisibilityState
  showExport?:         boolean
  onExport?:           (format: "csv" | "xlsx" | "pdf", rows: TData[]) => void
  error?:              string | null
  onRetry?:            () => void
  loading?:            boolean
  /**
   * Optional callback to compute a className for each `<tr>`. Receives the row
   * data and returns extra Tailwind classes (e.g. for section/subtotal/total
   * rows in a balance-sheet-style table). Additive — does not override the
   * canonical row styling (height, borders, hover, selection).
   */
  rowClassName?:       (row: TData) => string
  // ── Expand/collapse (hierarquical rows via TanStack getExpandedRowModel) ──
  /**
   * Habilita expand/collapse de sub-rows. Quando true, requer `getSubRows`.
   * Default: false (tabela continua flat como antes).
   */
  enableExpanding?:    boolean
  /**
   * Acessor que devolve sub-rows de uma linha. Retorne `undefined` para folhas.
   */
  getSubRows?:         (row: TData) => TData[] | undefined
  /**
   * Estado inicial de expansao. Default: `{}` (tudo colapsado).
   * Use `true` para expandir tudo, ou objeto `{ rowId: true }` para abrir
   * linhas especificas.
   */
  defaultExpanded?:    ExpandedState
  /**
   * Id da coluna onde o chevron de expand renderiza (default: id da primeira
   * coluna acessor). Use quando a primeira coluna nao for a apropriada
   * (ex.: tem coluna de checkbox antes).
   */
  expandedColumnId?:   string
}

const DENSITY_ICONS: Record<DensityMode, React.ReactNode> = {
  compact: (
    <svg viewBox="0 0 14 14" className="size-3.5" fill="none">
      <line x1="2" y1="2.5"  x2="12" y2="2.5"  stroke="currentColor" strokeWidth="1.5"/>
      <line x1="2" y1="5.5"  x2="12" y2="5.5"  stroke="currentColor" strokeWidth="1.5"/>
      <line x1="2" y1="8.5"  x2="12" y2="8.5"  stroke="currentColor" strokeWidth="1.5"/>
      <line x1="2" y1="11.5" x2="12" y2="11.5" stroke="currentColor" strokeWidth="1.5"/>
    </svg>
  ),
  default: (
    <svg viewBox="0 0 14 14" className="size-3.5" fill="none">
      <line x1="2" y1="3"  x2="12" y2="3"  stroke="currentColor" strokeWidth="1.5"/>
      <line x1="2" y1="7"  x2="12" y2="7"  stroke="currentColor" strokeWidth="1.5"/>
      <line x1="2" y1="11" x2="12" y2="11" stroke="currentColor" strokeWidth="1.5"/>
    </svg>
  ),
  comfortable: (
    <svg viewBox="0 0 14 14" className="size-3.5" fill="none">
      <line x1="2" y1="3.5" x2="12" y2="3.5" stroke="currentColor" strokeWidth="1.5"/>
      <line x1="2" y1="9.5" x2="12" y2="9.5" stroke="currentColor" strokeWidth="1.5"/>
    </svg>
  ),
}

function SortIcon({ direction }: { direction: "asc" | "desc" | false }) {
  if (direction === "asc")  return <RiArrowUpLine    className="ml-1 size-3 shrink-0 text-blue-500" />
  if (direction === "desc") return <RiArrowDownLine  className="ml-1 size-3 shrink-0 text-blue-500" />
  return <RiArrowUpDownLine className="ml-1 size-3 shrink-0 text-gray-300 dark:text-gray-600" />
}

function ColumnManager<TData>({
  table,
}: {
  table: ReturnType<typeof useReactTable<TData>>
}) {
  const allColumns = table.getAllLeafColumns().filter((c) => c.id !== "select")
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label="Gerenciar colunas"
          className={cx(
            "flex h-7 w-7 items-center justify-center rounded border",
            "border-gray-200 dark:border-gray-800",
            "bg-white dark:bg-gray-950",
            "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200",
            "transition-colors duration-100",
            focusRing,
          )}
        >
          <RiSettings4Line className="size-3.5" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" sideOffset={6} className="w-52 p-2">
        <p className="mb-1.5 px-1 text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-400 dark:text-gray-600">
          Colunas visíveis
        </p>
        <div className="space-y-0.5">
          {allColumns.map((column) => (
            <label
              key={column.id}
              className={cx(
                "flex cursor-pointer items-center gap-2 rounded px-2 py-1.5",
                "text-sm text-gray-700 dark:text-gray-300",
                "hover:bg-gray-100 dark:hover:bg-gray-800",
              )}
            >
              <input
                type="checkbox"
                checked={column.getIsVisible()}
                onChange={column.getToggleVisibilityHandler()}
                className="size-3.5 rounded border-gray-300 text-blue-500 accent-blue-500"
              />
              <span className="flex-1 truncate capitalize">{String(column.columnDef.header ?? column.id)}</span>
            </label>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  )
}

function ExportMenu<TData>({
  onExport,
  rows,
}: {
  onExport: (format: "csv" | "xlsx" | "pdf", rows: TData[]) => void
  rows: TData[]
}) {
  const [withLineage, setWithLineage] = React.useState(true)
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cx(
            "inline-flex h-7 items-center gap-1.5 rounded border px-2.5 text-xs font-medium",
            "border-gray-200 dark:border-gray-800",
            "bg-white dark:bg-gray-950",
            "text-gray-700 dark:text-gray-300",
            "hover:bg-gray-50 dark:hover:bg-gray-900",
            "transition-colors duration-100",
            focusRing,
          )}
        >
          <RiDownloadLine className="size-3.5" aria-hidden="true" />
          Exportar
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" sideOffset={6} className="w-52 p-2">
        <p className="mb-1.5 px-1 text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-400 dark:text-gray-600">
          Formato
        </p>
        {(["csv", "xlsx", "pdf"] as const).map((fmt) => (
          <button
            key={fmt}
            type="button"
            onClick={() => onExport(fmt, rows)}
            className={cx(
              "flex w-full items-center gap-2 rounded px-2 py-1.5 text-sm",
              "text-gray-700 dark:text-gray-300",
              "hover:bg-gray-100 dark:hover:bg-gray-800",
              "transition-colors duration-100",
              focusRing,
            )}
          >
            <RiArrowRightLine className="size-3.5 text-gray-400" aria-hidden="true" />
            {fmt.toUpperCase()}
          </button>
        ))}
        <div className="my-1.5 border-t border-gray-100 dark:border-gray-800" />
        <label className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-xs text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800">
          <input
            type="checkbox"
            checked={withLineage}
            onChange={(e) => setWithLineage(e.target.checked)}
            className="size-3 rounded accent-blue-500"
          />
          Incluir lineage de dados
        </label>
      </PopoverContent>
    </Popover>
  )
}

function LoadingSkeleton({ rows = 8, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div className="animate-pulse">
      <div className="flex gap-4 border-b border-gray-100 dark:border-gray-900 px-3 py-2">
        {Array(cols).fill(null).map((_, i) => (
          <div key={i} className="h-3 flex-1 rounded bg-gray-100 dark:bg-gray-800" />
        ))}
      </div>
      {Array(rows).fill(null).map((_, ri) => (
        <div key={ri} className="flex gap-4 border-b border-gray-50 dark:border-gray-900/50 px-3 py-2.5">
          {Array(cols).fill(null).map((_, ci) => (
            <div
              key={ci}
              className="h-3 flex-1 rounded bg-gray-50 dark:bg-gray-900"
              style={{ opacity: 1 - ri * 0.08 }}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3">
      <RiErrorWarningLine className="size-8 text-red-400" aria-hidden="true" />
      <div className="text-center">
        <p className="text-sm font-medium text-gray-900 dark:text-gray-50">Falha ao carregar dados</p>
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{message}</p>
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className={cx(
            "inline-flex items-center gap-1.5 rounded border px-3 py-1.5 text-xs font-medium",
            "border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950",
            "text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-900",
            "transition-colors duration-100",
            focusRing,
          )}
        >
          <RiRefreshLine className="size-3.5" aria-hidden="true" />
          Tentar novamente
        </button>
      )}
    </div>
  )
}

export function DataTable<TData>({
  data,
  columns,
  density:           densityProp = "default",
  selectable        = false,
  onRowClick,
  renderBulkActions,
  renderEmpty,
  globalFilter      = "",
  renderFooter,
  className,
  virtualize,
  showDensityToggle = true,
  showColumnManager = true,
  showExport        = false,
  onExport,
  error             = null,
  onRetry,
  loading           = false,
  rowClassName,
  enableExpanding   = false,
  getSubRows,
  defaultExpanded   = {},
  expandedColumnId,
  initialColumnVisibility,
}: DataTableProps<TData>) {
  const [sorting, setSorting]               = React.useState<SortingState>([])
  const [rowSelection, setRowSelection]     = React.useState<RowSelectionState>({})
  const [colVisibility, setColVisibility]   = React.useState<VisibilityState>(
    initialColumnVisibility ?? {},
  )
  const [density, setDensity]               = React.useState<DensityMode>(densityProp)
  const [expanded, setExpanded]             = React.useState<ExpandedState>(defaultExpanded)

  const parentRef = React.useRef<HTMLDivElement>(null)
  const shouldVirtualize = virtualize ?? data.length > 100

  const table = useReactTable({
    data,
    columns,
    state: {
      sorting,
      rowSelection,
      globalFilter,
      columnVisibility: colVisibility,
      expanded,
    },
    onSortingChange:          setSorting,
    onRowSelectionChange:     setRowSelection,
    onColumnVisibilityChange: setColVisibility,
    onExpandedChange:         setExpanded,
    getCoreRowModel:          getCoreRowModel(),
    getSortedRowModel:        getSortedRowModel(),
    getFilteredRowModel:      getFilteredRowModel(),
    getExpandedRowModel:      enableExpanding ? getExpandedRowModel() : undefined,
    getSubRows:               enableExpanding ? getSubRows : undefined,
    enableRowSelection:       selectable,
    enableExpanding,
    enableMultiSort:          true,
    globalFilterFn:           "includesString",
  })

  // Resolve qual coluna recebe o chevron (default: primeira coluna).
  const expandColId = expandedColumnId ?? (columns[0] as { id?: string; accessorKey?: string })?.id
    ?? (columns[0] as { accessorKey?: string })?.accessorKey ?? null

  const { rows } = table.getRowModel()

  const rowVirtualizer = useVirtualizer({
    count: shouldVirtualize ? rows.length : 0,
    getScrollElement: () => parentRef.current,
    estimateSize: () => (density === "compact" ? 32 : density === "comfortable" ? 48 : 40),
    overscan: 12,
  })

  const virtualRows = shouldVirtualize ? rowVirtualizer.getVirtualItems() : null
  const totalVirtH  = shouldVirtualize ? rowVirtualizer.getTotalSize() : 0

  const selectedFlatRows = table.getSelectedRowModel().flatRows.map((r) => r.original)
  const hasSelection     = selectedFlatRows.length > 0
  const filteredData     = rows.map((r) => r.original)

  const rowH = rowHeightClass(density)
  const showToolbar = showDensityToggle || showColumnManager || showExport

  return (
    <div className={cx("relative flex flex-col overflow-hidden", className)}>
      {showToolbar && (
        <div className="flex shrink-0 items-center justify-end gap-2 border-b border-gray-100 dark:border-gray-900 px-3 py-1.5">
          {showDensityToggle && (
            <div className="flex items-center rounded border border-gray-200 dark:border-gray-800 overflow-hidden">
              {(["compact", "default", "comfortable"] as DensityMode[]).map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setDensity(d)}
                  aria-label={`Densidade ${d}`}
                  aria-pressed={density === d}
                  className={cx(
                    "flex h-6 w-7 items-center justify-center transition-colors duration-100",
                    density === d
                      ? "bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-200"
                      : "text-gray-400 dark:text-gray-600 hover:text-gray-600 dark:hover:text-gray-400",
                  )}
                >
                  {DENSITY_ICONS[d]}
                </button>
              ))}
            </div>
          )}
          {showColumnManager && <ColumnManager table={table} />}
          {showExport && onExport && (
            <ExportMenu onExport={onExport} rows={filteredData} />
          )}
        </div>
      )}

      {loading ? (
        <LoadingSkeleton cols={columns.length} />
      ) : error ? (
        <ErrorState message={error} onRetry={onRetry} />
      ) : (
        <div ref={parentRef} className="flex-1 overflow-auto">
          <table className="w-full border-collapse text-[13px]">
            <thead className="sticky top-0 z-[1] bg-gray-50 dark:bg-gray-900/60">
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id}>
                  {hg.headers.map((header) => {
                    // Header alignment via column meta — alinha o titulo da coluna
                    // ao alinhamento dos dados. Default: left. Use `meta: { align: "right" }`
                    // em colunas numericas (valores, deltas) para alinhar a direita.
                    const align = (header.column.columnDef.meta as { align?: "left" | "right" | "center" } | undefined)?.align ?? "left"
                    return (
                      <th
                        key={header.id}
                        colSpan={header.colSpan}
                        style={{ width: header.getSize() !== 150 ? header.getSize() : undefined }}
                        className={cx(
                          "h-7 border-b border-gray-200 dark:border-gray-800 px-4",
                          "text-[10px] font-semibold uppercase tracking-[0.05em]",
                          "text-gray-400 dark:text-gray-500 whitespace-nowrap select-none",
                          align === "right" ? "text-right" : align === "center" ? "text-center" : "text-left",
                          header.column.getCanSort() && "cursor-pointer hover:text-gray-700 dark:hover:text-gray-300",
                        )}
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        {header.isPlaceholder ? null : (
                          <span className={cx(
                            "inline-flex items-center",
                            align === "right" && "justify-end",
                            align === "center" && "justify-center",
                          )}>
                            {flexRender(header.column.columnDef.header, header.getContext())}
                            {header.column.getCanSort() && (
                              <SortIcon direction={header.column.getIsSorted()} />
                            )}
                          </span>
                        )}
                      </th>
                    )
                  })}
                </tr>
              ))}
            </thead>

            <tbody>
              {shouldVirtualize && virtualRows && virtualRows.length > 0 && (
                <tr style={{ height: virtualRows[0].start }}><td /></tr>
              )}

              {(shouldVirtualize && virtualRows
                ? virtualRows.map((vr) => rows[vr.index])
                : rows
              ).map((row) => {
                const isSel = row.getIsSelected()
                return (
                  <tr
                    key={row.id}
                    data-selected={isSel}
                    onClick={() => onRowClick?.(row.original)}
                    className={cx(
                      rowH,
                      "border-b border-gray-100 dark:border-gray-900",
                      "transition-colors duration-75",
                      onRowClick && "cursor-pointer",
                      isSel
                        ? "bg-blue-50 dark:bg-blue-500/10 border-l-2 border-l-blue-500"
                        : "border-l-2 border-l-transparent hover:bg-gray-50 dark:hover:bg-gray-900/50",
                      rowClassName?.(row.original),
                    )}
                  >
                    {row.getVisibleCells().map((cell) => {
                      const isExpandCol = enableExpanding && expandColId !== null && cell.column.id === expandColId
                      const depth = row.depth
                      const canExpand = row.getCanExpand()
                      const isExpanded = row.getIsExpanded()
                      return (
                        <td key={cell.id} className="px-3 text-gray-900 dark:text-gray-50">
                          {isExpandCol ? (
                            <span className="inline-flex items-center gap-1.5">
                              {/* Indent baseado em depth (16px por nivel) */}
                              {depth > 0 && (
                                <span aria-hidden="true" style={{ display: "inline-block", width: depth * 16 }} />
                              )}
                              {/* Chevron clicavel quando ha sub-rows */}
                              {canExpand ? (
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    row.getToggleExpandedHandler()()
                                  }}
                                  className={cx(
                                    "inline-flex size-4 shrink-0 items-center justify-center rounded",
                                    "text-gray-400 hover:text-gray-700 hover:bg-gray-100",
                                    "dark:text-gray-500 dark:hover:text-gray-200 dark:hover:bg-gray-800",
                                  )}
                                  aria-label={isExpanded ? "Recolher" : "Expandir"}
                                  aria-expanded={isExpanded}
                                >
                                  <span
                                    aria-hidden="true"
                                    className={cx(
                                      "inline-block font-mono text-[12px] leading-none transition-transform duration-100",
                                      isExpanded && "rotate-90",
                                    )}
                                  >
                                    {">"}
                                  </span>
                                </button>
                              ) : (
                                /* Sem chevron: placeholder pra alinhar com linhas que tem */
                                <span aria-hidden="true" className="inline-block size-4 shrink-0" />
                              )}
                              <span className="min-w-0 flex-1">
                                {flexRender(cell.column.columnDef.cell, cell.getContext())}
                              </span>
                            </span>
                          ) : (
                            flexRender(cell.column.columnDef.cell, cell.getContext())
                          )}
                        </td>
                      )
                    })}
                  </tr>
                )
              })}

              {rows.length === 0 && (
                <tr>
                  <td colSpan={columns.length} className="py-16 text-center">
                    {renderEmpty
                      ? renderEmpty(!!globalFilter)
                      : (
                        <div className="flex flex-col items-center gap-2 text-gray-400 dark:text-gray-600">
                          <p className="text-sm">Nenhum resultado para os filtros atuais</p>
                          {globalFilter && (
                            <p className="text-xs">para &quot;{globalFilter}&quot;</p>
                          )}
                        </div>
                      )}
                  </td>
                </tr>
              )}

              {shouldVirtualize && virtualRows && virtualRows.length > 0 && (
                <tr style={{ height: totalVirtH - (virtualRows.at(-1)?.end ?? 0) }}><td /></tr>
              )}
            </tbody>

            {renderFooter && rows.length > 0 && (
              <tfoot className="sticky bottom-0 bg-gray-50 dark:bg-gray-900">
                {renderFooter(filteredData)}
              </tfoot>
            )}
          </table>
        </div>
      )}

      {hasSelection && renderBulkActions && (
        <div
          className={cx(
            "absolute bottom-4 left-1/2 z-20 -translate-x-1/2",
            "animate-slide-up-and-fade",
          )}
        >
          <div className={cx(
            "flex items-center gap-3 rounded-lg px-5 py-2.5",
            "bg-gray-900 dark:bg-gray-800 text-white",
            "shadow-xl ring-1 ring-black/10",
          )}>
            <span className="text-sm font-medium">
              {selectedFlatRows.length} selecionada{selectedFlatRows.length !== 1 ? "s" : ""}
            </span>
            <span className="h-4 w-px bg-white/20" aria-hidden="true" />
            {renderBulkActions(selectedFlatRows, () => setRowSelection({}))}
          </div>
        </div>
      )}
    </div>
  )
}

export * from "./cells"
