// src/design-system/components/DataTableShell/index.tsx
//
// DataTableShell — wrapper canonico de listagens CRUD/admin.
//
// Encapsula o pattern usado em /admin/ia/providers (Card + faixa de filtros +
// contador + DataTable) para garantir que TODAS as proximas listagens fiquem
// visualmente identicas. Layout, ordem dos elementos, gaps, classes — tudo
// vem daqui, nao do caller.
//
// Quando usar:
//   - Listagens admin/CRUD (~5-200 rows): Provedores, Usuarios, Etiquetas...
//   - Tabelas com filtros simples (search global + segments single-select).
//
// Quando NAO usar (caia de volta na <DataTable> direta + tableTokens):
//   - Filtros complexos (range sliders, multi-select com Popover).
//   - Footer com agregacoes custom.
//   - Tabelas hierarquicas multi-nivel pesadas (BalanceTable, etc).

"use client"

import * as React from "react"
import type { ColumnDef, VisibilityState } from "@tanstack/react-table"
import type { RemixiconComponentType } from "@remixicon/react"

import { cx } from "@/lib/utils"
import { Button } from "@/components/tremor/Button"
import { Card } from "@/components/tremor/Card"
import { DataTable } from "@/design-system/components/DataTable"
import { EmptyState } from "@/design-system/components/EmptyState"
import { ErrorState } from "@/design-system/components/ErrorState"
import { FilterSearch } from "@/design-system/components/FilterBar"
import { OriginDot } from "@/design-system/components/OriginDot"
import { SegmentSwitch } from "@/design-system/components/SegmentSwitch"
import type { DensityMode } from "@/design-system/tokens/spacing"
import { tableTokens } from "@/design-system/tokens/table"
import type { Provenance } from "@/design-system/types/provenance"

// ───────────────────────────────────────────────────────────────────────────
// Configs
// ───────────────────────────────────────────────────────────────────────────

export type ShellSearchConfig = {
  value: string
  onChange: (next: string) => void
  placeholder?: string
}

/** Uma opcao de segmento — a `filter` e funcao predicado executada em cada row. */
export type ShellSegmentOption<T> = {
  value: string
  label: string
  filter: (row: T) => boolean
}

export type ShellSegmentsConfig<T> = {
  options: ShellSegmentOption<T>[]
  value: string
  onChange: (next: string) => void
  ariaLabel?: string
}

export type ShellEmptyState = {
  icon: RemixiconComponentType
  title: string
  description?: string
  action?: React.ReactNode
}

export type ShellErrorState = {
  title?: string
  description?: string
}

export type DataTableShellProps<T> = {
  // ── Dados ────────────────────────────────────────────────────────────
  data: T[]
  columns: ColumnDef<T, unknown>[]

  // ── Estado da query (opcionais — controlam loading/error externos) ───
  loading?: boolean
  error?: Error | string | null
  onRetry?: () => void

  // ── Filtros (opcionais — Shell renderiza condicionalmente) ──────────
  search?: ShellSearchConfig
  segments?: ShellSegmentsConfig<T>

  /** Substantivo do item para o counter "X de Y {plural}". */
  itemNoun?: { singular: string; plural: string }

  // ── Comportamento ────────────────────────────────────────────────────
  density?: DensityMode
  onRowClick?: (row: T) => void

  // ── Empty states ─────────────────────────────────────────────────────
  /** Mostrado quando data.length === 0 (sem filtros aplicados). */
  emptyState?: ShellEmptyState
  /** Override do estado vazio quando filtros retornam 0 (default: "Nenhum resultado"). */
  filteredEmptyText?: string

  // ── Passthrough da DataTable (raros) ─────────────────────────────────
  enableExpanding?: boolean
  getSubRows?: (row: T) => T[] | undefined
  expandedColumnId?: string
  rowClassName?: (row: T) => string
  initialColumnVisibility?: VisibilityState
  virtualize?: boolean

  // ── Proveniencia (CLAUDE.md §14.1) ────────────────────────────────────
  /**
   * Proveniencia canonica dos dados da tabela.
   * Renderiza dot pequeno no rodape direito do card com tooltip de
   * fonte + adapter@versao + sincronizacao + trust level.
   * Mock = `undefined | null` (dot some).
   */
  provenance?: Provenance | null
}

// ───────────────────────────────────────────────────────────────────────────
// Component
// ───────────────────────────────────────────────────────────────────────────

