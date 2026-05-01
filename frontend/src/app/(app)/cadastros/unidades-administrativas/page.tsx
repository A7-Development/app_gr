"use client"

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { toast } from "sonner"
import {
  RiAddLine,
  RiBuildingLine,
  RiDeleteBinLine,
  RiMoreLine,
} from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import { Button } from "@/components/tremor/Button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/tremor/Dialog"
import { Divider } from "@/components/tremor/Divider"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/tremor/DropdownMenu"
import {
  DataTableShell,
  DateCell,
  DrillDownSheet,
  PageHeader,
} from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import type { TipoUA, UnidadeAdministrativa } from "@/lib/api-client"
import {
  useCreateUA,
  useDeleteUA,
  useUAs,
  useUpdateUA,
} from "@/lib/hooks/cadastros"
import { cx } from "@/lib/utils"

import { UACreateForm, UAEditForm, type UAFormValues } from "./_components/UAForm"

// ─── Cell helpers ────────────────────────────────────────────────────────────

const TIPO_LABELS: Record<TipoUA, string> = {
  fidc: "FIDC",
  consultoria: "Consultoria",
  securitizadora: "Securitizadora",
  factoring: "Factoring",
  gestora: "Gestora",
}

const TIPO_TONES: Record<TipoUA, { bg: string; fg: string; dot: string }> = {
  fidc: {
    bg: "bg-blue-50 dark:bg-blue-500/10",
    fg: "text-blue-700 dark:text-blue-300",
    dot: "bg-blue-500",
  },
  securitizadora: {
    bg: "bg-violet-50 dark:bg-violet-500/10",
    fg: "text-violet-700 dark:text-violet-300",
    dot: "bg-violet-500",
  },
  factoring: {
    bg: "bg-gray-100 dark:bg-gray-500/10",
    fg: "text-gray-700 dark:text-gray-300",
    dot: "bg-gray-500",
  },
  gestora: {
    bg: "bg-gray-100 dark:bg-gray-500/10",
    fg: "text-gray-700 dark:text-gray-300",
    dot: "bg-gray-500",
  },
  consultoria: {
    bg: "bg-gray-100 dark:bg-gray-500/10",
    fg: "text-gray-700 dark:text-gray-300",
    dot: "bg-gray-500",
  },
}

function TipoBadge({ tipo }: { tipo: TipoUA }) {
  const tone = TIPO_TONES[tipo]
  return (
    <span className={cx(tableTokens.badgeWithDot, tone.bg, tone.fg)}>
      <span aria-hidden className={cx("size-1.5 rounded-full", tone.dot)} />
      {TIPO_LABELS[tipo]}
    </span>
  )
}

function StatusBadge({ ativa }: { ativa: boolean }) {
  return (
    <span
      className={cx(
        tableTokens.badge,
        ativa
          ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
          : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400",
      )}
    >
      {ativa ? "Ativa" : "Inativa"}
    </span>
  )
}

function formatCnpj(cnpj: string | null): string {
  if (!cnpj) return ""
  if (cnpj.length !== 14) return cnpj
  return `${cnpj.slice(0, 2)}.${cnpj.slice(2, 5)}.${cnpj.slice(5, 8)}/${cnpj.slice(8, 12)}-${cnpj.slice(12)}`
}

// ─── Page ────────────────────────────────────────────────────────────────────

const col = createColumnHelper<UnidadeAdministrativa>()

