// src/app/(app)/admin/dados/provedores/page.tsx
//
// Admin · Provedores de Dados (BigDataCorp, Infosimples...).
//
// Credenciais GLOBAIS (nivel mantenedor) de fontes externas de dado — paralelo
// aos Provedores de IA. O secret e vendor-specific (BDC: access_token + token_id)
// e cifrado server-side; a listagem nunca mostra o segredo. Backend protege com
// require_system_maintainer (HTTP 403).

"use client"

import * as React from "react"
import { toast } from "sonner"
import {
  RiAddLine,
  RiCheckLine,
  RiDatabase2Line,
  RiDeleteBinLine,
  RiMoreLine,
  RiShieldCheckLine,
  RiShieldLine,
} from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"
import { formatDistanceToNow, parseISO } from "date-fns"
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
import { Divider } from "@/components/tremor/Divider"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/tremor/DropdownMenu"
import { Input } from "@/components/tremor/Input"
import { Label } from "@/components/tremor/Label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/tremor/Select"
import { Switch } from "@/components/tremor/Switch"
import {
  DataTableShell,
  DateCell,
  DrillDownSheet,
  PageHeader,
} from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import type {
  DataProviderCredentialRead,
  DataProviderRead,
} from "@/lib/api-client"
import {
  useCreateDataProviderCredential,
  useDataProviderCredentials,
  useDataProviders,
  useDeleteDataProviderCredential,
  useUpdateDataProviderCredential,
} from "@/lib/hooks/admin-data-providers"
import { cx } from "@/lib/utils"

// Campos do secret por slug de provider (vendor-specific). Fallback generico.
const SECRET_FIELDS: Record<string, { key: string; label: string }[]> = {
  bigdatacorp: [
    { key: "access_token", label: "Access Token" },
    { key: "token_id", label: "Token ID" },
  ],
  infosimples: [{ key: "api_key", label: "API Key" }],
}
function secretFieldsFor(slug?: string): { key: string; label: string }[] {
  return (slug && SECRET_FIELDS[slug]) || [{ key: "api_key", label: "Chave" }]
}

// ─── Cells ──────────────────────────────────────────────────────────────────

function ZdrBadge({ enabled }: { enabled: boolean }) {
  return (
    <span
      className={cx(
        tableTokens.badge,
        enabled
          ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
          : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
      )}
      title={enabled ? "ZDR contratado." : "ZDR desligado."}
    >
      {enabled ? (
        <RiShieldCheckLine className="size-3" aria-hidden />
      ) : (
        <RiShieldLine className="size-3" aria-hidden />
      )}
      {enabled ? "Ativo" : "Inativo"}
    </span>
  )
}

function ActiveBadge({ active }: { active: boolean }) {
  return (
    <span
      className={cx(
        tableTokens.badge,
        active
          ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
          : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400",
      )}
    >
      {active && <RiCheckLine className="size-3" aria-hidden />}
      {active ? "Ativa" : "Suspensa"}
    </span>
  )
}

function RotatedAtCell({ value }: { value: string | null }) {
  if (!value) return <span className={tableTokens.cellMuted}>—</span>
  return (
    <span className={tableTokens.cellSecondary} title={value}>
      {formatDistanceToNow(parseISO(value), { addSuffix: true, locale: ptBR })}
    </span>
  )
}

// ─── Forms ────────────────────────────────────────────────────────────────────

