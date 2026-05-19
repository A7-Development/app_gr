// Admin · Gestao · Usuarios
//
// Gestao dos users do tenant ativo + convites pendentes. Acessivel apenas a
// Owner do tenant (backend valida em /admin/users/* com require_module(ADMIN,
// ADMIN) + tenant_role=owner). Sidebar mostra a entrada pra todos no modulo
// admin; UI nao acessa quando o backend devolve 403 (mostra error state).
//
// URL state:
//   ?tab=usuarios | convites    (default: usuarios)
//   ?action=new                 -> drawer de convidar usuario
//   ?selected=<uuid>            -> drawer de editar user
//

"use client"

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { toast } from "sonner"
import {
  RiAddLine,
  RiCheckLine,
  RiClipboardLine,
  RiCloseLine,
  RiDeleteBinLine,
  RiMoreLine,
  RiUserLine,
} from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"
import { format, parseISO, formatDistanceToNow } from "date-fns"
import { ptBR } from "date-fns/locale"

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
import { TabNavigation, TabNavigationLink } from "@/components/tremor/TabNavigation"
import {
  DataTableShell,
  DrillDownSheet,
  PageHeader,
} from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import type {
  InvitationCreateResponse,
  InvitationRead,
  TenantRoleId,
  UserRead,
} from "@/lib/api-client"
import {
  useCancelInvitation,
  useCreateInvitation,
  useInvitations,
  useUsers,
} from "@/lib/hooks/admin-tenants-users"
import { cx } from "@/lib/utils"

import { UserEditPanel } from "./_components/UserEditPanel"
import { UserInviteForm } from "./_components/UserInviteForm"

// ───────────────────────────────────────────────────────────────────────────
// Badges
// ───────────────────────────────────────────────────────────────────────────

const ROLE_TONES: Record<TenantRoleId, { bg: string; fg: string; label: string }> = {
  owner:  { bg: "bg-blue-50 dark:bg-blue-500/10",       fg: "text-blue-700 dark:text-blue-300",       label: "Owner"  },
  member: { bg: "bg-emerald-50 dark:bg-emerald-500/10", fg: "text-emerald-700 dark:text-emerald-300", label: "Member" },
  viewer: { bg: "bg-gray-100 dark:bg-gray-800",         fg: "text-gray-700 dark:text-gray-300",       label: "Viewer" },
}

function RoleBadge({ role }: { role: TenantRoleId }) {
  const t = ROLE_TONES[role]
  return <span className={cx(tableTokens.badge, t.bg, t.fg)}>{t.label}</span>
}

