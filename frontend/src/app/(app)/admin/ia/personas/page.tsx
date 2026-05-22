// src/app/(app)/admin/ia/personas/page.tsx
//
// Admin · IA · Personas (DB-backed, F2.c.1, CLAUDE.md §19.12).
//
// Lista as personas de agentes versionadas em DB. Permite:
//  - Cadastrar nova familia (vira v1 e e ativada)
//  - Editar persona (sempre cria nova versao — base e imutavel)
//  - Ativar uma versao (rollback de 1 click)
//  - Arquivar versao inativa (soft-delete)
//
// Acessivel apenas a usuarios do tenant mantenedor — backend protege com
// `require_system_maintainer` (HTTP 403).
//
// Pattern: ListagemCrudInline (CLAUDE.md §7) — PageHeader + Card com
// FilterSearch + DataTable + DrillDownSheet pra criar/editar.

"use client"

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { toast } from "sonner"
import {
  RiAddLine,
  RiArchive2Line,
  RiCheckLine,
  RiEdit2Line,
  RiHistoryLine,
  RiMoreLine,
  RiUserStarLine,
} from "@remixicon/react"
import { formatDistanceToNow, parseISO } from "date-fns"
import { ptBR } from "date-fns/locale"
import { type ColumnDef } from "@tanstack/react-table"

import { Badge } from "@/components/tremor/Badge"
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
  DrillDownSheet,
  PageHeader,
} from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import type { AIPersonaDetail, AIPersonaVersionInfo } from "@/lib/api-client"
import {
  useActivatePersonaVersion,
  useArchivePersona,
  useCreatePersona,
  usePersonaDetail,
  usePersonas,
  useUpdatePersona,
} from "@/lib/hooks/admin-ai"
import {
  buildCreatePayload,
  buildUpdatePayload,
  type PersonaCreateValues,
  type PersonaUpdateValues,
} from "@/lib/schemas/ai-persona-schema"
import { cx } from "@/lib/utils"

import { PersonaCreateForm, PersonaEditForm } from "./_components/PersonaForm"

// ───────────────────────────────────────────────────────────────────────────
// Cells / badges
// ───────────────────────────────────────────────────────────────────────────

function StatusBadge({ active, archived }: { active: boolean; archived: boolean }) {
  if (archived) {
    return (
      <Badge variant="neutral" className={tableTokens.badge}>
        Arquivada
      </Badge>
    )
  }
  if (active) {
    return (
      <Badge variant="success" className={tableTokens.badge}>
        Ativa
      </Badge>
    )
  }
  return (
    <Badge variant="neutral" className={tableTokens.badge}>
      Inativa
    </Badge>
  )
}