export function DataTableShell<T>({
  data,
  columns,
  loading,
  error,
  onRetry,
  search,
  segments,
  itemNoun,
  density = "compact",
  onRowClick,
  emptyState,
  filteredEmptyText,
  enableExpanding,
  getSubRows,
  expandedColumnId,
  rowClassName,
  initialColumnVisibility,
  virtualize,
  provenance,
}: DataTableShellProps<T>) {
  // ── Counts agregados (segment ANTES, search depois via globalFilter) ─
  const totalCount = data.length

  const segmentFiltered = React.useMemo<T[]>(() => {
    if (!segments) return data
    const opt = segments.options.find((o) => o.value === segments.value)
    if (!opt) return data
    return data.filter(opt.filter)
  }, [data, segments])

  const visibleCount = React.useMemo(() => {
    const term = (search?.value ?? "").trim().toLowerCase()
    if (!term) return segmentFiltered.length
    return segmentFiltered.filter((row) =>
      Object.values(row as Record<string, unknown>).some(
        (v) => typeof v === "string" && v.toLowerCase().includes(term),
      ),
    ).length
  }, [segmentFiltered, search?.value])

  const segmentOptionsWithCounts = React.useMemo(() => {
    if (!segments) return null
    return segments.options.map((opt) => ({
      value: opt.value,
      label: opt.label,
      count: data.filter(opt.filter).length,
    }))
  }, [segments, data])

  // ── Reset ────────────────────────────────────────────────────────────
  const handleResetFilters = React.useCallback(() => {
    search?.onChange("")
    if (segments && segments.options[0]) {
      segments.onChange(segments.options[0].value)
    }
  }, [search, segments])

  // ── Error state externo ──────────────────────────────────────────────
  if (error && !loading) {
    return (
      <ErrorState
        title="Falha ao carregar"
        description={
          typeof error === "string"
            ? error
            : error instanceof Error
              ? error.message
              : "Tente novamente em alguns instantes."
        }
        action={
          onRetry && (
            <Button variant="secondary" onClick={onRetry}>
              Tentar novamente
            </Button>
          )
        }
      />
    )
  }

  // ── Empty state externo (data totalmente vazio) ──────────────────────
  if (!loading && data.length === 0 && emptyState) {
    return (
      <EmptyState
        icon={emptyState.icon}
        title={emptyState.title}
        description={emptyState.description}
        action={emptyState.action}
      />
    )
  }

  const hasFilterBar = !!search || !!segments || !!itemNoun

  // Counter label (X de Y, ou X cedentes/credenciais/etc).
  const counterLabel = itemNoun
    ? visibleCount === totalCount
      ? `${visibleCount} ${visibleCount === 1 ? itemNoun.singular : itemNoun.plural}`
      : `${visibleCount} de ${totalCount}`
    : null

  return (
    <Card className={cx(tableTokens.cardWrapper, "relative")}>
      {hasFilterBar && (
        <div className={tableTokens.filterBar}>
          {search && (
            <FilterSearch
              value={search.value}
              onChange={(e) => search.onChange(e.currentTarget.value)}
              onClear={() => search.onChange("")}
              placeholder={search.placeholder}
            />
          )}
          {segments && segmentOptionsWithCounts && (
            <SegmentSwitch
              options={segmentOptionsWithCounts}
              value={segments.value}
              onChange={segments.onChange}
              ariaLabel={segments.ariaLabel}
            />
          )}
          {counterLabel && (
            <span className={tableTokens.countLabel} aria-live="polite">
              {counterLabel}
            </span>
          )}
        </div>
      )}

      <DataTable
        data={segmentFiltered}
        columns={columns}
        loading={loading}
        density={density}
        virtualize={virtualize ?? false}
        showColumnManager={false}
        showDensityToggle={false}
        showExport={false}
        globalFilter={search?.value ?? ""}
        onRowClick={onRowClick}
        enableExpanding={enableExpanding}
        getSubRows={getSubRows}
        expandedColumnId={expandedColumnId}
        rowClassName={rowClassName}
        initialColumnVisibility={initialColumnVisibility}
        renderEmpty={(hasFilters) =>
          hasFilters ? (
            <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                {filteredEmptyText ?? "Nenhum resultado para esses filtros"}
              </p>
              <Button variant="ghost" onClick={handleResetFilters}>
                Limpar filtros
              </Button>
            </div>
          ) : (
            <div className="py-12 text-center text-sm text-gray-500 dark:text-gray-400">
              Sem registros disponiveis.
            </div>
          )
        }
      />

      {/* Proveniencia (CLAUDE.md §14.1) — dot pinned no rodape direito do Card.
          Mock (provenance undefined) = nada renderiza. */}
      {provenance && <OriginDot provenance={provenance} variant="pinned" />}
    </Card>
  )
}