function ActiveBadge({ ativo }: { ativo: boolean }) {
  return (
    <span
      className={cx(
        tableTokens.badge,
        ativo
          ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
          : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400",
      )}
    >
      {ativo ? "Ativo" : "Inativo"}
    </span>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Page
// ───────────────────────────────────────────────────────────────────────────

const userCol = createColumnHelper<UserRead>()
const inviteCol = createColumnHelper<InvitationRead>()

type Tab = "usuarios" | "convites"

export default function UsersPage() {
  const router = useRouter()
  const sp = useSearchParams()
  const tab: Tab = (sp.get("tab") as Tab) ?? "usuarios"
  const action = sp.get("action")
  const selectedId = sp.get("selected")

  const usersQuery = useUsers()
  const invitesQuery = useInvitations()
  const createInviteMut = useCreateInvitation()
  const cancelInviteMut = useCancelInvitation()

  const users = React.useMemo(() => usersQuery.data ?? [], [usersQuery.data])
  const invites = React.useMemo(() => invitesQuery.data ?? [], [invitesQuery.data])
  const selectedUser = React.useMemo(
    () => (selectedId ? users.find((u) => u.id === selectedId) ?? null : null),
    [users, selectedId],
  )

  const [search, setSearch] = React.useState("")
  const [segment, setSegment] = React.useState<"todos" | "ativos" | "inativos" | "owner" | "member" | "viewer">("todos")

  const [newInvite, setNewInvite] = React.useState<InvitationCreateResponse | null>(null)
  const [copied, setCopied] = React.useState(false)
  const [pendingCancel, setPendingCancel] = React.useState<InvitationRead | null>(null)

  const setQuery = React.useCallback(
    (next: { tab?: Tab; action?: string | null; selected?: string | null }) => {
      const params = new URLSearchParams(sp.toString())
      if (next.tab !== undefined) {
        if (next.tab && next.tab !== "usuarios") params.set("tab", next.tab)
        else params.delete("tab")
      }
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
    (u: UserRead) => setQuery({ action: null, selected: u.id }),
    [setQuery],
  )
  const closeSheet = React.useCallback(() => setQuery({ action: null, selected: null }), [setQuery])

  async function handleInvite(payload: Parameters<typeof createInviteMut.mutateAsync>[0]) {
    try {
      const res = await createInviteMut.mutateAsync(payload)
      toast.success(`Convite enviado para ${payload.email}.`)
      closeSheet()
      setNewInvite(res)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao enviar convite.")
    }
  }

  async function handleCancelInvite() {
    if (!pendingCancel) return
    try {
      await cancelInviteMut.mutateAsync(pendingCancel.id)
      toast.success(`Convite para ${pendingCancel.email} cancelado.`)
      setPendingCancel(null)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao cancelar convite.")
    }
  }

  async function copyLink() {
    if (!newInvite) return
    try {
      await navigator.clipboard.writeText(newInvite.accept_url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error("Nao foi possivel copiar.")
    }
  }

  const userColumns = React.useMemo<ColumnDef<UserRead, unknown>[]>(
    () => [
      userCol.accessor("name", {
        header: "Nome",
        size: 200,
        cell: (info) => (
          <span className={tableTokens.cellStrong}>{info.getValue()}</span>
        ),
      }) as ColumnDef<UserRead, unknown>,
      userCol.accessor("email", {
        header: "Email",
        size: 240,
        cell: (info) => (
          <span className={tableTokens.cellSecondary}>{info.getValue()}</span>
        ),
      }) as ColumnDef<UserRead, unknown>,
      userCol.accessor("tenant_role", {
        header: "Role",
        size: 100,
        cell: (info) => <RoleBadge role={info.getValue()} />,
      }) as ColumnDef<UserRead, unknown>,
      userCol.accessor("ativo", {
        header: "Status",
        size: 90,
        cell: (info) => <ActiveBadge ativo={info.getValue()} />,
      }) as ColumnDef<UserRead, unknown>,
      userCol.accessor("last_login_at", {
        header: "Ultimo login",
        size: 140,
        cell: (info) => {
          const v = info.getValue()
          if (!v) return <span className={tableTokens.cellMuted}>nunca</span>
          return (
            <span className={tableTokens.cellSecondary} title={v}>
              {formatDistanceToNow(parseISO(v), { addSuffix: true, locale: ptBR })}
            </span>
          )
        },
      }) as ColumnDef<UserRead, unknown>,
      userCol.display({
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
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        ),
      }) as ColumnDef<UserRead, unknown>,
    ],
    [openEdit],
  )

  const inviteColumns = React.useMemo<ColumnDef<InvitationRead, unknown>[]>(
    () => [
      inviteCol.accessor("email", {
        header: "Email",
        size: 280,
        cell: (info) => <span className={tableTokens.cellStrong}>{info.getValue()}</span>,
      }) as ColumnDef<InvitationRead, unknown>,
      inviteCol.accessor("role", {
        header: "Role",
        size: 100,
        cell: (info) => <RoleBadge role={info.getValue()} />,
      }) as ColumnDef<InvitationRead, unknown>,
      inviteCol.display({
        id: "status",
        header: "Status",
        size: 110,
        cell: ({ row }) => {
          const r = row.original
          if (r.accepted_at) {
            return <span className={cx(tableTokens.badge, "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300")}>Aceito</span>
          }
          if (r.revoked_at) {
            return <span className={cx(tableTokens.badge, "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400")}>Cancelado</span>
          }
          const expired = new Date(r.expires_at) <= new Date()
          if (expired) {
            return <span className={cx(tableTokens.badge, "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300")}>Expirado</span>
          }
          return <span className={cx(tableTokens.badge, "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300")}>Pendente</span>
        },
      }) as ColumnDef<InvitationRead, unknown>,
      inviteCol.accessor("expires_at", {
        header: "Expira em",
        size: 150,
        cell: (info) => (
          <span className={tableTokens.cellSecondary}>
            {format(parseISO(info.getValue()), "dd/MM/yyyy HH:mm", { locale: ptBR })}
          </span>
        ),
      }) as ColumnDef<InvitationRead, unknown>,
      inviteCol.accessor("created_at", {
        header: "Criado em",
        size: 130,
        cell: (info) => (
          <span className={tableTokens.cellSecondary}>
            {format(parseISO(info.getValue()), "dd/MM/yyyy", { locale: ptBR })}
          </span>
        ),
      }) as ColumnDef<InvitationRead, unknown>,
      inviteCol.display({
        id: "actions",
        header: "",
        size: 56,
        cell: ({ row }) => {
          const r = row.original
          const isOpen = !r.accepted_at && !r.revoked_at && new Date(r.expires_at) > new Date()
          if (!isOpen) return null
          return (
            <div className="flex justify-end">
              <Button
                variant="ghost"
                className="size-7 p-0"
                aria-label="Cancelar convite"
                onClick={(e) => {
                  e.stopPropagation()
                  setPendingCancel(r)
                }}
              >
                <RiCloseLine className="size-4 text-gray-500" aria-hidden />
              </Button>
            </div>
          )
        },
      }) as ColumnDef<InvitationRead, unknown>,
    ],
    [],
  )

  return (
    <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
      <PageHeader
        title="Usuarios"
        info="Time do seu tenant. Apenas Owners veem essa pagina. Convites sao enviados por email e expiram em 7 dias."
        subtitle="Administracao · Gestao"
        actions={
          <Button variant="primary" onClick={openNew}>
            <RiAddLine className="mr-1 size-4" aria-hidden />
            Convidar usuario
          </Button>
        }
      />

      <TabNavigation>
        <TabNavigationLink
          asChild
          active={tab === "usuarios"}
        >
          <button type="button" onClick={() => setQuery({ tab: "usuarios" })}>
            Usuarios ({users.length})
          </button>
        </TabNavigationLink>
        <TabNavigationLink
          asChild
          active={tab === "convites"}
        >
          <button type="button" onClick={() => setQuery({ tab: "convites" })}>
            Convites ({invites.filter((i) => !i.accepted_at && !i.revoked_at && new Date(i.expires_at) > new Date()).length} abertos)
          </button>
        </TabNavigationLink>
      </TabNavigation>

      {tab === "usuarios" ? (
        <DataTableShell<UserRead>
          data={users}
          columns={userColumns}
          loading={usersQuery.isLoading}
          error={usersQuery.error}
          onRetry={() => usersQuery.refetch()}
          search={{
            value: search,
            onChange: setSearch,
            placeholder: "Buscar por nome ou email...",
          }}
          segments={{
            value: segment,
            onChange: (v) => setSegment(v as typeof segment),
            options: [
              { value: "todos",    label: "Todos",    filter: () => true },
              { value: "ativos",   label: "Ativos",   filter: (u) => u.ativo },
              { value: "inativos", label: "Inativos", filter: (u) => !u.ativo },
              { value: "owner",    label: "Owner",    filter: (u) => u.tenant_role === "owner" },
              { value: "member",   label: "Member",   filter: (u) => u.tenant_role === "member" },
              { value: "viewer",   label: "Viewer",   filter: (u) => u.tenant_role === "viewer" },
            ],
          }}
          itemNoun={{ singular: "usuario", plural: "usuarios" }}
          onRowClick={openEdit}
          emptyState={{
            icon: RiUserLine,
            title: "Nenhum usuario cadastrado",
            description: "Convide o primeiro membro do time pra colaborar.",
            action: (
              <Button variant="primary" onClick={openNew}>
                <RiAddLine className="mr-1 size-4" aria-hidden />
                Convidar usuario
              </Button>
            ),
          }}
        />
      ) : (
        <DataTableShell<InvitationRead>
          data={invites}
          columns={inviteColumns}
          loading={invitesQuery.isLoading}
          error={invitesQuery.error}
          onRetry={() => invitesQuery.refetch()}
          itemNoun={{ singular: "convite", plural: "convites" }}
          emptyState={{
            icon: RiUserLine,
            title: "Nenhum convite",
            description: "Convites recentes aparecem aqui.",
          }}
        />
      )}

      <DrillDownSheet
        open={action === "new"}
        onClose={closeSheet}
        title="Convidar usuario"
        size="md"
      >
        <div className="p-6">
          <UserInviteForm
            submitting={createInviteMut.isPending}
            onSubmit={handleInvite}
            onCancel={closeSheet}
          />
        </div>
      </DrillDownSheet>

      <DrillDownSheet
        open={selectedUser !== null}
        onClose={closeSheet}
        title={selectedUser ? selectedUser.name : ""}
        size="md"
      >
        {selectedUser && <UserEditPanel user={selectedUser} onClose={closeSheet} />}
      </DrillDownSheet>

      {/* Dialog pos-convite */}
      <Dialog open={newInvite !== null} onOpenChange={(o) => !o && setNewInvite(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Convite enviado</DialogTitle>
            <DialogDescription>
              Encaminhe o link abaixo para {newInvite?.invitation.email}. Ele e
              valido por 7 dias e expira ao ser usado.
            </DialogDescription>
          </DialogHeader>

          {newInvite && (
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
          )}

          <DialogFooter>
            <Button variant="primary" onClick={() => setNewInvite(null)}>Fechar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Confirmacao de cancelar convite */}
      <Dialog open={pendingCancel !== null} onOpenChange={(o) => !o && setPendingCancel(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cancelar convite</DialogTitle>
            <DialogDescription>
              O link enviado para{" "}
              <span className="font-mono text-gray-900 dark:text-gray-50">
                {pendingCancel?.email}
              </span>{" "}
              vai deixar de funcionar imediatamente. Se quiser reativar, basta
              enviar um novo convite.
            </DialogDescription>
          </DialogHeader>

          <DialogFooter>
            <Button
              variant="secondary"
              onClick={() => setPendingCancel(null)}
              disabled={cancelInviteMut.isPending}
            >
              Voltar
            </Button>
            <Button
              variant="destructive"
              onClick={handleCancelInvite}
              disabled={cancelInviteMut.isPending}
            >
              <RiDeleteBinLine className="mr-1.5 size-4" aria-hidden />
              Cancelar convite
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
