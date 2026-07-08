// Admin · Gestao · Tenants
//
// Lista tenants do sistema. Acessivel apenas a usuarios do tenant mantenedor
// (CLAUDE.md §19.2). Backend protege com require_system_maintainer (HTTP 403).
//
// Estado da URL:
//   ?action=new            -> drawer de criacao de tenant
//   ?selected=<uuid>       -> drawer de edicao do tenant selecionado
//
// Pos-criacao: dialog com o token + accept_url (mostrado UMA VEZ).

"use client"

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { toast } from "sonner"
import {
  RiAddLine,
  RiBuilding4Line,
  RiCheckLine,
  RiClipboardLine,
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
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/tremor/DropdownMenu"
import { Input } from "@/components/tremor/Input"
import {
  DataTableShell,
  DateCell,
  DrillDownSheet,
  PageHeader,
} from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import type {
  InvitationCreateResponse,
  TenantRead,
  TenantStatusId,
} from "@/lib/api-client"
import {
  useCreateTenant,
  useTenants,
  useUpdateTenant,
} from "@/lib/hooks/admin-tenants-users"
import { cx } from "@/lib/utils"

import { TenantCreateForm } from "./_components/TenantCreateForm"
import { TenantEditPanel } from "./_components/TenantEditPanel"

// ───────────────────────────────────────────────────────────────────────────
// Cells
// ───────────────────────────────────────────────────────────────────────────

const STATUS_TONES: Record<TenantStatusId, { bg: string; fg: string; dot: string; label: string }> = {
  trial:     { bg: "bg-amber-50 dark:bg-amber-500/10",  fg: "text-amber-700 dark:text-amber-300",  dot: "bg-amber-500", label: "Trial"     },
  active:    { bg: "bg-emerald-50 dark:bg-emerald-500/10", fg: "text-emerald-700 dark:text-emerald-300", dot: "bg-emerald-500", label: "Ativo"  },
  suspended: { bg: "bg-red-50 dark:bg-red-500/10",      fg: "text-red-700 dark:text-red-300",      dot: "bg-red-500",   label: "Suspenso"  },
  cancelled: { bg: "bg-gray-100 dark:bg-gray-800",      fg: "text-gray-600 dark:text-gray-400",    dot: "bg-gray-500",  label: "Cancelado" },
}

function StatusBadge({ status }: { status: TenantStatusId }) {
  const t = STATUS_TONES[status]
  return (
    <span className={cx(tableTokens.badgeWithDot, t.bg, t.fg)}>
      <span aria-hidden className={cx("size-1.5 rounded-full", t.dot)} />
      {t.label}
    </span>
  )
}

function ModuleCountCell({ subs }: { subs: TenantRead["subscriptions"] }) {
  const enabled = subs.filter((s) => s.enabled).length
  return (
    <span className={tableTokens.cellSecondary} title={subs.filter((s) => s.enabled).map((s) => s.module).join(", ")}>
      {enabled} {enabled === 1 ? "modulo" : "modulos"}
    </span>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Page
// ───────────────────────────────────────────────────────────────────────────

const col = createColumnHelper<TenantRead>()

export default function TenantsPage() {
  const router = useRouter()
  const sp = useSearchParams()
  const action = sp.get("action")
  const selectedId = sp.get("selected")

  const tenantsQuery = useTenants()
  const createMut = useCreateTenant()
  const updateMut = useUpdateTenant()

  const data = React.useMemo(() => tenantsQuery.data ?? [], [tenantsQuery.data])
  const selected = React.useMemo(
    () => (selectedId ? data.find((t) => t.id === selectedId) ?? null : null),
    [data, selectedId],
  )

  // Search e filtro de status multi-select (client-side).
  const [search, setSearch] = React.useState("")
  const [statusSel, setStatusSel] = React.useState<string[]>([])

  // Dialog pos-criacao com o accept_url (mostrado uma vez).
  const [newInvite, setNewInvite] = React.useState<InvitationCreateResponse | null>(null)
  const [copied, setCopied] = React.useState(false)

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

  const openNew = React.useCallback(() => setQuery({ action: "new", selected: null }), [setQuery])
  const openEdit = React.useCallback(
    (t: TenantRead) => setQuery({ action: null, selected: t.id }),
    [setQuery],
  )
  const closeSheet = React.useCallback(() => setQuery({ action: null, selected: null }), [setQuery])

  async function handleCreate(payload: Parameters<typeof createMut.mutateAsync>[0]) {
    try {
      const res = await createMut.mutateAsync(payload)
      toast.success(`Tenant '${payload.name}' criado. Owner convidado.`)
      closeSheet()
      setNewInvite(res)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao criar tenant.")
    }
  }

  async function copyLink() {
    if (!newInvite) return
    try {
      await navigator.clipboard.writeText(newInvite.accept_url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error("Nao foi possivel copiar. Selecione o link manualmente.")
    }
  }

  const columns = React.useMemo<ColumnDef<TenantRead, unknown>[]>(
    () => [
      col.accessor("name", {
        header: "Nome",
        size: 220,
        cell: (info) => (
          <span className={tableTokens.cellStrong}>{info.getValue()}</span>
        ),
      }) as ColumnDef<TenantRead, unknown>,
      col.accessor("slug", {
        header: "Slug",
        size: 150,
        cell: (info) => (
          <span className={cx(tableTokens.cellSecondary, "font-mono")}>
            {info.getValue()}
          </span>
        ),
      }) as ColumnDef<TenantRead, unknown>,
      col.accessor("status", {
        header: "Status",
        size: 110,
        cell: (info) => <StatusBadge status={info.getValue()} />,
      }) as ColumnDef<TenantRead, unknown>,
      col.accessor("subscriptions", {
        header: "Modulos",
        size: 110,
        cell: (info) => <ModuleCountCell subs={info.getValue()} />,
      }) as ColumnDef<TenantRead, unknown>,
      col.accessor("user_count", {
        header: "Usuarios",
        size: 90,
        cell: (info) => <span className={tableTokens.cellNumber}>{info.getValue()}</span>,
      }) as ColumnDef<TenantRead, unknown>,
      col.accessor("created_at", {
        header: "Criado em",
        size: 110,
        cell: (info) => <DateCell value={info.getValue()} />,
      }) as ColumnDef<TenantRead, unknown>,
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
                  aria-label={`Acoes de ${row.original.name}`}
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
                  disabled={row.original.is_system_maintainer || row.original.status === "suspended"}
                  onSelect={async () => {
                    try {
                      await updateMut.mutateAsync({
                        id: row.original.id,
                        payload: { status: "suspended" },
                      })
                      toast.success(`'${row.original.name}' suspenso.`)
                    } catch (err) {
                      toast.error(err instanceof Error ? err.message : "Falha ao suspender.")
                    }
                  }}
                >
                  Suspender
                </DropdownMenuItem>
                <DropdownMenuItem
                  disabled={row.original.status === "active"}
                  onSelect={async () => {
                    try {
                      await updateMut.mutateAsync({
                        id: row.original.id,
                        payload: { status: "active" },
                      })
                      toast.success(`'${row.original.name}' reativado.`)
                    } catch (err) {
                      toast.error(err instanceof Error ? err.message : "Falha ao reativar.")
                    }
                  }}
                >
                  Reativar
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        ),
      }) as ColumnDef<TenantRead, unknown>,
    ],
    [openEdit, updateMut],
  )

  return (
    <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
      <PageHeader
        title="Tenants"
        info="Organizacoes que usam o sistema. A7 (mantenedor) cria tenants, ativa modulos contratados e convida o primeiro Owner. Cada Owner gere os usuarios do proprio tenant."
        subtitle="Administracao · Gestao"
        actions={
          <Button variant="primary" onClick={openNew} disabled={tenantsQuery.isLoading}>
            <RiAddLine className="mr-1 size-4" aria-hidden />
            Novo tenant
          </Button>
        }
      />

      <DataTableShell<TenantRead>
        data={data}
        columns={columns}
        loading={tenantsQuery.isLoading}
        error={tenantsQuery.error}
        onRetry={() => tenantsQuery.refetch()}
        search={{
          value: search,
          onChange: setSearch,
          placeholder: "Buscar por slug ou nome...",
        }}
        statusFilter={{
          value: statusSel,
          onChange: setStatusSel,
          // Tones espelham STATUS_TONES do badge da coluna (mesma linguagem).
          options: [
            { value: "active",    label: "Ativo",     tone: "success", filter: (t) => t.status === "active" },
            { value: "trial",     label: "Trial",     tone: "warning", filter: (t) => t.status === "trial" },
            { value: "suspended", label: "Suspenso",  tone: "danger",  filter: (t) => t.status === "suspended" },
            { value: "cancelled", label: "Cancelado", tone: "neutral", filter: (t) => t.status === "cancelled" },
          ],
        }}
        itemNoun={{ singular: "tenant", plural: "tenants" }}
        onRowClick={openEdit}
        emptyState={{
          icon: RiBuilding4Line,
          title: "Nenhum tenant cadastrado",
          description: "Crie o primeiro tenant para liberar acesso a um cliente.",
          action: (
            <Button variant="primary" onClick={openNew}>
              <RiAddLine className="mr-1 size-4" aria-hidden />
              Criar tenant
            </Button>
          ),
        }}
      />

      {/* Drawer: novo tenant */}
      <DrillDownSheet
        open={action === "new"}
        onClose={closeSheet}
        title="Novo tenant"
        size="md"
      >
        <div className="p-6">
          <TenantCreateForm
            submitting={createMut.isPending}
            onSubmit={handleCreate}
            onCancel={closeSheet}
          />
        </div>
      </DrillDownSheet>

      {/* Drawer: editar tenant */}
      <DrillDownSheet
        open={selected !== null}
        onClose={closeSheet}
        title={selected ? selected.name : ""}
        size="md"
      >
        {selected && <TenantEditPanel tenant={selected} onClose={closeSheet} />}
      </DrillDownSheet>

      {/* Dialog pos-criacao: invitation link (mostrado uma vez) */}
      <Dialog
        open={newInvite !== null}
        onOpenChange={(open) => !open && setNewInvite(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Convite criado</DialogTitle>
            <DialogDescription>
              Copie o link abaixo e envie ao Owner do tenant. Ele e valido por
              7 dias e so pode ser usado uma vez. Por seguranca, este e o unico
              momento em que mostramos o link.
            </DialogDescription>
          </DialogHeader>

          {newInvite && (
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-1">
                <span className="text-xs text-gray-500">Para</span>
                <span className="text-sm text-gray-900 dark:text-gray-50">
                  {newInvite.invitation.email}
                </span>
              </div>

              <div className="flex flex-col gap-1.5">
                <span className="text-xs text-gray-500">Link de aceite</span>
                <div className="flex gap-2">
                  <Input
                    readOnly
                    value={newInvite.accept_url}
                    onClick={(e) => (e.target as HTMLInputElement).select()}
                    className="font-mono text-xs"
                  />
                  <Button variant="secondary" onClick={copyLink}>
                    {copied ? (
                      <>
                        <RiCheckLine className="mr-1 size-4" aria-hidden />
                        Copiado
                      </>
                    ) : (
                      <>
                        <RiClipboardLine className="mr-1 size-4" aria-hidden />
                        Copiar
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="primary" onClick={() => setNewInvite(null)}>
              Fechar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
