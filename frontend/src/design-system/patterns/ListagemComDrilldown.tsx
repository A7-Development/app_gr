// src/design-system/patterns/ListagemComDrilldown.tsx
//
// PATTERN — Listagem com Drill-down
// Copy, paste, adapt. Not a black-box component.
//
// Composes:
//   PageHeader → FilterBar → DataTable → DrillDownSheet (URL-synced)
//
// Use for: Cessões, Cedentes, Sacados, Cobrança, Reconciliação, Eventos
//
// URL state: ?selected=<id> opens the sheet on load.
// Pass `useQueryState` from nuqs, or use the fallback below.

"use client"

import * as React from "react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"
import {
  RiAddLine,
  RiDownloadLine,
  RiCheckLine,
} from "@remixicon/react"
import { cx } from "@/lib/utils"

import { DataTable, CurrencyCell, DateCell, IdCell, StatusCell } from "@/design-system/components/DataTable"
import {
  FilterBar, FilterSearch, FilterChip,
  RemovableChip, SavedViewsDropdown,
} from "@/design-system/components/FilterBar"
import { DrillDownSheet } from "@/design-system/components/DrillDownSheet"
import { ApprovalQueueBadge } from "@/design-system/components/ApprovalQueueBadge"
import { StatusPill } from "@/design-system/components/StatusPill"
import { Button } from "@/components/tremor/Button"
import type { StatusKey } from "@/design-system/tokens"
import { fmt } from "@/design-system/tokens/typography"

export interface CessaoRow {
  id:         string
  cedente:    string
  sacado:     string
  valor:      number
  vencimento: string
  status:     StatusKey
  prazo:      number
  inadimpl:   number
}

const SAMPLE_DATA: CessaoRow[] = [
  { id: "CCB-2024-001234", cedente: "Metalúrgica São Paulo Ltda", sacado: "Auto Peças Brasil", valor: 185400,  vencimento: "2026-06-15", status: "em-dia",       prazo: 45, inadimpl: 0   },
  { id: "CCB-2024-001235", cedente: "Distribuidora Norte S.A.",   sacado: "Mercado Central",   valor: 92300,   vencimento: "2026-05-30", status: "atrasado-30",  prazo: 30, inadimpl: 3.2 },
  { id: "CCB-2024-001236", cedente: "Tech Soluções ME",           sacado: "Gov. Estado RS",    valor: 450000,  vencimento: "2026-07-01", status: "em-dia",       prazo: 60, inadimpl: 0   },
  { id: "CCB-2024-001237", cedente: "Construtora ABC Ltda",       sacado: "Shopping Vila",     valor: 78900,   vencimento: "2026-04-20", status: "inadimplente", prazo: 0,  inadimpl: 100 },
  { id: "CCB-2024-001238", cedente: "Agro Grãos do Sul S.A.",     sacado: "Cooperativa RS",    valor: 1230000, vencimento: "2026-08-10", status: "em-dia",       prazo: 90, inadimpl: 0   },
  { id: "CCB-2024-001239", cedente: "Móveis Rápidos Ltda",        sacado: "Loja Decore",       valor: 34500,   vencimento: "2026-05-05", status: "atrasado-60",  prazo: 20, inadimpl: 5.1 },
  { id: "CCB-2024-001240", cedente: "Logística Express ME",       sacado: "E-commerce BR",     valor: 67800,   vencimento: "2026-09-20", status: "liquidado",    prazo: 0,  inadimpl: 0   },
  { id: "CCB-2024-001241", cedente: "Farmacêutica Sul Ltda",      sacado: "Rede Drogarias",    valor: 215000,  vencimento: "2026-06-30", status: "em-dia",       prazo: 55, inadimpl: 0.8 },
  { id: "CCB-2024-001242", cedente: "Padaria Industrial ME",      sacado: "Supermercado X",    valor: 29800,   vencimento: "2026-05-12", status: "recomprado",   prazo: 0,  inadimpl: 0   },
  { id: "CCB-2024-001243", cedente: "Confecções RJ Ltda",         sacado: "Lojas Moda+",       valor: 143200,  vencimento: "2026-07-15", status: "atrasado-30",  prazo: 35, inadimpl: 2.4 },
]

