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
// `optional`: famílias de consulta com login próprio (Infosimples: JUCESP e
// protestos têm CPF/senha DISTINTOS) — cadastráveis depois, na mesma credencial.
type SecretField = { key: string; label: string; optional?: boolean }
const SECRET_FIELDS: Record<string, SecretField[]> = {
  bigdatacorp: [
    { key: "access_token", label: "Access Token" },
    { key: "token_id", label: "Token ID" },
  ],
  infosimples: [
    { key: "api_key", label: "API Key" },
    { key: "jucesp_login_cpf", label: "JUCESP · CPF de acesso", optional: true },
    { key: "jucesp_login_senha", label: "JUCESP · Senha", optional: true },
    { key: "protesto_login_cpf", label: "Protestos · CPF de acesso", optional: true },
    { key: "protesto_login_senha", label: "Protestos · Senha", optional: true },
  ],
}
function secretFieldsFor(slug?: string): SecretField[] {
  return (slug && SECRET_FIELDS[slug]) || [{ key: "api_key", label: "Chave" }]
}

// ─── Cells ──────────────────────────────────────────────────────────────────

function ZdrBadge({ enabled }: { enabled: boolean }) {
  return (
    <span
      className={enabled ? tableTokens.badgeSuccess : tableTokens.badgeNeutral}
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
    // Status semantico usa token (§4: azul nao e cor de "sucesso").
    <span className={active ? tableTokens.badgeSuccess : tableTokens.badgeNeutral}>
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
  initialProviderId,
  submitting,
  onSubmit,
  onCancel,
}: {
  providers: DataProviderRead[]
  /** Pré-seleção (vindo do card do provedor na faixa do topo). */
  initialProviderId?: string | null
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
  const [providerId, setProviderId] = React.useState(
    initialProviderId ?? enabled[0]?.id ?? "",
  )
  const [alias, setAlias] = React.useState("")
  const [secret, setSecret] = React.useState<Record<string, string>>({})
  const [zdr, setZdr] = React.useState(false)
  const [notes, setNotes] = React.useState("")

  const slug = providers.find((p) => p.id === providerId)?.slug
  const fields = secretFieldsFor(slug)
  const valid =
    providerId &&
    alias.trim() &&
    fields.every((f) => f.optional || (secret[f.key] ?? "").trim())

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
          <Label htmlFor={f.key}>
            {f.label}
            {f.optional && (
              <span className="ml-1 font-normal text-gray-400">(opcional)</span>
            )}
          </Label>
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

// Linha da tabela: o PROVEDOR e a entidade. Credencial inline quando existe;
// provedor sem credencial aparece com status "Sem credencial" + CTA.
// Provedor com N credenciais vira N linhas (alias distingue).
type ProviderRow = {
  provider: DataProviderRead
  credential: DataProviderCredentialRead | null
}

const col = createColumnHelper<ProviderRow>()

export default function DataProvidersPage() {
  const providersQuery = useDataProviders()
  const credentialsQuery = useDataProviderCredentials()
  const createMut = useCreateDataProviderCredential()
  const updateMut = useUpdateDataProviderCredential()
  const deleteMut = useDeleteDataProviderCredential()

  const providers = providersQuery.data ?? []
  const data = credentialsQuery.data ?? []
  const rows = React.useMemo<ProviderRow[]>(() => {
    return providers.flatMap((p): ProviderRow[] => {
      const creds = data.filter((c) => c.provider_id === p.id)
      if (creds.length === 0) return [{ provider: p, credential: null }]
      return creds.map((c) => ({ provider: p, credential: c }))
    })
  }, [providers, data])

  const [creating, setCreating] = React.useState(false)
  // Pré-seleção do provedor ao criar pela faixa de provedores do topo.
  const [presetProviderId, setPresetProviderId] = React.useState<string | null>(null)
  const [editing, setEditing] = React.useState<DataProviderCredentialRead | null>(
    null,
  )
  const [pendingDelete, setPendingDelete] =
    React.useState<DataProviderCredentialRead | null>(null)
  const [search, setSearch] = React.useState("")
  const [segment, setSegment] = React.useState<
    "todas" | "ativas" | "suspensas" | "sem-credencial"
  >(
    "todas",
  )

  const columns = React.useMemo<ColumnDef<ProviderRow, unknown>[]>(
    () => [
      col.accessor((r) => r.provider.name, {
        id: "provedor",
        header: "Provedor",
        size: 170,
        cell: (info) => (
          <span
            className={cx(
              tableTokens.badgeWithDot,
              info.row.original.provider.enabled
                ? "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300"
                : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400",
            )}
          >
            <span
              aria-hidden
              className={cx(
                "size-1.5 rounded-full",
                info.row.original.provider.enabled ? "bg-amber-500" : "bg-gray-400",
              )}
            />
            {String(info.getValue())}
          </span>
        ),
      }) as ColumnDef<ProviderRow, unknown>,
      col.accessor(
        (r) =>
          r.credential
            ? r.credential.active
              ? "ativa"
              : "suspensa"
            : "sem credencial",
        {
          id: "status",
          header: "Status",
          size: 150,
          cell: (info) => {
            const c = info.row.original.credential
            if (!c) {
              return (
                <span
                  className={tableTokens.badgeWarning}
                  title="Sem credencial cadastrada — as consultas deste provedor estão indisponíveis."
                >
                  Sem credencial
                </span>
              )
            }
            return <ActiveBadge active={c.active} />
          },
        },
      ) as ColumnDef<ProviderRow, unknown>,
      col.accessor((r) => r.credential?.alias ?? "", {
        id: "alias",
        header: "Alias",
        size: 200,
        cell: (info) =>
          info.getValue() ? (
            <span className={tableTokens.cellTextMono}>{String(info.getValue())}</span>
          ) : (
            <span className={tableTokens.cellMuted}>—</span>
          ),
      }) as ColumnDef<ProviderRow, unknown>,
      col.display({
        id: "zdr",
        header: "ZDR",
        size: 90,
        cell: ({ row }) =>
          row.original.credential ? (
            <ZdrBadge enabled={row.original.credential.zdr_enabled} />
          ) : (
            <span className={tableTokens.cellMuted}>—</span>
          ),
      }) as ColumnDef<ProviderRow, unknown>,
      col.display({
        id: "rotacao",
        header: "Ultima rotacao",
        size: 150,
        cell: ({ row }) => (
          <RotatedAtCell value={row.original.credential?.rotated_at ?? null} />
        ),
      }) as ColumnDef<ProviderRow, unknown>,
      col.display({
        id: "criada",
        header: "Criada em",
        size: 110,
        cell: ({ row }) =>
          row.original.credential ? (
            <DateCell value={row.original.credential.created_at} />
          ) : (
            <span className={tableTokens.cellMuted}>—</span>
          ),
      }) as ColumnDef<ProviderRow, unknown>,
      col.display({
        id: "actions",
        header: "",
        size: 170,
        cell: ({ row }) => {
          const c = row.original.credential
          if (!c) {
            return (
              <div className="flex justify-end">
                <Button
                  variant="secondary"
                  className="h-7"
                  disabled={!row.original.provider.enabled}
                  onClick={(e) => {
                    e.stopPropagation()
                    setPresetProviderId(row.original.provider.id)
                    setCreating(true)
                  }}
                >
                  <RiAddLine className="mr-1 size-3.5" aria-hidden />
                  Cadastrar credencial
                </Button>
              </div>
            )
          }
          return (
            <div className="flex justify-end">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    className="size-7 p-0"
                    aria-label={`Acoes de ${c.alias}`}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <RiMoreLine className="size-4" aria-hidden />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" sideOffset={4}>
                  <DropdownMenuItem onSelect={() => setEditing(c)}>
                    Editar
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onSelect={() => setPendingDelete(c)}
                    className="text-red-600 focus:text-red-700 dark:text-red-400 dark:focus:text-red-300"
                  >
                    <RiDeleteBinLine className="mr-2 size-4" aria-hidden />
                    Excluir
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          )
        },
      }) as ColumnDef<ProviderRow, unknown>,
    ],
    [],
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
      setPresetProviderId(null)
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

      <DataTableShell<ProviderRow>
        data={rows}
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
            {
              value: "ativas",
              label: "Ativas",
              filter: (r) => Boolean(r.credential?.active),
            },
            {
              value: "suspensas",
              label: "Suspensas",
              filter: (r) => Boolean(r.credential && !r.credential.active),
            },
            {
              value: "sem-credencial",
              label: "Sem credencial",
              filter: (r) => r.credential === null,
            },
          ],
        }}
        itemNoun={{ singular: "provedor", plural: "provedores" }}
        onRowClick={(r) => {
          if (r.credential) {
            setEditing(r.credential)
          } else if (r.provider.enabled) {
            setPresetProviderId(r.provider.id)
            setCreating(true)
          }
        }}
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
        onClose={() => {
          setCreating(false)
          setPresetProviderId(null)
        }}
        title="Nova credencial de dados"
        size="md"
      >
        <div className="p-6">
          <CreateForm
            key={presetProviderId ?? "default"}
            initialProviderId={presetProviderId}
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
