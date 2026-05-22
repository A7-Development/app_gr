// src/app/(app)/admin/ia/tools/page.tsx
//
// Admin · IA · Tools (read-only, F2.c.4, CLAUDE.md §19.0).
//
// Lista as tools registradas via `@register_tool` em
// `app/agentic/tools/<modulo>/*.py`. Read-only — atualizar uma tool
// exige editar codigo Python + deploy.
//
// Pattern: ListagemCrudInline canonico via DataTableShell, sem CRUD
// (sem botao "+ Nova" no header, sem DropdownMenu de acoes).

"use client"

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { RiToolsLine } from "@remixicon/react"
import { type ColumnDef } from "@tanstack/react-table"

import { Button } from "@/components/tremor/Button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/tremor/Dialog"
import {
  DataTableShell,
  PageHeader,
} from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import type { AIToolInfo } from "@/lib/api-client"
import { useTools } from "@/lib/hooks/admin-ai"
import { cx } from "@/lib/utils"

// ───────────────────────────────────────────────────────────────────────────
// Badges
// ───────────────────────────────────────────────────────────────────────────

const MODULE_TONES: Record<string, { bg: string; fg: string }> = {
  bi: { bg: "bg-gray-100 dark:bg-gray-800", fg: "text-gray-700 dark:text-gray-300" },
  cadastros: { bg: "bg-blue-50 dark:bg-blue-500/10", fg: "text-blue-700 dark:text-blue-300" },
  operacoes: { bg: "bg-emerald-50 dark:bg-emerald-500/10", fg: "text-emerald-700 dark:text-emerald-300" },
  credito: { bg: "bg-indigo-50 dark:bg-indigo-500/10", fg: "text-indigo-700 dark:text-indigo-300" },
  controladoria: { bg: "bg-teal-50 dark:bg-teal-500/10", fg: "text-teal-700 dark:text-teal-300" },
  risco: { bg: "bg-amber-50 dark:bg-amber-500/10", fg: "text-amber-700 dark:text-amber-300" },
  integracoes: { bg: "bg-red-50 dark:bg-red-500/10", fg: "text-red-700 dark:text-red-300" },
  laboratorio: { bg: "bg-violet-50 dark:bg-violet-500/10", fg: "text-violet-700 dark:text-violet-300" },
  admin: { bg: "bg-slate-50 dark:bg-slate-500/10", fg: "text-slate-700 dark:text-slate-300" },
}

function ModuleBadge({ module }: { module: string }) {
  const tone = MODULE_TONES[module] ?? {
    bg: "bg-gray-100 dark:bg-gray-800",
    fg: "text-gray-700 dark:text-gray-300",
  }
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-sm px-1.5 py-0.5 text-[11px] font-medium",
        tone.bg,
        tone.fg,
      )}
    >
      {module}
    </span>
  )
}

function PermissionBadge({ perm }: { perm: string }) {
  const tone =
    perm === "admin"
      ? { bg: "bg-red-50 dark:bg-red-500/10", fg: "text-red-700 dark:text-red-300" }
      : perm === "write"
        ? { bg: "bg-amber-50 dark:bg-amber-500/10", fg: "text-amber-700 dark:text-amber-300" }
        : { bg: "bg-gray-100 dark:bg-gray-800", fg: "text-gray-700 dark:text-gray-300" }
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-sm px-1.5 py-0.5 text-[11px] font-medium",
        tone.bg,
        tone.fg,
      )}
    >
      {perm}
    </span>
  )
}

function CostBadge({ cost }: { cost: string }) {
  const tone =
    cost === "expensive"
      ? { bg: "bg-red-50 dark:bg-red-500/10", fg: "text-red-700 dark:text-red-300" }
      : cost === "medium"
        ? { bg: "bg-amber-50 dark:bg-amber-500/10", fg: "text-amber-700 dark:text-amber-300" }
        : { bg: "bg-emerald-50 dark:bg-emerald-500/10", fg: "text-emerald-700 dark:text-emerald-300" }
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-sm px-1.5 py-0.5 text-[11px] font-medium",
        tone.bg,
        tone.fg,
      )}
    >
      {cost}
    </span>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Page
// ───────────────────────────────────────────────────────────────────────────