export default function UnidadesAdministrativasPage() {
  const router = useRouter()
  const sp = useSearchParams()
  const action = sp.get("action")
  const selectedId = sp.get("selected")

  const uasQuery = useUAs()
  const createMut = useCreateUA()
  const deleteMut = useDeleteUA()

  const data = uasQuery.data ?? []
  const selected = React.useMemo(
    () => (selectedId ? data.find((u) => u.id === selectedId) ?? null : null),
    [data, selectedId],
  )
  const updateMut = useUpdateUA(selected?.id ?? "")

  const [pendingDelete, setPendingDelete] = React.useState<UnidadeAdministrativa | null>(null)
  const [search, setSearch] = React.useState("")
  const [segment, setSegment] = React.useState("todas")

  // ── Navigation ─────────────────────────────────────────────────────────
  const setQuery = React.useCallback(
    (next: { action?: string | null; selected?: string | null }) => {
      const params = new URLSearchParams(sp.toString())
      if (next.action !== undefined) {
        if (next.action) params.set("action", next.action)
        else params.delete("action")
      }
      if (next.selected !== undefined) {
        if (next.selected) params.set("selected", next.selected)
        else params.delete("selected")
      }
      const qs = params.toString()
      router.push(qs ? `?${qs}` : "?")
    },
    [router, sp],
  )

  const openNew = React.useCallback(
    () => setQuery({ action: "new", selected: null }),
    [setQuery],
  )
  const openEdit = React.useCallback(
    (ua: UnidadeAdministrativa) => setQuery({ action: null, selected: ua.id }),
    [setQuery],
  )
  const closeSheet = React.useCallback(
    () => setQuery({ action: null, selected: null }),
    [setQuery],
  )

  // ── Handlers ───────────────────────────────────────────────────────────
  const handleCreate = React.useCallback(
    async (values: UAFormValues) => {
      try {
        await createMut.mutateAsync({
          nome: values.nome.trim(),
          cnpj: values.cnpj?.trim() || null,
          tipo: values.tipo,
          ativa: values.ativa,
        })
        toast.success(`UA "${values.nome}" cadastrada.`)
        closeSheet()
      } catch (err) {
        toast.error(
          err instanceof Error ? err.message : "Falha ao cadastrar UA.",
        )
      }
    },
    [createMut, closeSheet],
  )

  const handleEdit = React.useCallback(
    async (values: UAFormValues) => {
      if (!selected) return
      try {
        await updateMut.mutateAsync({
          nome: values.nome.trim(),
          cnpj: values.cnpj?.trim() || null,
          tipo: values.tipo,
          ativa: values.ativa,
        })
        toast.success(`UA "${values.nome}" atualizada.`)
        closeSheet()
      } catch (err) {
        toast.error(
          err instanceof Error ? err.message : "Falha ao atualizar UA.",
        )
      }
    },
    [updateMut, selected, closeSheet],
  )

  const handleDelete = React.useCallback(async () => {
    if (!pendingDelete) return
    try {
      await deleteMut.mutateAsync(pendingDelete.id)
      toast.success(`UA "${pendingDelete.nome}" excluida.`)
      setPendingDelete(null)
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Falha ao excluir UA.",
      )
    }
  }, [deleteMut, pendingDelete])

  // ── Columns ────────────────────────────────────────────────────────────
  const columns = React.useMemo<ColumnDef<UnidadeAdministrativa, unknown>[]>(
    () => [
      col.accessor("nome", {
        header: "Nome",
        size: 240,
        cell: (info) => (
          <span className={tableTokens.cellText}>{info.getValue()}</span>
        ),
      }) as ColumnDef<UnidadeAdministrativa, unknown>,
      col.accessor("tipo", {
        header: "Tipo",
        size: 150,
        cell: (info) => <TipoBadge tipo={info.getValue()} />,
      }) as ColumnDef<UnidadeAdministrativa, unknown>,
      col.accessor("cnpj", {
        header: "CNPJ",
        size: 180,
        cell: (info) => {
          const v = info.getValue()
          if (!v) return <span className={tableTokens.cellMuted}>—</span>
          return (
            <span className={tableTokens.cellTextMono}>
              {formatCnpj(v)}
            </span>
          )
        },
      }) as ColumnDef<UnidadeAdministrativa, unknown>,
      col.accessor("ativa", {
        header: "Status",
        size: 100,
        cell: (info) => <StatusBadge ativa={info.getValue()} />,
      }) as ColumnDef<UnidadeAdministrativa, unknown>,
      col.accessor("created_at", {
        header: "Criada em",
        size: 110,
        cell: (info) => <DateCell value={info.getValue()} />,
      }) as ColumnDef<UnidadeAdministrativa, unknown>,
      col.display({
        id: "actions",
        header: "",
        size: 56,
        cell: ({ row }) => (
          <div className="flex justify-end">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  className="size-7 p-0"
                  aria-label={`Acoes de ${row.original.nome}`}
                  onClick={(e) => e.stopPropagation()}
                >
                  <RiMoreLine className="size-4" aria-hidden />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" sideOffset={4}>
                <DropdownMenuItem onSelect={() => openEdit(row.original)}>
                  Editar
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onSelect={() => setPendingDelete(row.original)}
                  className="text-red-600 focus:text-red-700 dark:text-red-400 dark:focus:text-red-300"
                >
                  <RiDeleteBinLine className="mr-2 size-4" aria-hidden />
                  Excluir
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        ),
      }) as ColumnDef<UnidadeAdministrativa, unknown>,
    ],
    [openEdit],
  )

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
      <PageHeader
        title="Unidades administrativas"
        info="UAs sao as entidades operacionais do tenant: FIDCs, securitizadoras, factorings, gestoras, consultorias. Cada UA pode ter ou nao integracao com fontes externas."
        subtitle="Cadastros"
        actions={
          <Button
            variant="primary"
            onClick={openNew}
            disabled={uasQuery.isLoading}
          >
            <RiAddLine className="mr-1 size-4" aria-hidden />
            Nova UA
          </Button>
        }
      />

      <DataTableShell<UnidadeAdministrativa>
        data={data}
        columns={columns}
        loading={uasQuery.isLoading}
        error={uasQuery.error}
        onRetry={() => uasQuery.refetch()}
        search={{
          value: search,
          onChange: setSearch,
          placeholder: "Buscar por nome, CNPJ ou tipo...",
        }}
        segments={{
          value: segment,
          onChange: setSegment,
          options: [
            { value: "todas", label: "Todas", filter: () => true },
            { value: "ativas", label: "Ativas", filter: (u) => u.ativa },
            { value: "inativas", label: "Inativas", filter: (u) => !u.ativa },
            { value: "fidc", label: "FIDC", filter: (u) => u.tipo === "fidc" },
            { value: "securitizadora", label: "Securitizadora", filter: (u) => u.tipo === "securitizadora" },
          ],
        }}
        itemNoun={{ singular: "unidade", plural: "unidades" }}
        onRowClick={openEdit}
        emptyState={{
          icon: RiBuildingLine,
          title: "Nenhuma UA cadastrada",
          description: "Cadastre a primeira unidade administrativa do tenant para comecar a usar integracoes e BI.",
          action: (
            <Button variant="primary" onClick={openNew}>
              <RiAddLine className="mr-1 size-4" aria-hidden />
              Cadastrar primeira UA
            </Button>
          ),
        }}
      />

      {/* Drawer: Nova UA */}
      <DrillDownSheet
        open={action === "new"}
        onClose={closeSheet}
        title="Nova unidade administrativa"
        size="md"
      >
        <div className="p-6">
          <UACreateForm
            submitting={createMut.isPending}
            onSubmit={handleCreate}
            onCancel={closeSheet}
          />
        </div>
      </DrillDownSheet>

      {/* Drawer: Editar UA */}
      <DrillDownSheet
        open={selected !== null}
        onClose={closeSheet}
        title={selected ? `Editar · ${selected.nome}` : ""}
        size="md"
      >
        {selected && (
          <div className="p-6">
            <UAEditForm
              initial={selected}
              submitting={updateMut.isPending}
              onSubmit={handleEdit}
              onCancel={closeSheet}
            />
          </div>
        )}
      </DrillDownSheet>

      {/* Confirmacao destrutiva */}
      <Dialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Excluir unidade administrativa</DialogTitle>
            <DialogDescription>
              Esta acao remove permanentemente a UA{" "}
              <span className="font-semibold text-gray-900 dark:text-gray-50">
                {pendingDelete?.nome}
              </span>
              . Integracoes associadas perderao a referencia.
            </DialogDescription>
          </DialogHeader>

          <Divider />

          <DialogFooter>
            <Button
              variant="secondary"
              onClick={() => setPendingDelete(null)}
              disabled={deleteMut.isPending}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteMut.isPending}
            >
              <RiDeleteBinLine className="mr-1.5 size-4" aria-hidden />
              Excluir UA
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