function CreateForm({
  providers,
  submitting,
  onSubmit,
  onCancel,
}: {
  providers: DataProviderRead[]
  submitting: boolean
  onSubmit: (v: {
    provider_id: string
    alias: string
    secret: Record<string, string>
    zdr_enabled: boolean
    notes: string | null
  }) => void
  onCancel: () => void
}) {
  const enabled = providers.filter((p) => p.enabled)
  const [providerId, setProviderId] = React.useState(enabled[0]?.id ?? "")
  const [alias, setAlias] = React.useState("")
  const [secret, setSecret] = React.useState<Record<string, string>>({})
  const [zdr, setZdr] = React.useState(false)
  const [notes, setNotes] = React.useState("")

  const slug = providers.find((p) => p.id === providerId)?.slug
  const fields = secretFieldsFor(slug)
  const valid =
    providerId &&
    alias.trim() &&
    fields.every((f) => (secret[f.key] ?? "").trim())

  return (
    <div className="space-y-4">
      <div>
        <Label htmlFor="provider">Provedor</Label>
        <Select value={providerId} onValueChange={setProviderId}>
          <SelectTrigger id="provider" className="mt-1">
            <SelectValue placeholder="Selecione" />
          </SelectTrigger>
          <SelectContent>
            {enabled.map((p) => (
              <SelectItem key={p.id} value={p.id}>
                {p.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div>
        <Label htmlFor="alias">Alias</Label>
        <Input
          id="alias"
          value={alias}
          onChange={(e) => setAlias(e.target.value)}
          placeholder="bigdatacorp_prod_2026"
          className="mt-1"
        />
        <p className={cx(tableTokens.cellSecondary, "mt-1")}>
          Rótulo único pra distinguir credenciais (ex.: prod vs uat).
        </p>
      </div>

      {fields.map((f) => (
        <div key={f.key}>
          <Label htmlFor={f.key}>{f.label}</Label>
          <Input
            id={f.key}
            type="password"
            autoComplete="off"
            value={secret[f.key] ?? ""}
            onChange={(e) =>
              setSecret((s) => ({ ...s, [f.key]: e.target.value }))
            }
            className="mt-1"
          />
        </div>
      ))}

      <div className="flex items-center justify-between">
        <div>
          <Label htmlFor="zdr">ZDR contratado</Label>
          <p className={cx(tableTokens.cellSecondary, "mt-0.5")}>
            Provider não retém dados das consultas.
          </p>
        </div>
        <Switch id="zdr" checked={zdr} onCheckedChange={setZdr} />
      </div>

      <div>
        <Label htmlFor="notes">Notas (opcional)</Label>
        <Input
          id="notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          className="mt-1"
        />
      </div>

      <div className="flex justify-end gap-2 pt-2">
        <Button variant="secondary" onClick={onCancel} disabled={submitting}>
          Cancelar
        </Button>
        <Button
          variant="primary"
          disabled={!valid || submitting}
          isLoading={submitting}
          onClick={() =>
            onSubmit({
              provider_id: providerId,
              alias: alias.trim(),
              secret,
              zdr_enabled: zdr,
              notes: notes.trim() || null,
            })
          }
        >
          Cadastrar
        </Button>
      </div>
    </div>
  )
}

function EditForm({
  cred,
  providers,
  submitting,
  onSubmit,
  onCancel,
}: {
  cred: DataProviderCredentialRead
  providers: DataProviderRead[]
  submitting: boolean
  onSubmit: (v: {
    secret?: Record<string, string>
    zdr_enabled: boolean
    active: boolean
    notes: string | null
  }) => void
  onCancel: () => void
}) {
  const slug = providers.find((p) => p.id === cred.provider_id)?.slug
  const fields = secretFieldsFor(slug)
  const [secret, setSecret] = React.useState<Record<string, string>>({})
  const [zdr, setZdr] = React.useState(cred.zdr_enabled)
  const [active, setActive] = React.useState(cred.active)
  const [notes, setNotes] = React.useState(cred.notes ?? "")

  const filledSecret = Object.fromEntries(
    Object.entries(secret).filter(([, v]) => (v ?? "").trim()),
  )

  return (
    <div className="space-y-4">
      <div className="rounded-md border border-gray-200 bg-gray-50/60 p-3 dark:border-gray-800 dark:bg-gray-950/40">
        <p className={tableTokens.cellSecondary}>Alias</p>
        <p className={tableTokens.cellTextMono}>{cred.alias}</p>
      </div>

      <p className={tableTokens.cellSecondary}>
        Preencha os campos abaixo só pra <b>rotacionar</b> o secret — deixe
        vazio pra manter o atual.
      </p>
      {fields.map((f) => (
        <div key={f.key}>
          <Label htmlFor={`e_${f.key}`}>{f.label}</Label>
          <Input
            id={`e_${f.key}`}
            type="password"
            autoComplete="off"
            placeholder="•••••• (manter)"
            value={secret[f.key] ?? ""}
            onChange={(e) =>
              setSecret((s) => ({ ...s, [f.key]: e.target.value }))
            }
            className="mt-1"
          />
        </div>
      ))}

      <div className="flex items-center justify-between">
        <Label htmlFor="e_zdr">ZDR contratado</Label>
        <Switch id="e_zdr" checked={zdr} onCheckedChange={setZdr} />
      </div>
      <div className="flex items-center justify-between">
        <Label htmlFor="e_active">Ativa</Label>
        <Switch id="e_active" checked={active} onCheckedChange={setActive} />
      </div>

      <div>
        <Label htmlFor="e_notes">Notas</Label>
        <Input
          id="e_notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          className="mt-1"
        />
      </div>

      <div className="flex justify-end gap-2 pt-2">
        <Button variant="secondary" onClick={onCancel} disabled={submitting}>
          Cancelar
        </Button>
        <Button
          variant="primary"
          disabled={submitting}
          isLoading={submitting}
          onClick={() =>
            onSubmit({
              secret:
                Object.keys(filledSecret).length > 0 ? filledSecret : undefined,
              zdr_enabled: zdr,
              active,
              notes: notes.trim() || null,
            })
          }
        >
          Salvar
        </Button>
      </div>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

const col = createColumnHelper<DataProviderCredentialRead>()

export default function DataProvidersPage() {
  const providersQuery = useDataProviders()
  const credentialsQuery = useDataProviderCredentials()
  const createMut = useCreateDataProviderCredential()
  const updateMut = useUpdateDataProviderCredential()
  const deleteMut = useDeleteDataProviderCredential()

  const providers = providersQuery.data ?? []
  const data = credentialsQuery.data ?? []
  const providerName = React.useCallback(
    (id: string) => providers.find((p) => p.id === id)?.name ?? "—",
    [providers],
  )

  const [creating, setCreating] = React.useState(false)
  const [editing, setEditing] = React.useState<DataProviderCredentialRead | null>(
    null,
  )
  const [pendingDelete, setPendingDelete] =
    React.useState<DataProviderCredentialRead | null>(null)
  const [search, setSearch] = React.useState("")
  const [segment, setSegment] = React.useState<"todas" | "ativas" | "suspensas">(
    "todas",
  )

  const columns = React.useMemo<ColumnDef<DataProviderCredentialRead, unknown>[]>(
    () => [
      col.accessor("provider_id", {
        header: "Provedor",
        size: 160,
        cell: (info) => (
          <span className={cx(tableTokens.badgeWithDot, "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300")}>
            <span aria-hidden className="size-1.5 rounded-full bg-amber-500" />
            {providerName(info.getValue())}
          </span>
        ),
      }) as ColumnDef<DataProviderCredentialRead, unknown>,
      col.accessor("alias", {
        header: "Alias",
        size: 200,
        cell: (info) => (
          <span className={tableTokens.cellTextMono}>{info.getValue()}</span>
        ),
      }) as ColumnDef<DataProviderCredentialRead, unknown>,
      col.accessor("zdr_enabled", {
        header: "ZDR",
        size: 90,
        cell: (info) => <ZdrBadge enabled={info.getValue()} />,
      }) as ColumnDef<DataProviderCredentialRead, unknown>,
      col.accessor("active", {
        header: "Status",
        size: 100,
        cell: (info) => <ActiveBadge active={info.getValue()} />,
      }) as ColumnDef<DataProviderCredentialRead, unknown>,
      col.accessor("rotated_at", {
        header: "Ultima rotacao",
        size: 150,
        cell: (info) => <RotatedAtCell value={info.getValue()} />,
      }) as ColumnDef<DataProviderCredentialRead, unknown>,
      col.accessor("created_at", {
        header: "Criada em",
        size: 110,
        cell: (info) => <DateCell value={info.getValue()} />,
      }) as ColumnDef<DataProviderCredentialRead, unknown>,
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
                  aria-label={`Acoes de ${row.original.alias}`}
                  onClick={(e) => e.stopPropagation()}
                >
                  <RiMoreLine className="size-4" aria-hidden />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" sideOffset={4}>
                <DropdownMenuItem onSelect={() => setEditing(row.original)}>
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
      }) as ColumnDef<DataProviderCredentialRead, unknown>,
    ],
    [providerName],
  )

  const handleCreate = async (v: {
    provider_id: string
    alias: string
    secret: Record<string, string>
    zdr_enabled: boolean
    notes: string | null
  }) => {
    try {
      await createMut.mutateAsync(v)
      toast.success(`Credencial '${v.alias}' cadastrada.`)
      setCreating(false)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao cadastrar.")
    }
  }

  const handleEdit = async (v: {
    secret?: Record<string, string>
    zdr_enabled: boolean
    active: boolean
    notes: string | null
  }) => {
    if (!editing) return
    try {
      await updateMut.mutateAsync({ id: editing.id, payload: v })
      toast.success(`Credencial '${editing.alias}' atualizada.`)
      setEditing(null)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao atualizar.")
    }
  }

  const handleDelete = async () => {
    if (!pendingDelete) return
    try {
      await deleteMut.mutateAsync(pendingDelete.id)
      toast.success(`Credencial '${pendingDelete.alias}' excluida.`)
      setPendingDelete(null)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao excluir.")
    }
  }

  return (
    <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
      <PageHeader
        title="Provedores de Dados"
        info="Credenciais globais de fontes externas (BigDataCorp...) usadas por todos os tenants e cobradas por consulta. Nível mantenedor — o Serasa próprio do tenant fica em Integrações."
        subtitle="Fontes de Dados · Administração"
        actions={
          <Button
            variant="primary"
            onClick={() => setCreating(true)}
            disabled={providersQuery.isLoading}
          >
            <RiAddLine className="mr-1 size-4" aria-hidden />
            Nova credencial
          </Button>
        }
      />

      <DataTableShell<DataProviderCredentialRead>
        data={data}
        columns={columns}
        loading={credentialsQuery.isLoading}
        error={credentialsQuery.error}
        onRetry={() => credentialsQuery.refetch()}
        search={{
          value: search,
          onChange: setSearch,
          placeholder: "Buscar por alias ou nota...",
        }}
        segments={{
          value: segment,
          onChange: (v) => setSegment(v as typeof segment),
          options: [
            { value: "todas", label: "Todas", filter: () => true },
            { value: "ativas", label: "Ativas", filter: (c) => c.active },
            { value: "suspensas", label: "Suspensas", filter: (c) => !c.active },
          ],
        }}
        itemNoun={{ singular: "credencial", plural: "credenciais" }}
        onRowClick={(c) => setEditing(c)}
        emptyState={{
          icon: RiDatabase2Line,
          title: "Nenhuma credencial cadastrada",
          description:
            "Cadastre a credencial do BigDataCorp (access_token + token_id) pra liberar as consultas de dados.",
          action: (
            <Button variant="primary" onClick={() => setCreating(true)}>
              <RiAddLine className="mr-1 size-4" aria-hidden />
              Cadastrar credencial
            </Button>
          ),
        }}
      />

      <DrillDownSheet
        open={creating}
        onClose={() => setCreating(false)}
        title="Nova credencial de dados"
        size="md"
      >
        <div className="p-6">
          <CreateForm
            providers={providers}
            submitting={createMut.isPending}
            onSubmit={handleCreate}
            onCancel={() => setCreating(false)}
          />
        </div>
      </DrillDownSheet>

      <DrillDownSheet
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={editing ? `Editar · ${editing.alias}` : ""}
        size="md"
      >
        {editing && (
          <div className="p-6">
            <EditForm
              cred={editing}
              providers={providers}
              submitting={updateMut.isPending}
              onSubmit={handleEdit}
              onCancel={() => setEditing(null)}
            />
          </div>
        )}
      </DrillDownSheet>

      <Dialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Excluir credencial</DialogTitle>
            <DialogDescription>
              Remove permanentemente a credencial{" "}
              <span className="font-mono text-gray-900 dark:text-gray-50">
                {pendingDelete?.alias}
              </span>
              . As consultas que dependem dela falharão até cadastrar outra.
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
              Excluir
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
