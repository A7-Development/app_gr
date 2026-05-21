// src/app/(app)/admin/ia/agents/page.tsx
//
// Admin · IA · Agents (DB-backed, F2.c.3, CLAUDE.md §19.12).
//
// Substitui a versao legada que mostrava apenas override de modelo via
// `agent_config`. Agora editor completo de agent_definition:
//   - Persona picker
//   - Expertises multi-picker
//   - Prompt task picker
//   - Model overrides (Opus/Sonnet/Haiku + temperature/max_tokens)
//   - Toggle cross_module
//   - Preview do system_text composto (XML — persona + expertise + task)
//
// Pattern: ListagemCrudInline canonico via DataTableShell.

"use client"

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { toast } from "sonner"
import {
  RiAddLine,
  RiArchive2Line,
  RiCheckLine,
  RiCpuLine,
  RiEdit2Line,
  RiEyeLine,
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
  AIAgentDefinitionDetail,
  AIAgentDefinitionPreview,
  AIAgentDefinitionVersionInfo,
} from "@/lib/api-client"
import {
  useActivateAgentDefinitionVersion,
  useAdminAgentModels,
  useAgentDefinitionDetail,
  useAgentDefinitions,
  useArchiveAgentDefinition,
  useCreateAgentDefinition,
  useExpertises,
  usePersonas,
  usePreviewAgentDefinition,
  usePrompts,
  useUpdateAgentDefinition,
} from "@/lib/hooks/admin-ai"
import {
  buildCreatePayload,
  buildUpdatePayload,
  type AgentDefinitionCreateValues,
  type AgentDefinitionUpdateValues,
} from "@/lib/schemas/ai-agent-definition-schema"
import { cx } from "@/lib/utils"

import { AgentCreateForm, AgentEditForm } from "./_components/AgentForm"

// ───────────────────────────────────────────────────────────────────────────
// Module badge (cor por modulo — espelha avatars de modulo §11.6)
// ───────────────────────────────────────────────────────────────────────────