const col = createColumnHelper<CessaoRow>()

const COLUMNS: ColumnDef<CessaoRow, unknown>[] = [
  col.accessor("id", {
    header: "CCB / ID",
    size:   160,
    cell:   (info) => <IdCell value={info.getValue<string>()} />,
  }) as ColumnDef<CessaoRow, unknown>,
  col.accessor("cedente", {
    header: "Cedente",
    size:   200,
    cell:   (info) => (
      <span className="truncate text-sm text-gray-900 dark:text-gray-50">{info.getValue<string>()}</span>
    ),
  }) as ColumnDef<CessaoRow, unknown>,
  col.accessor("sacado", {
    header: "Sacado",
    size:   160,
    cell:   (info) => (
      <span className="truncate text-sm text-gray-500 dark:text-gray-400">{info.getValue<string>()}</span>
    ),
  }) as ColumnDef<CessaoRow, unknown>,
  col.accessor("valor", {
    header: "Valor",
    size:   130,
    cell:   (info) => (
      <div className="text-right">
        <CurrencyCell value={info.getValue<number>()} />
      </div>
    ),
  }) as ColumnDef<CessaoRow, unknown>,
  col.accessor("vencimento", {
    header: "Vencimento",
    size:   110,
    cell:   (info) => <DateCell value={info.getValue<string>()} format="absolute" />,
  }) as ColumnDef<CessaoRow, unknown>,
  col.accessor("prazo", {
    header: "Prazo",
    size:   80,
    cell:   (info) => {
      const v = info.getValue<number>()
      return (
        <span className={cx("tabular-nums text-sm", v <= 0 ? "text-gray-400 dark:text-gray-600" : "text-gray-900 dark:text-gray-50")}>
          {v > 0 ? `${v}d` : "—"}
        </span>
      )
    },
  }) as ColumnDef<CessaoRow, unknown>,
  col.accessor("status", {
    header: "Status",
    size:   140,
    cell:   (info) => <StatusCell value={info.getValue<StatusKey>()} />,
  }) as ColumnDef<CessaoRow, unknown>,
]

function useSelectedId() {
  const [selectedId, setSelectedId] = React.useState<string | null>(() => {
    if (typeof window === "undefined") return null
    return new URLSearchParams(window.location.search).get("selected")
  })

  const set = React.useCallback((id: string | null) => {
    setSelectedId(id)
    const url = new URL(window.location.href)
    if (id) url.searchParams.set("selected", id)
    else    url.searchParams.delete("selected")
    window.history.replaceState({}, "", url.toString())
  }, [])

  return [selectedId, set] as const
}

const STATUS_OPTIONS: { value: StatusKey | "all"; label: string }[] = [
  { value: "all",          label: "Todos"        },
  { value: "em-dia",       label: "Em dia"       },
  { value: "atrasado-30",  label: "Atrasado 30d" },
  { value: "atrasado-60",  label: "Atrasado 60d" },
  { value: "inadimplente", label: "Inadimplente" },
  { value: "liquidado",    label: "Liquidado"    },
  { value: "recomprado",   label: "Recomprado"   },
]

