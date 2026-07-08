// src/app/(app)/admin/ia/providers/page.tsx
//
// Admin · IA · Provedores LLM.
//
// Lista as credenciais globais cadastradas (Anthropic / OpenAI). Permite
// cadastrar nova, editar (rotacionar key, ajustar ZDR/active/notes) e
// excluir. Acessivel apenas a usuarios do tenant mantenedor (CLAUDE.md §19.2)
// — backend protege com `require_system_maintainer` (HTTP 403).
//
// Estado da URL (deep-linkavel):
//   ?action=new            → drawer de criacao
//   ?selected=<uuid>       → drawer de edicao da credencial selecionada
//

"use client"

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { toast } from "sonner"
import {
  RiAddLine,
  RiCheckLine,
  RiDeleteBinLine,
  RiKey2Line,
  RiMoreLine,
  RiShieldCheckLine,
  RiShieldLine,
} from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"
import { formatDistanceToNow, parseISO } from "date-fns"
import { ptBR } from "date-fns/locale"

import { Button } from "@/components/tremor/Button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/tremor/Dialog"
import { Divider } from "@/components/tremor/Divider"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/tremor/DropdownMenu"
import {
  DataTableShell,
  DateCell,
  DrillDownSheet,
  PageHeader,
} from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import type { AIProviderCredentialRead } from "@/lib/api-client"
import {
  useCreateProvider,
  useDeleteProvider,
  useProviders,
  useUpdateProvider,
} from "@/lib/hooks/admin-ai"
import {
  AI_PROVIDER_LABEL,
  buildUpdatePayload,
  type ProviderCreateValues,
  type ProviderUpdateValues,
} from "@/lib/schemas/ai-provider-schema"
import { cx } from "@/lib/utils"

import {
  ProviderCreateForm,
  ProviderEditForm,
} from "./_components/ProviderForm"

// ───────────────────────────────────────────────────────────────────────────
// Cells custom (compartilhadas com a tabela)
// ───────────────────────────────────────────────────────────────────────────

const PROVIDER_TONES: Record<
  AIProviderCredentialRead["provider"],
  { bg: string; fg: string; dot: string }
> = {
  anthropic: {
    bg: "bg-violet-50 dark:bg-violet-500/10",
    fg: "text-violet-700 dark:text-violet-300",
    dot: "bg-violet-500",
  },
  openai: {
    bg: "bg-emerald-50 dark:bg-emerald-500/10",
    fg: "text-emerald-700 dark:text-emerald-300",
    dot: "bg-emerald-500",
  },
}

function ProviderBadge({ provider }: { provider: AIProviderCredentialRead["provider"] }) {
  const tone = PROVIDER_TONES[provider]
  return (
    <span className={cx(tableTokens.badgeWithDot, tone.bg, tone.fg)}>
      <span aria-hidden className={cx("size-1.5 rounded-full", tone.dot)} />
      {AI_PROVIDER_LABEL[provider]}
    </span>
  )
}