export default function ToolsAdminPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const selectedName = searchParams.get("selected")

  const [segment, setSegment] = React.useState<string>("todas")
  const [search, setSearch] = React.useState("")

  const toolsQuery = useTools()
  const toolsData = React.useMemo(
    () => toolsQuery.data ?? [],
    [toolsQuery.data],
  )

  const selected: AIToolInfo | null = React.useMemo(() => {
    if (!selectedName) return null
    return toolsData.find((t) => t.name === selectedName) ?? null
  }, [selectedName, toolsData])

  // Modulos disponiveis pra segments (dinamicos)
  const modulesAvailable = React.useMemo(() => {
    const set = new Set<string>()
    for (const t of toolsData) set.add(t.module)
    return Array.from(set).sort()
  }, [toolsData])

  // ── URL helpers ───────────────────────────────────────────────────────
  const closeDetail = React.useCallback(() => {
    const params = new URLSearchParams(searchParams.toString())
    params.delete("selected")
    router.replace(
      params.toString() ? `?${params.toString()}` : window.location.pathname,
      { scroll: false },
    )
  }, [router, searchParams])

  const openDetail = React.useCallback(
    (name: string) => {
      const params = new URLSearchParams(searchParams.toString())
      params.set("selected", name)
      router.replace(`?${params.toString()}`, { scroll: false })
    },
    [router, searchParams],
  )

  // ── Columns ───────────────────────────────────────────────────────────
  const columns = React.useMemo<ColumnDef<AIToolInfo>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Nome",
        cell: ({ row }) => (
          <span className={cx(tableTokens.cellStrong, "font-mono")}>
            {row.original.name}
          </span>
        ),
      },
      {
        accessorKey: "module",
        header: "Modulo",
        cell: ({ row }) => <ModuleBadge module={row.original.module} />,
      },
      {
        accessorKey: "description",
        header: "Descricao",
        cell: ({ row }) => (
          <span
            className={cx(tableTokens.cellSecondary, "line-clamp-2")}
            title={row.original.description}
          >
            {row.original.description}
          </span>
        ),
      },
      {
        accessorKey: "min_permission",
        header: "Permissao",
        cell: ({ row }) => (
          <PermissionBadge perm={row.original.min_permission} />
        ),
      },
      {
        accessorKey: "cost_hint",
        header: "Custo",
        cell: ({ row }) => <CostBadge cost={row.original.cost_hint} />,
      },
    ],
    [],
  )

  // ── Segments dinamicos por modulo ────────────────────────────────────
  const segmentOptions = React.useMemo(
    () => [
      { value: "todas", label: "Todas", filter: () => true },
      ...modulesAvailable.map((m) => ({
        value: m,
        label: m,
        filter: (t: AIToolInfo) => t.module === m,
      })),
    ],
    [modulesAvailable],
  )

  // ── Render ────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
      <PageHeader
        title="Tools de IA"
        subtitle="Inteligencia Artificial · Administracao"
        info="Funcoes atomicas que agentes podem invocar (CLAUDE.md §19.0). Tools sao definidas em codigo via @register_tool — read-only aqui. Para mudar, edite o arquivo Python e faca deploy."
      />

      <DataTableShell<AIToolInfo>
        data={toolsData}
        columns={columns}
        loading={toolsQuery.isLoading}
        error={toolsQuery.error}
        onRetry={() => toolsQuery.refetch()}
        search={{
          value: search,
          onChange: setSearch,
          placeholder: "Buscar por nome ou descricao...",
        }}
        segments={{
          value: segment,
          onChange: setSegment,
          options: segmentOptions,
        }}
        itemNoun={{ singular: "tool", plural: "tools" }}
        onRowClick={(row) => openDetail(row.name)}
        emptyState={{
          icon: RiToolsLine,
          title: "Nenhuma tool registrada",
          description:
            "Tools sao definidas em codigo via @register_tool. Verifique imports em app/agentic/tools/.",
        }}
      />

      {/* Dialog de detalhe — mostra input_schema completo */}
      <Dialog
        open={selected !== null}
        onOpenChange={(open) => !open && closeDetail()}
      >
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle className="font-mono">{selected?.name}</DialogTitle>
            <DialogDescription>{selected?.description}</DialogDescription>
          </DialogHeader>
          {selected && (
            <div className="flex flex-col gap-4">
              <div className="flex flex-wrap gap-2">
                <ModuleBadge module={selected.module} />
                <PermissionBadge perm={selected.min_permission} />
                <CostBadge cost={selected.cost_hint} />
              </div>

              <section>
                <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  Input schema (JSON Schema)
                </div>
                <pre
                  className={cx(
                    "max-h-[400px] overflow-auto rounded-md border p-3 font-mono text-[12px] leading-relaxed",
                    "border-gray-200 bg-gray-50 text-gray-900",
                    "dark:border-gray-800 dark:bg-gray-900 dark:text-gray-100",
                  )}
                >
                  {JSON.stringify(selected.input_schema, null, 2)}
                </pre>
              </section>

              <div className="text-[12px] text-gray-500 dark:text-gray-400">
                Para editar:{" "}
                <code>{`app/agentic/tools/${selected.module}/*.py`}</code>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="secondary" onClick={closeDetail}>
              Fechar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
