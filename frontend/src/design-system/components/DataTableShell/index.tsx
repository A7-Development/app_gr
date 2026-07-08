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
//   - Tabelas com filtros simples (search global + segments single-select +
//     statusFilter multi-select "dropdown quieto" do handoff v2).
//
// Quando NAO usar (caia de volta na <DataTable> direta + tableTokens):
//   - Filtros complexos (range sliders, multiplos eixos de multi-select).
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

import { ShellStatusFilter, type ShellStatusTone } from "./ShellStatusFilter"

export { ShellStatusFilter, type ShellStatusTone, type ShellStatusOption } from "./ShellStatusFilter"

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

/** Uma opcao de filtro-pill (modo Triagem/`queue`). O `label` ja inclui a
 *  contagem quando aplicavel (ex.: "Esperando por mim · 1"). */
export type ShellPillOption = { value: string; label: string }

/**
 * Filtros pill do modo **Triagem** (preset `queue`). Substituem os `segments`
 * na toolbar — usados em filas de triagem de workflow (ex.: esteira de credito).
 * A FILTRAGEM e do caller: passe `data` ja filtrado; o Shell so renderiza os
 * pills e dispara `onChange`.
 */
export type ShellPillFiltersConfig = {
  options: ShellPillOption[]
  value: string
  onChange: (next: string) => void
  ariaLabel?: string
}

/** Uma opcao do filtro de status multi-select (dropdown quieto do handoff
 *  Tabela canonica v2). `filter` e o predicado; `tone` pinta dot/valor/pill. */
export type ShellStatusFilterOption<T> = {
  value: string
  label: string
  tone: ShellStatusTone
  filter: (row: T) => boolean
}

/**
 * Filtro de status **multi-select** na toolbar ("dropdown quieto" — aplica no
 * toggle). Selecao vazia = todos. A filtragem e INTERNA (OR entre os status
 * selecionados, combinada com `segments` e `search`); o trigger fechado mostra
 * cor + contagem do filtro ativo. Coexiste com `segments` — use segments para
 * recorte single-select e statusFilter para o eixo de status multi-select.
 */
export type ShellStatusFilterConfig<T> = {
  /** Rotulo no trigger. Default "Status". */
  label?: string
  options: ShellStatusFilterOption<T>[]
  /** Valores selecionados (controlado). Vazio = filtro inativo. */
  value: string[]
  onChange: (next: string[]) => void
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
  /** Filtro de status multi-select ("dropdown quieto" do handoff v2).
   *  Filtragem interna: OR entre selecionados, AND com segments/search. */
  statusFilter?: ShellStatusFilterConfig<T>
  /** Modo Triagem (`queue`): filtros pill no lugar dos segments. Filtragem
   *  e do caller — passe `data` ja filtrado. */
  pillFilters?: ShellPillFiltersConfig

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
  statusFilter,
  pillFilters,
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

  // Status multi-select (OR entre selecionados; vazio = todos) — aplicado
  // DEPOIS do segment e ANTES do search (que roda via globalFilter).
  const statusFiltered = React.useMemo<T[]>(() => {
    if (!statusFilter || statusFilter.value.length === 0) return segmentFiltered
    const preds = statusFilter.options
      .filter((o) => statusFilter.value.includes(o.value))
      .map((o) => o.filter)
    if (preds.length === 0) return segmentFiltered
    return segmentFiltered.filter((row) => preds.some((p) => p(row)))
  }, [segmentFiltered, statusFilter])

  const statusOptionsWithCounts = React.useMemo(() => {
    if (!statusFilter) return null
    return statusFilter.options.map((opt) => ({
      value: opt.value,
      label: opt.label,
      tone: opt.tone,
      count: segmentFiltered.filter(opt.filter).length,
    }))
  }, [statusFilter, segmentFiltered])

  const visibleCount = React.useMemo(() => {
    const term = (search?.value ?? "").trim().toLowerCase()
    if (!term) return statusFiltered.length
    return statusFiltered.filter((row) =>
      Object.values(row as Record<string, unknown>).some(
        (v) => typeof v === "string" && v.toLowerCase().includes(term),
      ),
    ).length
  }, [statusFiltered, search?.value])

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
    statusFilter?.onChange([])
  }, [search, segments, statusFilter])

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
  // No modo Triagem (pillFilters) NAO fazemos early-return: a toolbar de pills
  // precisa continuar visivel mesmo com 0 linhas (senao o usuario fica preso
  // no filtro). Nesse caso o empty e renderizado inline dentro do Card.
  if (!loading && data.length === 0 && emptyState && !pillFilters) {
    return (
      <EmptyState
        icon={emptyState.icon}
        title={emptyState.title}
        description={emptyState.description}
        action={emptyState.action}
      />
    )
  }

  const hasFilterBar = !!search || !!segments || !!statusFilter || !!pillFilters || !!itemNoun

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
          {statusFilter && statusOptionsWithCounts && (
            <ShellStatusFilter
              label={statusFilter.label}
              options={statusOptionsWithCounts}
              value={statusFilter.value}
              onChange={statusFilter.onChange}
              activeCount={statusFilter.value.length > 0 ? statusFiltered.length : undefined}
              ariaLabel={statusFilter.ariaLabel}
            />
          )}
          {/* Modo Triagem (queue): filtros pill. Filtragem e do caller. */}
          {pillFilters && (
            <div
              className="flex flex-wrap items-center gap-2"
              role="tablist"
              aria-label={pillFilters.ariaLabel}
            >
              {pillFilters.options.map((opt) => {
                const active = pillFilters.value === opt.value
                return (
                  <button
                    key={opt.value}
                    type="button"
                    role="tab"
                    aria-selected={active}
                    onClick={() => pillFilters.onChange(opt.value)}
                    className={cx(
                      "inline-flex h-[26px] items-center rounded-full border px-2.5 text-xs font-medium tabular-nums transition-colors duration-100",
                      active
                        ? "border-blue-500 bg-blue-50 text-blue-700 dark:border-blue-500 dark:bg-blue-500/10 dark:text-blue-300"
                        : "border-gray-200 text-gray-500 hover:bg-gray-50 dark:border-gray-800 dark:text-gray-400 dark:hover:bg-gray-900",
                    )}
                  >
                    {opt.label}
                  </button>
                )
              })}
            </div>
          )}
          {counterLabel && (
            <span className={tableTokens.countLabel} aria-live="polite">
              {counterLabel}
            </span>
          )}
        </div>
      )}

      {pillFilters && !loading && data.length === 0 ? (
        // Modo Triagem: empty inline (toolbar de pills permanece acima).
        // O caller controla a mensagem via `emptyState` (sabe se e fila vazia
        // de verdade ou so o filtro atual sem itens).
        <div className="flex flex-col items-center gap-3 py-12 text-center">
          {emptyState?.icon && (
            <emptyState.icon
              className="size-7 text-gray-300 dark:text-gray-700"
              aria-hidden
            />
          )}
          <p className="text-[13px] text-gray-500 dark:text-gray-400">
            {emptyState?.title ?? "Nada aqui."}
          </p>
          {emptyState?.action}
        </div>
      ) : (
        <DataTable
          data={statusFiltered}
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
          renderEmpty={(hasSearchTerm) =>
            hasSearchTerm || (statusFilter?.value.length ?? 0) > 0 ? (
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
      )}

      {/* Proveniencia (CLAUDE.md §14.1) — dot pinned no rodape direito do Card.
          Mock (provenance undefined) = nada renderiza. */}
      {provenance && <OriginDot provenance={provenance} variant="pinned" />}
    </Card>
  )
}