function ZdrBadge({ enabled }: { enabled: boolean }) {
  return (
    <span
      className={enabled ? tableTokens.badgeSuccess : tableTokens.badgeNeutral}
      title={
        enabled
          ? "ZDR contratado — adapter permite uso em producao."
          : "ZDR desligado — adapter bloqueara chamadas em producao."
      }
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
  if (!value) {
    return <span className={tableTokens.cellMuted}>—</span>
  }
  const distance = formatDistanceToNow(parseISO(value), {
    addSuffix: true,
    locale: ptBR,
  })
  return (
    <span className={tableTokens.cellSecondary} title={value}>
      {distance}
    </span>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Page
// ───────────────────────────────────────────────────────────────────────────

const col = createColumnHelper<AIProviderCredentialRead>()

export default function ProvidersPage() {
  const router = useRouter()
  const sp = useSearchParams()
  const action = sp.get("action") // "new" | null
  const selectedId = sp.get("selected")

  const providersQuery = useProviders()
  const createMut = useCreateProvider()
  const updateMut = useUpdateProvider()
  const deleteMut = useDeleteProvider()

  const data = providersQuery.data ?? []
  const selected = React.useMemo(
    () => (selectedId ? data.find((p) => p.id === selectedId) ?? null : null),
    [data, selectedId],
  )

  // Confirmacao de delete: id em estado local (nao via URL — operacao
  // efemera, sem necessidade de deep-linking).
  const [pendingDelete, setPendingDelete] = React.useState<
    AIProviderCredentialRead | null
  >(null)

  // ── Filtros locais (busca + segment) — counts/segmentFiltered/visibleCount
  // ficam dentro do <DataTableShell>, calculados a partir de `segments.options`.
  const [search, setSearch] = React.useState("")
  const [segment, setSegment] = React.useState<
    "todas" | "ativas" | "suspensas" | "anthropic" | "openai"
  >("todas")

  // ── Navigation helpers ──────────────────────────────────────────────────
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
    (p: AIProviderCredentialRead) => setQuery({ action: null, selected: p.id }),
    [setQuery],
  )
  const closeSheet = React.useCallback(
    () => setQuery({ action: null, selected: null }),
    [setQuery],
  )

  // ── Submit handlers ─────────────────────────────────────────────────────
  const handleCreate = React.useCallback(
    async (values: ProviderCreateValues) => {
      try {
        await createMut.mutateAsync({
          provider: values.provider,
          alias: values.alias.trim(),
          api_key: values.api_key.trim(),
          org_id: values.org_id?.trim() || null,
          zdr_enabled: values.zdr_enabled,
          notes: values.notes?.trim() || null,
        })
        toast.success(`Credencial '${values.alias}' cadastrada.`)
        closeSheet()
      } catch (err) {
        toast.error(
          err instanceof Error ? err.message : "Falha ao cadastrar credencial.",
        )
      }
    },
    [createMut, closeSheet],
  )

  const handleEdit = React.useCallback(
    async (values: ProviderUpdateValues) => {
      if (!selected) return
      try {
        await updateMut.mutateAsync({
          id: selected.id,
          payload: buildUpdatePayload(values),
        })
        toast.success(`Credencial '${selected.alias}' atualizada.`)
        closeSheet()
      } catch (err) {
        toast.error(
          err instanceof Error ? err.message : "Falha ao atualizar credencial.",
        )
      }
    },
    [updateMut, selected, closeSheet],
  )

  const handleDelete = React.useCallback(async () => {
    if (!pendingDelete) return
    try {
      await deleteMut.mutateAsync(pendingDelete.id)
      toast.success(`Credencial '${pendingDelete.alias}' excluida.`)
      setPendingDelete(null)
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Falha ao excluir credencial.",
      )
    }
  }, [deleteMut, pendingDelete])

  // ── Columns ─────────────────────────────────────────────────────────────
  const columns = React.useMemo<ColumnDef<AIProviderCredentialRead, unknown>[]>(
    () => [
      col.accessor("provider", {
        header: "Provedor",
        size: 130,
        cell: (info) => <ProviderBadge provider={info.getValue()} />,
      }) as ColumnDef<AIProviderCredentialRead, unknown>,
      col.accessor("alias", {
        header: "Alias",
        size: 200,
        cell: (info) => (
          <span className={tableTokens.cellTextMono}>{info.getValue()}</span>
        ),
      }) as ColumnDef<AIProviderCredentialRead, unknown>,
      col.accessor("zdr_enabled", {
        header: "ZDR",
        size: 90,
        cell: (info) => <ZdrBadge enabled={info.getValue()} />,
      }) as ColumnDef<AIProviderCredentialRead, unknown>,
      col.accessor("active", {
        header: "Status",
        size: 100,
        cell: (info) => <ActiveBadge active={info.getValue()} />,
      }) as ColumnDef<AIProviderCredentialRead, unknown>,
      col.accessor("rotated_at", {
        header: "Ultima rotacao",
        size: 150,
        cell: (info) => <RotatedAtCell value={info.getValue()} />,
      }) as ColumnDef<AIProviderCredentialRead, unknown>,
      col.accessor("created_at", {
        header: "Criada em",
        size: 110,
        cell: (info) => <DateCell value={info.getValue()} />,
      }) as ColumnDef<AIProviderCredentialRead, unknown>,
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
                <DropdownMenuItem
                  onSelect={() => openEdit(row.original)}
                >
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
      }) as ColumnDef<AIProviderCredentialRead, unknown>,
    ],
    [openEdit],
  )

  // ── Render ──────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
      <PageHeader
        title="Provedores LLM"
        info="Credenciais globais usadas por todos os tenants para chamar OpenAI e Anthropic. Acessivel apenas ao tenant mantenedor."
        subtitle="Inteligencia Artificial · Administracao"
        actions={
          <Button
            variant="primary"
            onClick={openNew}
            disabled={providersQuery.isLoading}
          >
            <RiAddLine className="mr-1 size-4" aria-hidden />
            Novo provedor
          </Button>
        }
      />

      <DataTableShell<AIProviderCredentialRead>
        data={data}
        columns={columns}
        loading={providersQuery.isLoading}
        error={providersQuery.error}
        onRetry={() => providersQuery.refetch()}
        search={{
          value: search,
          onChange: setSearch,
          placeholder: "Buscar por alias, provedor ou nota...",
        }}
        segments={{
          value: segment,
          onChange: (v) => setSegment(v as typeof segment),
          options: [
            { value: "todas",     label: "Todas",     filter: () => true },
            { value: "ativas",    label: "Ativas",    filter: (p) => p.active },
            { value: "suspensas", label: "Suspensas", filter: (p) => !p.active },
            { value: "anthropic", label: "Anthropic", filter: (p) => p.provider === "anthropic" },
            { value: "openai",    label: "OpenAI",    filter: (p) => p.provider === "openai" },
          ],
        }}
        itemNoun={{ singular: "credencial", plural: "credenciais" }}
        onRowClick={openEdit}
        emptyState={{
          icon: RiKey2Line,
          title: "Nenhuma credencial cadastrada",
          description: "Cadastre a primeira credencial Anthropic ou OpenAI para liberar IA aos tenants.",
          action: (
            <Button variant="primary" onClick={openNew}>
              <RiAddLine className="mr-1 size-4" aria-hidden />
              Cadastrar credencial
            </Button>
          ),
        }}
      />

      {/* Drawer: Novo */}
      <DrillDownSheet
        open={action === "new"}
        onClose={closeSheet}
        title="Novo provedor LLM"
        size="md"
      >
        <div className="p-6">
          <ProviderCreateForm
            submitting={createMut.isPending}
            onSubmit={handleCreate}
            onCancel={closeSheet}
          />
        </div>
      </DrillDownSheet>

      {/* Drawer: Editar */}
      <DrillDownSheet
        open={selected !== null}
        onClose={closeSheet}
        title={selected ? `Editar · ${selected.alias}` : ""}
        size="md"
      >
        {selected && (
          <div className="p-6">
            <ProviderEditForm
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
            <DialogTitle>Excluir credencial</DialogTitle>
            <DialogDescription>
              Esta acao remove permanentemente a credencial{" "}
              <span className="font-mono text-gray-900 dark:text-gray-50">
                {pendingDelete?.alias}
              </span>
              . Chamadas em curso continuarao com a key ate completarem.
              Tenants que dependem dela perderao acesso a IA ate uma nova
              ser cadastrada.
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
              Excluir credencial
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