function DomainsCell({ domains }: { domains: string[] | null }) {
  if (!domains || domains.length === 0) {
    return <span className={tableTokens.cellMuted}>—</span>
  }
  return (
    <div className="flex flex-wrap gap-1">
      {domains.slice(0, 3).map((d) => (
        <span
          key={d}
          className={cx(
            "rounded-sm px-1.5 py-0.5 text-[11px] font-medium",
            "bg-gray-100 text-gray-700",
            "dark:bg-gray-800 dark:text-gray-300",
          )}
        >
          {d}
        </span>
      ))}
      {domains.length > 3 && (
        <span className={tableTokens.cellMuted}>+{domains.length - 3}</span>
      )}
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Page
// ───────────────────────────────────────────────────────────────────────────

// sheetState.kind=="edit" nunca e retornado pelo useMemo (edit e controlado
// por `editingId` separado, nao via URL). Removido do union pra TS strict.
type DetailSheetState =
  | { kind: "closed" }
  | { kind: "view"; id: string }
  | { kind: "create" }

export default function PersonasAdminPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const selectedId = searchParams.get("selected")
  const action = searchParams.get("action")

  // URL-synced sheet state.
  const sheetState: DetailSheetState = React.useMemo(() => {
    if (action === "new") return { kind: "create" }
    if (selectedId) return { kind: "view", id: selectedId }
    return { kind: "closed" }
  }, [action, selectedId])

  const [editingId, setEditingId] = React.useState<string | null>(null)
  const [archivingId, setArchivingId] = React.useState<string | null>(null)
  const [segment, setSegment] = React.useState<"todas" | "ativas" | "inativas" | "arquivadas">("todas")
  const [search, setSearch] = React.useState("")

  // Quando segment "arquivadas" e selecionado, precisamos incluir
  // arquivadas no fetch — DataTableShell filtra client-side em cima.
  const includeArchived = segment === "arquivadas"
  const personasQuery = usePersonas({ includeArchived })
  // Abrir detail query pra: (a) o id sendo editado (se houver), (b) o id
  // selecionado via URL ?selected=, ou (c) null (sheet fechada/create).
  const detailQuery = usePersonaDetail(
    editingId ?? (sheetState.kind === "view" ? sheetState.id : null),
  )

  const createMut = useCreatePersona()
  const updateMut = useUpdatePersona()
  const activateMut = useActivatePersonaVersion()
  const archiveMut = useArchivePersona()

  const personasData = React.useMemo(
    () => personasQuery.data ?? [],
    [personasQuery.data],
  )

  // ── URL helpers ───────────────────────────────────────────────────────
  const closeSheet = React.useCallback(() => {
    setEditingId(null)
    const params = new URLSearchParams(searchParams.toString())
    params.delete("selected")
    params.delete("action")
    router.replace(
      params.toString() ? `?${params.toString()}` : window.location.pathname,
      { scroll: false },
    )
  }, [router, searchParams])

  const openDetail = React.useCallback(
    (id: string) => {
      const params = new URLSearchParams(searchParams.toString())
      params.set("selected", id)
      params.delete("action")
      router.replace(`?${params.toString()}`, { scroll: false })
    },
    [router, searchParams],
  )

  const openCreate = React.useCallback(() => {
    const params = new URLSearchParams(searchParams.toString())
    params.set("action", "new")
    params.delete("selected")
    router.replace(`?${params.toString()}`, { scroll: false })
  }, [router, searchParams])

  // ── Handlers ──────────────────────────────────────────────────────────
  const handleCreate = async (values: PersonaCreateValues) => {
    try {
      const created = await createMut.mutateAsync(buildCreatePayload(values))
      toast.success(`Persona ${created.name}@v${created.version} criada.`)
      closeSheet()
      // Abrir detail da nova.
      setTimeout(() => openDetail(created.id), 50)
    } catch (e) {
      toast.error(`Falha ao criar: ${(e as Error).message}`)
    }
  }

  const handleEdit = async (values: PersonaUpdateValues) => {
    if (!editingId) return
    try {
      const updated = await updateMut.mutateAsync({
        id: editingId,
        payload: buildUpdatePayload(values),
      })
      toast.success(
        `Nova versao ${updated.name}@v${updated.version} criada (nao ativa).`,
      )
      setEditingId(null)
      openDetail(updated.id)
    } catch (e) {
      toast.error(`Falha ao salvar versao: ${(e as Error).message}`)
    }
  }

  const handleActivate = async (row: AIPersonaVersionInfo | AIPersonaDetail) => {
    try {
      await activateMut.mutateAsync({ name: row.name, versionId: row.id })
      toast.success(`${row.name}@v${row.version} ativada.`)
    } catch (e) {
      toast.error(`Falha ao ativar: ${(e as Error).message}`)
    }
  }

  const handleArchive = async () => {
    if (!archivingId) return
    try {
      const archived = await archiveMut.mutateAsync(archivingId)
      toast.success(`${archived.name}@v${archived.version} arquivada.`)
      setArchivingId(null)
    } catch (e) {
      toast.error(`Falha ao arquivar: ${(e as Error).message}`)
    }
  }

  // ── Columns ───────────────────────────────────────────────────────────
  const columns = React.useMemo<ColumnDef<AIPersonaVersionInfo>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Nome canonico",
        cell: ({ row }) => (
          <span className={cx(tableTokens.cellStrong, "font-mono")}>
            {row.original.name}
          </span>
        ),
      },
      {
        accessorKey: "version",
        header: "Versao",
        cell: ({ row }) => (
          <span className={tableTokens.cellSecondary}>
            v{row.original.version}
          </span>
        ),
      },
      {
        accessorKey: "display_name",
        header: "Display",
        cell: ({ row }) => (
          <span className={tableTokens.cellText}>
            {row.original.display_name}
          </span>
        ),
      },
      {
        accessorKey: "expertise_domains",
        header: "Dominios",
        cell: ({ row }) => (
          <DomainsCell domains={row.original.expertise_domains} />
        ),
      },
      {
        accessorKey: "is_active",
        header: "Status",
        cell: ({ row }) => (
          <StatusBadge
            active={row.original.is_active}
            archived={row.original.archived_at !== null}
          />
        ),
      },
      {
        accessorKey: "usage_count",
        header: "Uso",
        cell: ({ row }) => (
          <span className={tableTokens.cellNumber}>
            {row.original.usage_count}{" "}
            <span className={tableTokens.cellMuted}>
              {row.original.usage_count === 1 ? "agente" : "agentes"}
            </span>
          </span>
        ),
      },
      {
        accessorKey: "created_at",
        header: "Criada",
        cell: ({ row }) => (
          <span className={tableTokens.cellSecondary}>
            {formatDistanceToNow(parseISO(row.original.created_at), {
              addSuffix: true,
              locale: ptBR,
            })}
          </span>
        ),
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <div className="flex justify-end">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  className="size-7 p-0"
                  onClick={(e) => e.stopPropagation()}
                  aria-label="Mais acoes"
                >
                  <RiMoreLine className="size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  onClick={(e) => {
                    e.stopPropagation()
                    setEditingId(row.original.id)
                  }}
                >
                  <RiEdit2Line className="mr-2 size-4" />
                  Editar (cria nova versao)
                </DropdownMenuItem>
                {!row.original.is_active &&
                  row.original.archived_at === null && (
                    <DropdownMenuItem
                      onClick={(e) => {
                        e.stopPropagation()
                        void handleActivate(row.original)
                      }}
                    >
                      <RiCheckLine className="mr-2 size-4" />
                      Ativar
                    </DropdownMenuItem>
                  )}
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  disabled={row.original.is_active}
                  onClick={(e) => {
                    e.stopPropagation()
                    setArchivingId(row.original.id)
                  }}
                  className="text-red-600 dark:text-red-500"
                >
                  <RiArchive2Line className="mr-2 size-4" />
                  Arquivar
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  )

  // ── Render ────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
      <PageHeader
        title="Personas de IA"
        subtitle="Inteligencia Artificial · Administracao"
        info="Papel reutilizavel injetado no system prompt do agente (CLAUDE.md §19.12). Versionado: editar cria nova versao; ativar em 1 click sem deploy."
        actions={
          <Button
            variant="primary"
            onClick={openCreate}
            disabled={personasQuery.isLoading}
          >
            <RiAddLine className="mr-1 size-4" aria-hidden />
            Nova persona
          </Button>
        }
      />

      <DataTableShell<AIPersonaVersionInfo>
        data={personasData}
        columns={columns}
        loading={personasQuery.isLoading}
        error={personasQuery.error}
        onRetry={() => personasQuery.refetch()}
        search={{
          value: search,
          onChange: setSearch,
          placeholder: "Buscar por nome ou display...",
        }}
        segments={{
          value: segment,
          onChange: (v) => setSegment(v as typeof segment),
          options: [
            { value: "todas", label: "Todas", filter: () => true },
            {
              value: "ativas",
              label: "Ativas",
              filter: (p) => p.is_active && p.archived_at === null,
            },
            {
              value: "inativas",
              label: "Inativas",
              filter: (p) => !p.is_active && p.archived_at === null,
            },
            {
              value: "arquivadas",
              label: "Arquivadas",
              filter: (p) => p.archived_at !== null,
            },
          ],
        }}
        itemNoun={{ singular: "persona", plural: "personas" }}
        onRowClick={(row) => openDetail(row.id)}
        emptyState={{
          icon: RiUserStarLine,
          title: "Nenhuma persona cadastrada",
          description:
            "Crie a primeira persona para enriquecer o system prompt dos agentes.",
          action: (
            <Button variant="primary" onClick={openCreate}>
              <RiAddLine className="mr-1 size-4" aria-hidden />
              Cadastrar persona
            </Button>
          ),
        }}
      />

      {/* Detail sheet */}
      <DrillDownSheet
        open={sheetState.kind === "view" || editingId !== null}
        onClose={closeSheet}
        title={
          editingId
            ? "Editar persona"
            : detailQuery.data
              ? detailQuery.data.display_name
              : "Persona"
        }
        size="lg"
      >
        <div className="flex-1 overflow-y-auto p-6">
          {detailQuery.isLoading ? (
            <div className="py-8 text-center text-[13px] text-gray-500">
              Carregando...
            </div>
          ) : detailQuery.data ? (
            editingId === detailQuery.data.id ? (
              <PersonaEditForm
                persona={detailQuery.data}
                onSubmit={handleEdit}
                onCancel={() => setEditingId(null)}
                submitting={updateMut.isPending}
              />
            ) : (
              <PersonaDetailView
                persona={detailQuery.data}
                onEdit={() => setEditingId(detailQuery.data!.id)}
                onActivate={() => handleActivate(detailQuery.data!)}
                onArchive={() => setArchivingId(detailQuery.data!.id)}
                activating={activateMut.isPending}
              />
            )
          ) : null}
        </div>
      </DrillDownSheet>

      {/* Create sheet */}
      <DrillDownSheet
        open={sheetState.kind === "create"}
        onClose={closeSheet}
        title="Nova persona"
        size="lg"
      >
        <div className="flex-1 overflow-y-auto p-6">
          <PersonaCreateForm
            onSubmit={handleCreate}
            onCancel={closeSheet}
            submitting={createMut.isPending}
          />
        </div>
      </DrillDownSheet>

      {/* Archive confirmation */}
      <Dialog
        open={archivingId !== null}
        onOpenChange={(open) => !open && setArchivingId(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Arquivar persona</DialogTitle>
            <DialogDescription>
              A versao sera marcada como arquivada e nao podera mais ser
              ativada. Versoes ja ativas em outros agentes continuam
              funcionando normalmente.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="secondary"
              onClick={() => setArchivingId(null)}
              disabled={archiveMut.isPending}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={handleArchive}
              disabled={archiveMut.isPending}
            >
              Arquivar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Detail view
// ───────────────────────────────────────────────────────────────────────────

type DetailViewProps = {
  persona: AIPersonaDetail
  onEdit: () => void
  onActivate: () => void
  onArchive: () => void
  activating: boolean
}

function PersonaDetailView({
  persona,
  onEdit,
  onActivate,
  onArchive,
  activating,
}: DetailViewProps) {
  const isArchived = persona.archived_at !== null
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className={cx("font-mono text-[13px]", tableTokens.cellStrong)}>
          {persona.name}
        </span>
        <Badge variant="neutral" className={tableTokens.badge}>
          v{persona.version}
        </Badge>
        <StatusBadge active={persona.is_active} archived={isArchived} />
        <span className="ml-auto text-[12px] text-gray-500 dark:text-gray-400">
          <RiHistoryLine className="-mt-0.5 mr-1 inline size-3.5" />
          {formatDistanceToNow(parseISO(persona.created_at), {
            addSuffix: true,
            locale: ptBR,
          })}
        </span>
      </div>

      <section>
        <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Display
        </div>
        <div className={tableTokens.cellText}>{persona.display_name}</div>
      </section>

      {persona.expertise_domains && persona.expertise_domains.length > 0 && (
        <section>
          <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
            Dominios
          </div>
          <DomainsCell domains={persona.expertise_domains} />
        </section>
      )}

      <section>
        <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
          role_block (markdown — vai em &lt;persona&gt; do system prompt)
        </div>
        <pre
          className={cx(
            "max-h-[400px] overflow-auto rounded-md border p-3 font-mono text-[12px] leading-relaxed",
            "border-gray-200 bg-gray-50 text-gray-900",
            "dark:border-gray-800 dark:bg-gray-900 dark:text-gray-100",
          )}
        >
          {persona.role_block}
        </pre>
      </section>

      {persona.description && (
        <section>
          <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
            Descricao
          </div>
          <div className={tableTokens.cellSecondary}>{persona.description}</div>
        </section>
      )}

      <section>
        <div className="text-[12px] text-gray-500 dark:text-gray-400">
          {persona.usage_count}{" "}
          {persona.usage_count === 1
            ? "agente referencia esta versao"
            : "agentes referenciam esta versao"}
          .
        </div>
      </section>

      <Divider />

      <div className="flex flex-wrap items-center justify-end gap-2">
        {!isArchived && (
          <>
            <Button
              variant="secondary"
              onClick={onArchive}
              disabled={persona.is_active}
              title={
                persona.is_active
                  ? "Versao ativa nao pode ser arquivada"
                  : undefined
              }
            >
              <RiArchive2Line className="mr-1.5 size-4" />
              Arquivar
            </Button>
            {!persona.is_active && (
              <Button
                variant="secondary"
                onClick={onActivate}
                disabled={activating}
              >
                <RiCheckLine className="mr-1.5 size-4" />
                Ativar esta versao
              </Button>
            )}
            <Button onClick={onEdit}>
              <RiEdit2Line className="mr-1.5 size-4" />
              Editar (nova versao)
            </Button>
          </>
        )}
      </div>
    </div>
  )
}
