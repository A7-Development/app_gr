// src/app/(app)/admin/ia/expertises/page.tsx
//
// Admin · IA · Expertises (DB-backed, F2.c.2, CLAUDE.md §19.12).
//
// Lista as expertises (knowledge packs) de agentes versionadas em DB.
// Permite:
//  - Cadastrar nova familia (vira v1 e e ativada)
//  - Editar (sempre cria nova versao — base e imutavel)
//  - Ativar uma versao (rollback de 1 click)
//  - Arquivar versao inativa (soft-delete)
//
// Pattern espelha /admin/ia/personas — mesmo CRUD versionado.

"use client"

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { toast } from "sonner"
import {
  RiAddLine,
  RiArchive2Line,
  RiBookOpenLine,
  RiCheckLine,
  RiEdit2Line,
  RiExternalLinkLine,
  RiHistoryLine,
  RiMoreLine,
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
import type {
  AIExpertiseDetail,
  AIExpertiseVersionInfo,
} from "@/lib/api-client"
import {
  useActivateExpertiseVersion,
  useArchiveExpertise,
  useCreateExpertise,
  useExpertiseDetail,
  useExpertises,
  useUpdateExpertise,
} from "@/lib/hooks/admin-ai"
import {
  buildCreatePayload,
  buildUpdatePayload,
  type ExpertiseCreateValues,
  type ExpertiseUpdateValues,
} from "@/lib/schemas/ai-expertise-schema"
import { cx } from "@/lib/utils"

import { ExpertiseCreateForm, ExpertiseEditForm } from "./_components/ExpertiseForm"

// ───────────────────────────────────────────────────────────────────────────
// Domain badge (cor por dominio)
// ───────────────────────────────────────────────────────────────────────────

const DOMAIN_TONES: Record<
  string,
  { bg: string; fg: string }
> = {
  contabilidade: {
    bg: "bg-teal-50 dark:bg-teal-500/10",
    fg: "text-teal-700 dark:text-teal-300",
  },
  credito: {
    bg: "bg-indigo-50 dark:bg-indigo-500/10",
    fg: "text-indigo-700 dark:text-indigo-300",
  },
  risco: {
    bg: "bg-amber-50 dark:bg-amber-500/10",
    fg: "text-amber-700 dark:text-amber-300",
  },
  regulatorio: {
    bg: "bg-violet-50 dark:bg-violet-500/10",
    fg: "text-violet-700 dark:text-violet-300",
  },
  mercado: {
    bg: "bg-blue-50 dark:bg-blue-500/10",
    fg: "text-blue-700 dark:text-blue-300",
  },
}

function DomainBadge({ domain }: { domain: string }) {
  const tone = DOMAIN_TONES[domain] ?? {
    bg: "bg-gray-100 dark:bg-gray-800",
    fg: "text-gray-700 dark:text-gray-300",
  }
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-sm px-1.5 py-0.5 text-[11px] font-medium",
        tone.bg,
        tone.fg,
      )}
    >
      {domain}
    </span>
  )
}