export function ListagemComDrilldown() {
  const [search, setSearch]             = React.useState("")
  const [statusFilter, setStatusFilter] = React.useState<StatusKey | "all">("all")
  const [selectedId, setSelectedId]     = useSelectedId()

  const filtered = React.useMemo(() => {
    return SAMPLE_DATA.filter((row) => {
      const q = search.toLowerCase()
      const matchSearch = !q
        || row.id.toLowerCase().includes(q)
        || row.cedente.toLowerCase().includes(q)
        || row.sacado.toLowerCase().includes(q)
      const matchStatus = statusFilter === "all" || row.status === statusFilter
      return matchSearch && matchStatus
    })
  }, [search, statusFilter])

  const selectedRow   = SAMPLE_DATA.find((r) => r.id === selectedId) ?? null
  const selectedIndex = filtered.findIndex((r) => r.id === selectedId)
  const pendingCount  = SAMPLE_DATA.filter((r) => r.status === "inadimplente" || r.status === "atrasado-60").length

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="shrink-0 border-b border-gray-200 dark:border-gray-800 px-6 py-4">
        <p className="mb-0.5 text-xs text-gray-500 dark:text-gray-400">Operação</p>
        <div className="flex items-center gap-2.5">
          <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-50">Cessões</h1>
          <ApprovalQueueBadge count={pendingCount} />
          <div className="ml-auto flex items-center gap-2">
            <Button variant="secondary">
              <RiDownloadLine className="size-3.5" aria-hidden="true" />
              Exportar
            </Button>
            <Button variant="primary">
              <RiAddLine className="size-3.5" aria-hidden="true" />
              Nova cessão
            </Button>
          </div>
        </div>
      </div>

      <FilterBar
        className="px-6"
        extraActions={
          <SavedViewsDropdown
            currentParams={{ status: statusFilter, q: search }}
            onApplyView={(view) => {
              setStatusFilter((view.params.status as StatusKey | "all") ?? "all")
              setSearch(view.params.q ?? "")
            }}
          />
        }
      >
        <FilterSearch
          placeholder="Buscar cessões..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onClear={() => setSearch("")}
        />

        <FilterChip
          label="Status"
          value={STATUS_OPTIONS.find((o) => o.value === statusFilter)?.label ?? "Todos"}
          active={statusFilter !== "all"}
        >
          <div className="py-1">
            {STATUS_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setStatusFilter(opt.value as StatusKey | "all")}
                className={cx(
                  "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                  statusFilter === opt.value
                    ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                    : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
                )}
              >
                <span className="flex-1 text-left">{opt.label}</span>
                {statusFilter === opt.value && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
              </button>
            ))}
          </div>
        </FilterChip>

        {statusFilter !== "all" && (
          <RemovableChip
            label="Status"
            value={STATUS_OPTIONS.find((o) => o.value === statusFilter)?.label ?? ""}
            onRemove={() => setStatusFilter("all")}
          />
        )}
      </FilterBar>

      <div className="relative flex-1 overflow-hidden">
        <DataTable
          data={filtered}
          columns={COLUMNS}
          density="default"
          selectable
          showExport
          showColumnManager
          showDensityToggle
          onRowClick={(row) => setSelectedId(row.id)}
          globalFilter={search}
          onExport={(format, rows) => {
            console.log("Export", format, rows.length, "rows")
          }}
          renderBulkActions={(rows, clear) => (
            <>
              <Button variant="ghost" onClick={clear} className="text-white/70 hover:text-white">
                Cancelar
              </Button>
              <Button variant="ghost" className="text-emerald-300 hover:text-emerald-100">
                Aprovar {rows.length}
              </Button>
              <Button variant="ghost" className="text-red-300 hover:text-red-100">
                Rejeitar
              </Button>
            </>
          )}
          renderEmpty={(hasFilters) => (
            <div className="flex flex-col items-center gap-3">
              <div className="size-12 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
                <RiDownloadLine className="size-5 text-gray-400 dark:text-gray-600" />
              </div>
              <div className="text-center">
                <p className="text-sm font-medium text-gray-900 dark:text-gray-50">
                  {hasFilters ? "Nenhuma cessão encontrada" : "Sem cessões cadastradas"}
                </p>
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  {hasFilters
                    ? "Tente ajustar os filtros ou limpar a busca"
                    : "Importe CCBs via API CIP/CERC ou cadastre manualmente"}
                </p>
              </div>
              {hasFilters && (
                <Button variant="secondary" onClick={() => { setSearch(""); setStatusFilter("all") }}>
                  Limpar filtros
                </Button>
              )}
            </div>
          )}
          renderFooter={(rows) => (
            <tr>
              <td colSpan={4} className="px-3 py-2 text-xs text-gray-500 dark:text-gray-400">
                {rows.length} cessão{rows.length !== 1 ? "ões" : ""}
              </td>
              <td className="px-3 py-2 text-right text-xs font-semibold tabular-nums text-gray-900 dark:text-gray-50">
                {fmt.currencyWhole.format(rows.reduce((s, r) => s + (r as CessaoRow).valor, 0))}
              </td>
              <td colSpan={3} className="px-3 py-2 text-xs text-gray-400 dark:text-gray-600">
                Total
              </td>
            </tr>
          )}
          className="h-full"
        />
      </div>

      {selectedRow && (
        <DrillDownSheet
          open={!!selectedId}
          onClose={() => setSelectedId(null)}
          size="md"
          title={`Cessão ${selectedRow.id}`}
        >
          <DrillDownSheet.Header
            breadcrumb={["Cessões", selectedRow.id]}
            statusSlot={<StatusPill status={selectedRow.status} />}
            onPrevious={selectedIndex > 0
              ? () => setSelectedId(filtered[selectedIndex - 1].id)
              : undefined}
            onNext={selectedIndex < filtered.length - 1
              ? () => setSelectedId(filtered[selectedIndex + 1].id)
              : undefined}
          />

          <DrillDownSheet.Hero
            id={selectedRow.id}
            title={selectedRow.cedente}
            value={selectedRow.valor}
          />

          <DrillDownSheet.Tabs
            tabs={[
              {
                value: "geral",
                label: "Visão geral",
                content: (
                  <div className="space-y-6">
                    <div>
                      <DrillDownSheet.SectionLabel>Dados da cessão</DrillDownSheet.SectionLabel>
                      <DrillDownSheet.PropertyList items={[
                        { label: "Cedente",    value: selectedRow.cedente },
                        { label: "Sacado",     value: selectedRow.sacado },
                        { label: "Valor",      value: selectedRow.valor, type: "currency" },
                        { label: "Vencimento", value: selectedRow.vencimento, type: "date" },
                        { label: "Prazo",      value: selectedRow.prazo, suffix: "dias", type: "number" },
                        { label: "Inadimpl.",  value: selectedRow.inadimpl, type: "percentage", editable: true },
                        { label: "Origem",     value: "CIP / CERC" },
                        { label: "Cedida em",  value: "02/04/2026" },
                      ]} />
                    </div>

                    <div>
                      <DrillDownSheet.SectionLabel>Objetos relacionados</DrillDownSheet.SectionLabel>
                      <DrillDownSheet.LinkedObjects items={[
                        { type: "Cedente", label: selectedRow.cedente, sub: "CNPJ 12.345.678/0001-99" },
                        { type: "Sacado",  label: selectedRow.sacado,  sub: "CNPJ 98.765.432/0001-11" },
                        { type: "Fundo",   label: "FIC FIDC Alpha",    sub: "CNPJ 11.222.333/0001-44", value: fmt.currencyCompact.format(124_500_000) },
                      ]} />
                    </div>

                    <div>
                      <DrillDownSheet.SectionLabel>Linha do tempo</DrillDownSheet.SectionLabel>
                      <DrillDownSheet.Timeline events={[
                        { type: "cedida",    date: "02/04/2026", actor: "Sistema CIP" },
                        { type: "lastreada", date: "03/04/2026", actor: "Custodiante" },
                        {
                          type:
                            selectedRow.status === "liquidado" ? "liquidada"
                            : selectedRow.status === "inadimplente" ? "atrasada"
                            : selectedRow.status === "recomprado" ? "recomprada"
                            : "a-vencer",
                          date:    selectedRow.status === "em-dia" ? "—" : "15/04/2026",
                          actor:   "Sistema CERC",
                          current: true,
                        },
                      ]} />
                    </div>
                  </div>
                ),
              },
              {
                value:   "historico",
                label:   "Histórico",
                content: <DrillDownSheet.Skeleton lines={6} />,
              },
              {
                value:   "documentos",
                label:   "Documentos",
                content: <DrillDownSheet.Skeleton lines={4} />,
              },
              {
                value:   "atividade",
                label:   "Atividade",
                content: <DrillDownSheet.Skeleton lines={5} />,
              },
            ]}
          />

          <DrillDownSheet.Footer>
            <Button variant="secondary">Exportar PDF</Button>
            <Button variant="ghost">Ver histórico</Button>
            <div className="flex-1" />
            {selectedRow.status !== "liquidado" && selectedRow.status !== "recomprado" && (
              <Button variant="primary">Registrar evento</Button>
            )}
          </DrillDownSheet.Footer>
        </DrillDownSheet>
      )}
    </div>
  )
}