const MODULE_TONES: Record<string, { bg: string; fg: string }> = {
  bi: {
    bg: "bg-gray-100 dark:bg-gray-800",
    fg: "text-gray-700 dark:text-gray-300",
  },
  cadastros: {
    bg: "bg-blue-50 dark:bg-blue-500/10",
    fg: "text-blue-700 dark:text-blue-300",
  },
  operacoes: {
    bg: "bg-emerald-50 dark:bg-emerald-500/10",
    fg: "text-emerald-700 dark:text-emerald-300",
  },
  credito: {
    bg: "bg-indigo-50 dark:bg-indigo-500/10",
    fg: "text-indigo-700 dark:text-indigo-300",
  },
  controladoria: {
    bg: "bg-teal-50 dark:bg-teal-500/10",
    fg: "text-teal-700 dark:text-teal-300",
  },
  risco: {
    bg: "bg-amber-50 dark:bg-amber-500/10",
    fg: "text-amber-700 dark:text-amber-300",
  },
  integracoes: {
    bg: "bg-red-50 dark:bg-red-500/10",
    fg: "text-red-700 dark:text-red-300",
  },
  laboratorio: {
    bg: "bg-violet-50 dark:bg-violet-500/10",
    fg: "text-violet-700 dark:text-violet-300",
  },
  admin: {
    bg: "bg-slate-50 dark:bg-slate-500/10",
    fg: "text-slate-700 dark:text-slate-300",
  },
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
        Arquivado
      </Badge>
    )
  }
  if (active) {
    return (
      <Badge variant="success" className={tableTokens.badge}>
        Ativo
      </Badge>
    )
  }
  return (
    <Badge variant="neutral" className={tableTokens.badge}>
      Inativo
    </Badge>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Page
// ───────────────────────────────────────────────────────────────────────────

type SheetState =
  | { kind: "closed" }
  | { kind: "view"; id: string }
  | { kind: "create" }

export default function AgentsAdminPage() {
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
  const [previewing, setPreviewing] = React.useState<AIAgentDefinitionPreview | null>(null)
  const [segment, setSegment] = React.useState<"todos" | "ativos" | "inativos" | "arquivados">("todos")
  const [search, setSearch] = React.useState("")

  const includeArchived = segment === "arquivados"
  const agentsQuery = useAgentDefinitions({ includeArchived })
  const detailQuery = useAgentDefinitionDetail(
    editingId ?? (sheetState.kind === "view" ? sheetState.id : null),
  )

  // Listas para pickers (filtradas dentro do AgentForm)
  const personasQuery = usePersonas()
  const expertisesQuery = useExpertises()
  const promptsQuery = usePrompts()
  const modelsQuery = useAdminAgentModels()

  const createMut = useCreateAgentDefinition()
  const updateMut = useUpdateAgentDefinition()
  const activateMut = useActivateAgentDefinitionVersion()
  const archiveMut = useArchiveAgentDefinition()
  const previewMut = usePreviewAgentDefinition()

  const agentsData = React.useMemo(
    () => agentsQuery.data ?? [],
    [agentsQuery.data],
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
  const handleCreate = async (values: AgentDefinitionCreateValues) => {
    try {
      const created = await createMut.mutateAsync(buildCreatePayload(values))
      toast.success(`Agente ${created.name}@v${created.version} criado.`)
      closeSheet()
      setTimeout(() => openDetail(created.id), 50)
    } catch (e) {
      toast.error(`Falha ao criar: ${(e as Error).message}`)
    }
  }

  const handleEdit = async (values: AgentDefinitionUpdateValues) => {
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
    row: AIAgentDefinitionVersionInfo | AIAgentDefinitionDetail,
  ) => {
    try {
      await activateMut.mutateAsync({ name: row.name, versionId: row.id })
      toast.success(`${row.name}@v${row.version} ativado.`)
    } catch (e) {
      toast.error(`Falha ao ativar: ${(e as Error).message}`)
    }
  }

  const handleArchive = async () => {
    if (!archivingId) return
    try {
      const archived = await archiveMut.mutateAsync(archivingId)
      toast.success(`${archived.name}@v${archived.version} arquivado.`)
      setArchivingId(null)
    } catch (e) {
      toast.error(`Falha ao arquivar: ${(e as Error).message}`)
    }
  }

  const handlePreview = async (id: string) => {
    try {
      const preview = await previewMut.mutateAsync(id)
      setPreviewing(preview)
    } catch (e) {
      toast.error(`Falha ao gerar preview: ${(e as Error).message}`)
    }
  }

  // ── Columns ───────────────────────────────────────────────────────────
  const columns = React.useMemo<ColumnDef<AIAgentDefinitionVersionInfo>[]>(
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
        accessorKey: "module",
        header: "Modulo",
        cell: ({ row }) => <ModuleBadge module={row.original.module} />,
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
        accessorKey: "persona_name",
        header: "Persona",
        cell: ({ row }) =>
          row.original.persona_name ? (
            <span className={tableTokens.cellText}>
              {row.original.persona_name}
            </span>
          ) : (
            <span className={tableTokens.cellMuted}>—</span>
          ),
      },
      {
        accessorKey: "expertise_count",
        header: "Expertises",
        cell: ({ row }) => (
          <span className={tableTokens.cellNumber}>
            {row.original.expertise_count}
          </span>
        ),
      },
      {
        accessorKey: "prompt_name",
        header: "Prompt",
        cell: ({ row }) => (
          <span className={cx(tableTokens.cellSecondary, "font-mono text-[12px]")}>
            {row.original.prompt_name}
          </span>
        ),
      },
      {
        accessorKey: "model",
        header: "Modelo",
        cell: ({ row }) =>
          row.original.model ? (
            <span className={cx(tableTokens.cellSecondary, "font-mono text-[12px]")}>
              {row.original.model}
            </span>
          ) : (
            <span className={tableTokens.cellMuted}>default</span>
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
                    void handlePreview(row.original.id)
                  }}
                >
                  <RiEyeLine className="mr-2 size-4" />
                  Preview system_text
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={(e) => {
                    e.stopPropagation()
                    setEditingId(row.original.id)
                  }}
                >
                  <RiEdit2Line className="mr-2 size-4" />
                  Editar (nova versao)
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
        title="Agentes de IA"
        subtitle="Inteligencia Artificial · Administracao"
        info="Catalogo central de agentes (CLAUDE.md §19.12). Cada agente compoe persona + expertises + prompt + modelo. Versionado: editar cria nova versao; ativar em 1 click sem deploy."
        actions={
          <Button
            variant="primary"
            onClick={openCreate}
            disabled={agentsQuery.isLoading}
          >
            <RiAddLine className="mr-1 size-4" aria-hidden />
            Novo agente
          </Button>
        }
      />

      <DataTableShell<AIAgentDefinitionVersionInfo>
        data={agentsData}
        columns={columns}
        loading={agentsQuery.isLoading}
        error={agentsQuery.error}
        onRetry={() => agentsQuery.refetch()}
        search={{
          value: search,
          onChange: setSearch,
          placeholder: "Buscar por nome, persona ou prompt...",
        }}
        segments={{
          value: segment,
          onChange: (v) => setSegment(v as typeof segment),
          options: [
            { value: "todos", label: "Todos", filter: () => true },
            {
              value: "ativos",
              label: "Ativos",
              filter: (a) => a.is_active && a.archived_at === null,
            },
            {
              value: "inativos",
              label: "Inativos",
              filter: (a) => !a.is_active && a.archived_at === null,
            },
            {
              value: "arquivados",
              label: "Arquivados",
              filter: (a) => a.archived_at !== null,
            },
          ],
        }}
        itemNoun={{ singular: "agente", plural: "agentes" }}
        onRowClick={(row) => openDetail(row.id)}
        emptyState={{
          icon: RiCpuLine,
          title: "Nenhum agente cadastrado",
          description:
            "Crie seu primeiro agente compondo persona + expertises + prompt.",
          action: (
            <Button variant="primary" onClick={openCreate}>
              <RiAddLine className="mr-1 size-4" aria-hidden />
              Cadastrar agente
            </Button>
          ),
        }}
      />

      {/* Detail/Edit sheet */}
      <DrillDownSheet
        open={sheetState.kind === "view" || editingId !== null}
        onClose={closeSheet}
        title={
          editingId
            ? "Editar agente"
            : detailQuery.data
              ? detailQuery.data.name
              : "Agente"
        }
        size="lg"
      >
        <div className="p-6">
          {detailQuery.isLoading ? (
            <div className="py-8 text-center text-[13px] text-gray-500">
              Carregando...
            </div>
          ) : detailQuery.data ? (
            editingId === detailQuery.data.id ? (
              <AgentEditForm
                agent={detailQuery.data}
                personas={personasQuery.data ?? []}
                expertises={expertisesQuery.data ?? []}
                prompts={promptsQuery.data ?? []}
                models={modelsQuery.data ?? []}
                onSubmit={handleEdit}
                onCancel={() => setEditingId(null)}
                submitting={updateMut.isPending}
              />
            ) : (
              <AgentDetailView
                agent={detailQuery.data}
                onEdit={() => setEditingId(detailQuery.data!.id)}
                onActivate={() => handleActivate(detailQuery.data!)}
                onArchive={() => setArchivingId(detailQuery.data!.id)}
                onPreview={() => handlePreview(detailQuery.data!.id)}
                activating={activateMut.isPending}
                previewing={previewMut.isPending}
              />
            )
          ) : null}
        </div>
      </DrillDownSheet>

      {/* Create sheet */}
      <DrillDownSheet
        open={sheetState.kind === "create"}
        onClose={closeSheet}
        title="Novo agente"
        size="lg"
      >
        <div className="p-6">
          <AgentCreateForm
            personas={personasQuery.data ?? []}
            expertises={expertisesQuery.data ?? []}
            prompts={promptsQuery.data ?? []}
            models={modelsQuery.data ?? []}
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
            <DialogTitle>Arquivar agente</DialogTitle>
            <DialogDescription>
              A versao sera marcada como arquivada e nao podera mais ser
              ativada.
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

      {/* Preview dialog */}
      <Dialog
        open={previewing !== null}
        onOpenChange={(open) => !open && setPreviewing(null)}
      >
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>
              Preview system_text — {previewing?.name}@v{previewing?.version}
            </DialogTitle>
            <DialogDescription>
              Bloco XML composto (persona + expertises + task) que e enviado ao
              LLM em runtime. Cache breakpoint Anthropic aplicado apos este
              system_text.
            </DialogDescription>
          </DialogHeader>
          {previewing && (
            <div className="flex flex-col gap-3">
              <div className="flex flex-wrap gap-1 text-[12px]">
                <Badge variant="neutral" className={tableTokens.badge}>
                  {previewing.model}
                </Badge>
                {previewing.fallback_model && (
                  <Badge variant="neutral" className={tableTokens.badge}>
                    fallback: {previewing.fallback_model}
                  </Badge>
                )}
                {previewing.temperature !== null && (
                  <Badge variant="neutral" className={tableTokens.badge}>
                    T={previewing.temperature}
                  </Badge>
                )}
                {previewing.max_tokens !== null && (
                  <Badge variant="neutral" className={tableTokens.badge}>
                    max={previewing.max_tokens}
                  </Badge>
                )}
              </div>
              <pre
                className={cx(
                  "max-h-[500px] overflow-auto rounded-md border p-3 font-mono text-[12px] leading-relaxed",
                  "border-gray-200 bg-gray-50 text-gray-900",
                  "dark:border-gray-800 dark:bg-gray-900 dark:text-gray-100",
                )}
              >
                {previewing.system_text}
              </pre>
              <div className="text-[12px] text-gray-500 dark:text-gray-400">
                {previewing.persona_full_id && (
                  <>
                    persona: <code>{previewing.persona_full_id}</code> ·{" "}
                  </>
                )}
                {previewing.expertise_full_ids.length > 0 && (
                  <>
                    expertises:{" "}
                    {previewing.expertise_full_ids.map((id) => (
                      <code key={id} className="mr-1">
                        {id}
                      </code>
                    ))}
                    ·{" "}
                  </>
                )}
                prompt: <code>{previewing.prompt_full_id}</code>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="secondary" onClick={() => setPreviewing(null)}>
              Fechar
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
  agent: AIAgentDefinitionDetail
  onEdit: () => void
  onActivate: () => void
  onArchive: () => void
  onPreview: () => void
  activating: boolean
  previewing: boolean
}

function AgentDetailView({
  agent,
  onEdit,
  onActivate,
  onArchive,
  onPreview,
  activating,
  previewing,
}: DetailViewProps) {
  const isArchived = agent.archived_at !== null
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className={cx("font-mono text-[13px]", tableTokens.cellStrong)}>
          {agent.name}
        </span>
        <Badge variant="neutral" className={tableTokens.badge}>
          v{agent.version}
        </Badge>
        <ModuleBadge module={agent.module} />
        <StatusBadge active={agent.is_active} archived={isArchived} />
        {agent.cross_module && (
          <Badge variant="warning" className={tableTokens.badge}>
            cross-module
          </Badge>
        )}
        <span className="ml-auto text-[12px] text-gray-500 dark:text-gray-400">
          <RiHistoryLine className="-mt-0.5 mr-1 inline size-3.5" />
          {formatDistanceToNow(parseISO(agent.created_at), {
            addSuffix: true,
            locale: ptBR,
          })}
        </span>
      </div>

      <section>
        <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Persona
        </div>
        {agent.persona ? (
          <div className={tableTokens.cellText}>
            {agent.persona.display_name}{" "}
            <span className={cx(tableTokens.cellMuted, "font-mono ml-1")}>
              {agent.persona.name}@v{agent.persona.version}
            </span>
          </div>
        ) : (
          <span className={tableTokens.cellMuted}>(sem persona)</span>
        )}
      </section>

      <section>
        <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Expertises ({agent.expertises.length})
        </div>
        {agent.expertises.length === 0 ? (
          <span className={tableTokens.cellMuted}>(sem expertises)</span>
        ) : (
          <ul className="flex flex-col gap-1">
            {agent.expertises.map((e) => (
              <li key={e.id} className="text-[13px]">
                <span className="text-gray-900 dark:text-gray-100">
                  {e.display_name}
                </span>{" "}
                <span className={cx(tableTokens.cellMuted, "font-mono ml-1")}>
                  {e.name}@v{e.version} · {e.domain}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Prompt task
        </div>
        <div className={cx(tableTokens.cellText, "font-mono")}>
          {agent.prompt_name}
          {agent.prompt && (
            <span className={cx(tableTokens.cellMuted, "ml-2")}>
              @v{agent.prompt.version}
            </span>
          )}
        </div>
      </section>

      <Divider />

      <section>
        <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Modelo (override)
        </div>
        <div className="grid grid-cols-2 gap-3 text-[13px]">
          <div>
            <span className={tableTokens.cellMuted}>Modelo: </span>
            {agent.model ? (
              <code className="font-mono text-[12px]">{agent.model}</code>
            ) : (
              <span className={tableTokens.cellMuted}>default do prompt</span>
            )}
          </div>
          <div>
            <span className={tableTokens.cellMuted}>Fallback: </span>
            {agent.fallback_model ? (
              <code className="font-mono text-[12px]">{agent.fallback_model}</code>
            ) : (
              <span className={tableTokens.cellMuted}>default</span>
            )}
          </div>
          <div>
            <span className={tableTokens.cellMuted}>Temperature: </span>
            {agent.temperature ?? "default"}
          </div>
          <div>
            <span className={tableTokens.cellMuted}>Max tokens: </span>
            {agent.max_tokens ?? "default"}
          </div>
        </div>
      </section>

      <Divider />

      <div className="flex flex-wrap items-center justify-end gap-2">
        <Button variant="secondary" onClick={onPreview} disabled={previewing}>
          <RiEyeLine className="mr-1.5 size-4" />
          Preview system_text
        </Button>
        {!isArchived && (
          <>
            <Button
              variant="secondary"
              onClick={onArchive}
              disabled={agent.is_active}
              title={
                agent.is_active
                  ? "Versao ativa nao pode ser arquivada"
                  : undefined
              }
            >
              <RiArchive2Line className="mr-1.5 size-4" />
              Arquivar
            </Button>
            {!agent.is_active && (
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