function StatusBadge({
  active,
  archived,
}: {
  active: boolean
  archived: boolean
}) {
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

// ───────────────────────────────────────────────────────────────────────────
// Page
// ───────────────────────────────────────────────────────────────────────────

// sheetState.kind=="edit" nunca e retornado pelo useMemo (edit e controlado
// por `editingId` separado, nao via URL). Removido do union pra TS strict.
type SheetState =
  | { kind: "closed" }
  | { kind: "view"; id: string }
  | { kind: "create" }

export default function ExpertisesAdminPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const selectedId = searchParams.get("selected")
  const action = searchParams.get("action")

  const sheetState: SheetState = React.useMemo(() => {
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
  const expertisesQuery = useExpertises({ includeArchived })
  // Abrir detail query pra: (a) o id sendo editado (se houver), (b) o id
  // selecionado via URL ?selected=, ou (c) null (sheet fechada/create).
  const detailQuery = useExpertiseDetail(
    editingId ?? (sheetState.kind === "view" ? sheetState.id : null),
  )

  const createMut = useCreateExpertise()
  const updateMut = useUpdateExpertise()
  const activateMut = useActivateExpertiseVersion()
  const archiveMut = useArchiveExpertise()

  const expertisesData = React.useMemo(
    () => expertisesQuery.data ?? [],
    [expertisesQuery.data],
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
  const handleCreate = async (values: ExpertiseCreateValues) => {
    try {
      const created = await createMut.mutateAsync(buildCreatePayload(values))
      toast.success(`Expertise ${created.name}@v${created.version} criada.`)
      closeSheet()
      setTimeout(() => openDetail(created.id), 50)
    } catch (e) {
      toast.error(`Falha ao criar: ${(e as Error).message}`)
    }
  }

  const handleEdit = async (values: ExpertiseUpdateValues) => {
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

  const handleActivate = async (
    row: AIExpertiseVersionInfo | AIExpertiseDetail,
  ) => {
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
  const columns = React.useMemo<ColumnDef<AIExpertiseVersionInfo>[]>(
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
        accessorKey: "domain",
        header: "Dominio",
        cell: ({ row }) => <DomainBadge domain={row.original.domain} />,
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
        title="Expertises de IA"
        subtitle="Inteligencia Artificial · Administracao"
        info="Knowledge pack injetado no system prompt do agente (CLAUDE.md §19.12). Define O QUE o agente sabe — embasamento teorico aplicado, vocabulario tecnico, normas. Versionado: editar cria nova versao."
        actions={
          <Button
            variant="primary"
            onClick={openCreate}
            disabled={expertisesQuery.isLoading}
          >
            <RiAddLine className="mr-1 size-4" aria-hidden />
            Nova expertise
          </Button>
        }
      />

      <DataTableShell<AIExpertiseVersionInfo>
        data={expertisesData}
        columns={columns}
        loading={expertisesQuery.isLoading}
        error={expertisesQuery.error}
        onRetry={() => expertisesQuery.refetch()}
        search={{
          value: search,
          onChange: setSearch,
          placeholder: "Buscar por nome, display ou dominio...",
        }}
        segments={{
          value: segment,
          onChange: (v) => setSegment(v as typeof segment),
          options: [
            { value: "todas", label: "Todas", filter: () => true },
            {
              value: "ativas",
              label: "Ativas",
              filter: (e) => e.is_active && e.archived_at === null,
            },
            {
              value: "inativas",
              label: "Inativas",
              filter: (e) => !e.is_active && e.archived_at === null,
            },
            {
              value: "arquivadas",
              label: "Arquivadas",
              filter: (e) => e.archived_at !== null,
            },
          ],
        }}
        itemNoun={{ singular: "expertise", plural: "expertises" }}
        onRowClick={(row) => openDetail(row.id)}
        emptyState={{
          icon: RiBookOpenLine,
          title: "Nenhuma expertise cadastrada",
          description:
            "Crie a primeira expertise (knowledge pack) para enriquecer o system prompt dos agentes.",
          action: (
            <Button variant="primary" onClick={openCreate}>
              <RiAddLine className="mr-1 size-4" aria-hidden />
              Cadastrar expertise
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
            ? "Editar expertise"
            : detailQuery.data
              ? detailQuery.data.display_name
              : "Expertise"
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
              <ExpertiseEditForm
                expertise={detailQuery.data}
                onSubmit={handleEdit}
                onCancel={() => setEditingId(null)}
                submitting={updateMut.isPending}
              />
            ) : (
              <ExpertiseDetailView
                expertise={detailQuery.data}
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
        title="Nova expertise"
        size="lg"
      >
        <div className="flex-1 overflow-y-auto p-6">
          <ExpertiseCreateForm
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
            <DialogTitle>Arquivar expertise</DialogTitle>
            <DialogDescription>
              A versao sera marcada como arquivada e nao podera mais ser
              ativada. Versoes ja ativas em outros agentes continuam funcionando.
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
  expertise: AIExpertiseDetail
  onEdit: () => void
  onActivate: () => void
  onArchive: () => void
  activating: boolean
}

function ExpertiseDetailView({
  expertise,
  onEdit,
  onActivate,
  onArchive,
  activating,
}: DetailViewProps) {
  const isArchived = expertise.archived_at !== null
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className={cx("font-mono text-[13px]", tableTokens.cellStrong)}>
          {expertise.name}
        </span>
        <Badge variant="neutral" className={tableTokens.badge}>
          v{expertise.version}
        </Badge>
        <DomainBadge domain={expertise.domain} />
        <StatusBadge active={expertise.is_active} archived={isArchived} />
        <span className="ml-auto text-[12px] text-gray-500 dark:text-gray-400">
          <RiHistoryLine className="-mt-0.5 mr-1 inline size-3.5" />
          {formatDistanceToNow(parseISO(expertise.created_at), {
            addSuffix: true,
            locale: ptBR,
          })}
        </span>
      </div>

      <section>
        <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Display
        </div>
        <div className={tableTokens.cellText}>{expertise.display_name}</div>
      </section>

      <section>
        <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
          knowledge_text (markdown — vai em &lt;expertise&gt; do system prompt)
        </div>
        <pre
          className={cx(
            "max-h-[500px] overflow-auto rounded-md border p-3 font-mono text-[12px] leading-relaxed",
            "border-gray-200 bg-gray-50 text-gray-900",
            "dark:border-gray-800 dark:bg-gray-900 dark:text-gray-100",
          )}
        >
          {expertise.knowledge_text}
        </pre>
      </section>

      {expertise.reference_urls && expertise.reference_urls.length > 0 && (
        <section>
          <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
            Referencias
          </div>
          <ul className="flex flex-col gap-1.5">
            {expertise.reference_urls.map((r, i) => (
              <li
                key={`${r.url}-${i}`}
                className="flex items-start gap-2 text-[13px]"
              >
                <RiExternalLinkLine className="mt-0.5 size-3.5 shrink-0 text-gray-400" />
                <a
                  href={r.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-700 hover:underline dark:text-blue-300"
                >
                  {r.label}
                </a>
                {r.kind && (
                  <span className={cx(tableTokens.cellMuted, "ml-1")}>
                    · {r.kind}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <div className="text-[12px] text-gray-500 dark:text-gray-400">
          {expertise.usage_count}{" "}
          {expertise.usage_count === 1
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
              disabled={expertise.is_active}
              title={
                expertise.is_active
                  ? "Versao ativa nao pode ser arquivada"
                  : undefined
              }
            >
              <RiArchive2Line className="mr-1.5 size-4" />
              Arquivar
            </Button>
            {!expertise.is_active && (
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
