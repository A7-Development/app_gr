// src/app/(app)/admin/ia/prompts/page.tsx
//
// Admin · IA · Prompts (DB-backed, CLAUDE.md sec 19.4 v2).
//
// Lista os prompts versionados em DB. Permite:
//  - Cadastrar nova familia (vira v1)
//  - Editar prompt (sempre cria nova versao — base e imutavel)
//  - Ativar uma versao (rollback de 1 click)
//  - Arquivar versao inativa
//  - Preview com contexto fake (sem chamar LLM)
//
// Acessivel apenas a usuarios do tenant mantenedor — backend protege com
// `require_system_maintainer` (HTTP 403).

"use client"

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { toast } from "sonner"
import {
  RiAddLine,
  RiArchive2Line,
  RiArrowRightSLine,
  RiBookOpenLine,
  RiCheckLine,
  RiEdit2Line,
  RiEyeLine,
  RiHistoryLine,
  RiMoreLine,
} from "@remixicon/react"
import { formatDistanceToNow, parseISO } from "date-fns"
import { ptBR } from "date-fns/locale"

import { Button } from "@/components/tremor/Button"
import { Card } from "@/components/tremor/Card"
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
  DrillDownSheet,
  EmptyState,
  ErrorState,
  FilterSearch,
  PageHeader,
  SegmentSwitch,
} from "@/design-system/components"
import type { AIPromptDetail, AIPromptVersionInfo } from "@/lib/api-client"
import {
  useActivatePromptVersion,
  useArchivePrompt,
  useCreatePrompt,
  usePromptDetail,
  usePrompts,
  useUpdatePrompt,
} from "@/lib/hooks/admin-ai"
import {
  buildUpdatePayload,
  type PromptCreateValues,
  type PromptUpdateValues,
} from "@/lib/schemas/ai-prompt-schema"
import { cx } from "@/lib/utils"

import { PromptCreateForm, PromptEditForm } from "./_components/PromptForm"

// ───────────────────────────────────────────────────────────────────────────
// Cells / badges
// ───────────────────────────────────────────────────────────────────────────

const CATEGORY_TONES: Record<string, { bg: string; fg: string; dot: string }> = {
  chat:           { bg: "bg-violet-50 dark:bg-violet-500/10",  fg: "text-violet-700 dark:text-violet-300",   dot: "bg-violet-500"  },
  insight:        { bg: "bg-emerald-50 dark:bg-emerald-500/10", fg: "text-emerald-700 dark:text-emerald-300", dot: "bg-emerald-500" },
  summary:        { bg: "bg-teal-50 dark:bg-teal-500/10",       fg: "text-teal-700 dark:text-teal-300",       dot: "bg-teal-500"    },
  system:         { bg: "bg-amber-50 dark:bg-amber-500/10",     fg: "text-amber-700 dark:text-amber-300",     dot: "bg-amber-500"   },
  classification: { bg: "bg-indigo-50 dark:bg-indigo-500/10",   fg: "text-indigo-700 dark:text-indigo-300",   dot: "bg-indigo-500"  },
}

function CategoryBadge({ name }: { name: string }) {
  const cat = name.split(".")[0] ?? "unknown"
  const tone = CATEGORY_TONES[cat] ?? {
    bg: "bg-gray-100 dark:bg-gray-800",
    fg: "text-gray-700 dark:text-gray-300",
    dot: "bg-gray-400",
  }
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-sm px-1.5 py-0.5 text-[11px] font-medium",
        tone.bg,
        tone.fg,
      )}
    >
      <span aria-hidden className={cx("size-1.5 rounded-full", tone.dot)} />
      {cat}
    </span>
  )
}

function ActiveBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-sm bg-blue-50 px-1.5 py-0.5 text-[11px] font-medium text-blue-700 dark:bg-blue-500/10 dark:text-blue-300">
      <RiCheckLine className="size-3" aria-hidden />
      Ativa
    </span>
  )
}

function ArchivedBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-sm bg-gray-100 px-1.5 py-0.5 text-[11px] font-medium text-gray-500 dark:bg-gray-800 dark:text-gray-400">
      Arquivada
    </span>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Page
// ───────────────────────────────────────────────────────────────────────────

type Segment = "todas" | "ativas" | "arquivadas"

type FamilyGroup = {
  name: string
  versions: AIPromptVersionInfo[]
  active: AIPromptVersionInfo | null
  // Quando filtrada por busca/segment, este array vira o subset visivel.
  visibleVersions: AIPromptVersionInfo[]
}

function groupByName(rows: AIPromptVersionInfo[]): FamilyGroup[] {
  const map = new Map<string, FamilyGroup>()
  for (const r of rows) {
    let g = map.get(r.name)
    if (!g) {
      g = { name: r.name, versions: [], active: null, visibleVersions: [] }
      map.set(r.name, g)
    }
    g.versions.push(r)
    if (r.is_active) g.active = r
  }
  // Ordena versoes mais recentes primeiro.
  const groups = Array.from(map.values())
  for (const g of groups) {
    g.versions.sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    )
    g.visibleVersions = g.versions
  }
  return groups.sort((a, b) => a.name.localeCompare(b.name))
}

export default function PromptsPage() {
  const router = useRouter()
  const sp = useSearchParams()

  const action = sp.get("action") // "new" | null
  const editId = sp.get("edit") // uuid
  const viewId = sp.get("view") // uuid (drawer de visualizacao read-only com preview)

  const promptsQuery = usePrompts({ includeArchived: true })
  const editQuery = usePromptDetail(editId)
  const viewQuery = usePromptDetail(viewId)

  const createMut = useCreatePrompt()
  const updateMut = useUpdatePrompt()
  const activateMut = useActivatePromptVersion()
  const archiveMut = useArchivePrompt()

  const data = promptsQuery.data ?? []

  // ── Filtros ─────────────────────────────────────────────────────────────
  const [search, setSearch] = React.useState("")
  const [segment, setSegment] = React.useState<Segment>("todas")

  const segmentFiltered = React.useMemo(() => {
    if (segment === "ativas") return data.filter((r) => r.is_active)
    if (segment === "arquivadas") return data.filter((r) => r.archived_at !== null)
    return data
  }, [data, segment])

  const searchFiltered = React.useMemo(() => {
    const term = search.trim().toLowerCase()
    if (!term) return segmentFiltered
    return segmentFiltered.filter((r) =>
      [r.name, r.description, r.model, r.version]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(term)),
    )
  }, [segmentFiltered, search])

  const groups = React.useMemo(() => groupByName(searchFiltered), [searchFiltered])

  const counts = React.useMemo(
    () => ({
      todas: data.length,
      ativas: data.filter((r) => r.is_active).length,
      arquivadas: data.filter((r) => r.archived_at !== null).length,
    }),
    [data],
  )

  // ── Confirmacao destrutiva (archive) ────────────────────────────────────
  const [pendingArchive, setPendingArchive] = React.useState<AIPromptVersionInfo | null>(null)

  // ── Navigation helpers ──────────────────────────────────────────────────
  const setQuery = React.useCallback(
    (next: { action?: string | null; edit?: string | null; view?: string | null }) => {
      const params = new URLSearchParams(sp.toString())
      const apply = (key: string, value: string | null | undefined) => {
        if (value === undefined) return
        if (value) params.set(key, value)
        else params.delete(key)
      }
      apply("action", next.action)
      apply("edit", next.edit)
      apply("view", next.view)
      const qs = params.toString()
      router.push(qs ? `?${qs}` : "?")
    },
    [router, sp],
  )

  const openNew = React.useCallback(
    () => setQuery({ action: "new", edit: null, view: null }),
    [setQuery],
  )
  const openEdit = React.useCallback(
    (id: string) => setQuery({ action: null, edit: id, view: null }),
    [setQuery],
  )
  const openView = React.useCallback(
    (id: string) => setQuery({ action: null, edit: null, view: id }),
    [setQuery],
  )
  const closeSheet = React.useCallback(
    () => setQuery({ action: null, edit: null, view: null }),
    [setQuery],
  )

  // ── Submit handlers ─────────────────────────────────────────────────────
  const handleCreate = React.useCallback(
    async (values: PromptCreateValues) => {
      try {
        const created = await createMut.mutateAsync({
          name: values.name.trim(),
          system_text: values.system_text,
          user_context_template: values.user_context_template?.trim() || undefined,
          assistant_prime: values.assistant_prime?.trim() || undefined,
          model: values.model.trim(),
          fallback_model: values.fallback_model?.trim() || undefined,
          temperature: values.temperature,
          max_tokens: values.max_tokens,
          cache_strategy: values.cache_strategy,
          description: values.description?.trim() || undefined,
        })
        toast.success(`Prompt '${created.name}' criado (v1, ja ativo).`)
        closeSheet()
      } catch (err) {
        toast.error(
          err instanceof Error ? err.message : "Falha ao criar prompt.",
        )
      }
    },
    [createMut, closeSheet],
  )

  const handleEdit = React.useCallback(
    async (values: PromptUpdateValues) => {
      if (!editQuery.data) return
      try {
        const created = await updateMut.mutateAsync({
          id: editQuery.data.id,
          payload: buildUpdatePayload(values),
        })
        toast.success(
          `Nova versao ${created.version} criada para '${created.name}'. Ative-a para usar em producao.`,
        )
        closeSheet()
      } catch (err) {
        toast.error(
          err instanceof Error ? err.message : "Falha ao editar prompt.",
        )
      }
    },
    [updateMut, editQuery.data, closeSheet],
  )

  const handleActivate = React.useCallback(
    async (row: AIPromptVersionInfo) => {
      try {
        await activateMut.mutateAsync({ name: row.name, versionId: row.id })
        toast.success(`Versao ${row.version} ativada para '${row.name}'.`)
      } catch (err) {
        toast.error(
          err instanceof Error ? err.message : "Falha ao ativar versao.",
        )
      }
    },
    [activateMut],
  )

  const handleArchive = React.useCallback(async () => {
    if (!pendingArchive) return
    try {
      await archiveMut.mutateAsync(pendingArchive.id)
      toast.success(
        `${pendingArchive.name} ${pendingArchive.version} arquivada.`,
      )
      setPendingArchive(null)
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Falha ao arquivar.",
      )
    }
  }, [archiveMut, pendingArchive])

  // ── Render ──────────────────────────────────────────────────────────────
  const isEmpty = !promptsQuery.isLoading && !promptsQuery.error && data.length === 0

  return (
    <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
      <PageHeader
        title="Prompts LLM"
        info="Prompts versionados em DB. Toda edicao cria nova versao (audit trail preservado). Ativar uma versao = 1 click, sem deploy."
        subtitle="Inteligencia Artificial · Administracao"
        actions={
          <Button
            variant="primary"
            onClick={openNew}
            disabled={promptsQuery.isLoading}
          >
            <RiAddLine className="mr-1 size-4" aria-hidden />
            Novo prompt
          </Button>
        }
      />

      {promptsQuery.error ? (
        <ErrorState
          title="Falha ao carregar prompts"
          description={
            promptsQuery.error instanceof Error
              ? promptsQuery.error.message
              : "Verifique sua conexao e tente novamente."
          }
          action={
            <Button variant="secondary" onClick={() => promptsQuery.refetch()}>
              Tentar novamente
            </Button>
          }
        />
      ) : isEmpty ? (
        <EmptyState
          icon={RiBookOpenLine}
          title="Nenhum prompt cadastrado"
          description="Cadastre o primeiro prompt para liberar IA aos tenants."
          action={
            <Button variant="primary" onClick={openNew}>
              <RiAddLine className="mr-1 size-4" aria-hidden />
              Novo prompt
            </Button>
          }
        />
      ) : (
        <Card className="flex flex-col gap-3 p-3">
          {/* Filtros */}
          <div className="flex flex-wrap items-center gap-2">
            <FilterSearch
              value={search}
              onChange={(e) => setSearch(e.currentTarget.value)}
              onClear={() => setSearch("")}
              placeholder="Buscar por nome, modelo ou descricao..."
            />
            <SegmentSwitch
              options={[
                { value: "todas",      label: "Todas",      count: counts.todas },
                { value: "ativas",     label: "Ativas",     count: counts.ativas },
                { value: "arquivadas", label: "Arquivadas", count: counts.arquivadas },
              ]}
              value={segment}
              onChange={setSegment}
            />
            <span
              className="ml-auto text-[11px] tabular-nums text-gray-500 dark:text-gray-400"
              aria-live="polite"
            >
              {groups.length === 0
                ? "Nenhum prompt"
                : `${groups.length} ${groups.length === 1 ? "familia" : "familias"} · ${searchFiltered.length} ${searchFiltered.length === 1 ? "versao" : "versoes"}`}
            </span>
          </div>

          {groups.length === 0 ? (
            <div className="py-12 text-center text-sm text-gray-500 dark:text-gray-400">
              Nenhum resultado para esses filtros.
              <Button
                variant="ghost"
                onClick={() => {
                  setSearch("")
                  setSegment("todas")
                }}
                className="ml-2"
              >
                Limpar filtros
              </Button>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {groups.map((g) => (
                <FamilyCard
                  key={g.name}
                  group={g}
                  onView={openView}
                  onEdit={openEdit}
                  onActivate={handleActivate}
                  onArchive={(row) => setPendingArchive(row)}
                  busyActivate={activateMut.isPending}
                  busyArchive={archiveMut.isPending}
                />
              ))}
            </div>
          )}
        </Card>
      )}

      {/* Drawer: Novo prompt */}
      <DrillDownSheet
        open={action === "new"}
        onClose={closeSheet}
        title="Novo prompt"
        size="lg"
      >
        <div className="p-6">
          <PromptCreateForm
            submitting={createMut.isPending}
            onSubmit={handleCreate}
            onCancel={closeSheet}
          />
        </div>
      </DrillDownSheet>

      {/* Drawer: Editar prompt (cria nova versao) */}
      <DrillDownSheet
        open={editId !== null}
        onClose={closeSheet}
        title={editQuery.data ? `Editar · ${editQuery.data.name}` : "Carregando..."}
        size="lg"
      >
        {editQuery.data && (
          <div className="p-6">
            <PromptEditForm
              initial={editQuery.data}
              submitting={updateMut.isPending}
              onSubmit={handleEdit}
              onCancel={closeSheet}
            />
          </div>
        )}
      </DrillDownSheet>

      {/* Drawer: Visualizar versao (read-only) */}
      <DrillDownSheet
        open={viewId !== null}
        onClose={closeSheet}
        title={
          viewQuery.data
            ? `${viewQuery.data.name} ${viewQuery.data.version}`
            : "Carregando..."
        }
        size="lg"
      >
        {viewQuery.data && <PromptDetailView prompt={viewQuery.data} />}
      </DrillDownSheet>

      {/* Confirmacao destrutiva — arquivar */}
      <Dialog
        open={pendingArchive !== null}
        onOpenChange={(open) => !open && setPendingArchive(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Arquivar versao</DialogTitle>
            <DialogDescription>
              {pendingArchive && (
                <>
                  Esta acao arquiva a versao{" "}
                  <span className="font-mono text-gray-900 dark:text-gray-50">
                    {pendingArchive.version}
                  </span>{" "}
                  de{" "}
                  <span className="font-mono text-gray-900 dark:text-gray-50">
                    {pendingArchive.name}
                  </span>
                  . Versoes arquivadas nao podem ser ativadas, mas o conteudo e
                  preservado para auditoria. Para reverter, use o endpoint de
                  desarquivamento (em breve).
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <Divider />
          <DialogFooter>
            <Button
              variant="secondary"
              onClick={() => setPendingArchive(null)}
              disabled={archiveMut.isPending}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={handleArchive}
              disabled={archiveMut.isPending}
            >
              <RiArchive2Line className="mr-1.5 size-4" aria-hidden />
              Arquivar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// FamilyCard — agrupa um nome + suas versoes
// ───────────────────────────────────────────────────────────────────────────

function FamilyCard({
  group,
  onView,
  onEdit,
  onActivate,
  onArchive,
  busyActivate,
  busyArchive,
}: {
  group: FamilyGroup
  onView: (id: string) => void
  onEdit: (id: string) => void
  onActivate: (row: AIPromptVersionInfo) => void
  onArchive: (row: AIPromptVersionInfo) => void
  busyActivate: boolean
  busyArchive: boolean
}) {
  const [expanded, setExpanded] = React.useState(false)
  const oldVersions = group.visibleVersions.filter((v) => !v.is_active)
  const activeVersion = group.active

  return (
    <div className="rounded border border-gray-200 dark:border-gray-800">
      {/* Cabecalho da familia */}
      <div className="flex items-start gap-3 px-3 py-2">
        <CategoryBadge name={group.name} />
        <div className="flex flex-1 flex-col gap-0.5 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm text-gray-900 dark:text-gray-100">
              {group.name}
            </span>
            <span className="text-[11px] text-gray-400 dark:text-gray-600">
              {group.versions.length}{" "}
              {group.versions.length === 1 ? "versao" : "versoes"}
            </span>
          </div>
          {activeVersion?.description && (
            <p className="truncate text-xs text-gray-500 dark:text-gray-400">
              {activeVersion.description}
            </p>
          )}
        </div>
      </div>

      <Divider className="my-0" />

      {/* Versao ativa */}
      {activeVersion && (
        <VersionRow
          row={activeVersion}
          onView={onView}
          onEdit={onEdit}
          onActivate={onActivate}
          onArchive={onArchive}
          busyActivate={busyActivate}
          busyArchive={busyArchive}
        />
      )}

      {/* Versoes anteriores (collapsable) */}
      {oldVersions.length > 0 && (
        <>
          <Divider className="my-0" />
          <button
            type="button"
            onClick={() => setExpanded((e) => !e)}
            className={cx(
              "flex w-full items-center gap-1 px-3 py-1.5 text-[11px] text-gray-500 transition-colors",
              "hover:bg-gray-50 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-900 dark:hover:text-gray-200",
            )}
          >
            <RiArrowRightSLine
              className={cx(
                "size-3.5 transition-transform",
                expanded && "rotate-90",
              )}
              aria-hidden
            />
            <RiHistoryLine className="size-3.5" aria-hidden />
            <span>
              {expanded ? "Ocultar" : "Mostrar"} {oldVersions.length}{" "}
              {oldVersions.length === 1 ? "versao anterior" : "versoes anteriores"}
            </span>
          </button>

          {expanded &&
            oldVersions.map((v) => (
              <React.Fragment key={v.id}>
                <Divider className="my-0" />
                <VersionRow
                  row={v}
                  onView={onView}
                  onEdit={onEdit}
                  onActivate={onActivate}
                  onArchive={onArchive}
                  busyActivate={busyActivate}
                  busyArchive={busyArchive}
                />
              </React.Fragment>
            ))}
        </>
      )}
    </div>
  )
}

function VersionRow({
  row,
  onView,
  onEdit,
  onActivate,
  onArchive,
  busyActivate,
  busyArchive,
}: {
  row: AIPromptVersionInfo
  onView: (id: string) => void
  onEdit: (id: string) => void
  onActivate: (row: AIPromptVersionInfo) => void
  onArchive: (row: AIPromptVersionInfo) => void
  busyActivate: boolean
  busyArchive: boolean
}) {
  const created = formatDistanceToNow(parseISO(row.created_at), {
    addSuffix: true,
    locale: ptBR,
  })
  return (
    <div
      className={cx(
        "flex items-center gap-3 px-3 py-2",
        "hover:bg-gray-50 dark:hover:bg-gray-900",
      )}
    >
      <span className="font-mono text-xs text-gray-900 dark:text-gray-100">
        {row.version}
      </span>
      {row.is_active && <ActiveBadge />}
      {row.archived_at && <ArchivedBadge />}

      <span className="text-[11px] text-gray-500 dark:text-gray-400">
        {row.model}
        {" · "}
        T={row.temperature.toFixed(2)}
        {" · "}
        max={row.max_tokens.toLocaleString("pt-BR")}
      </span>

      <span
        className="ml-auto text-[11px] text-gray-400 dark:text-gray-600"
        title={row.created_at}
      >
        Criada {created}
      </span>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            className="size-7 p-0"
            aria-label={`Acoes de ${row.name} ${row.version}`}
          >
            <RiMoreLine className="size-4" aria-hidden />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" sideOffset={4}>
          <DropdownMenuItem onSelect={() => onView(row.id)}>
            <RiEyeLine className="mr-2 size-4" aria-hidden />
            Visualizar
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => onEdit(row.id)}>
            <RiEdit2Line className="mr-2 size-4" aria-hidden />
            Editar (cria nova versao)
          </DropdownMenuItem>
          {!row.is_active && !row.archived_at && (
            <DropdownMenuItem
              onSelect={() => onActivate(row)}
              disabled={busyActivate}
            >
              <RiCheckLine className="mr-2 size-4" aria-hidden />
              Ativar esta versao
            </DropdownMenuItem>
          )}
          {!row.is_active && !row.archived_at && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onSelect={() => onArchive(row)}
                disabled={busyArchive}
                className="text-red-600 focus:text-red-700 dark:text-red-400 dark:focus:text-red-300"
              >
                <RiArchive2Line className="mr-2 size-4" aria-hidden />
                Arquivar
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// PromptDetailView — drawer read-only com texto + preview
// ───────────────────────────────────────────────────────────────────────────

function PromptDetailView({ prompt }: { prompt: AIPromptDetail }) {
  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <CategoryBadge name={prompt.name} />
          <span className="font-mono text-sm text-gray-900 dark:text-gray-100">
            {prompt.name}
          </span>
          <span className="font-mono text-xs text-gray-500 dark:text-gray-400">
            {prompt.version}
          </span>
          {prompt.is_active && <ActiveBadge />}
          {prompt.archived_at && <ArchivedBadge />}
        </div>
        {prompt.description && (
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {prompt.description}
          </p>
        )}
      </div>

      <Divider />

      <div className="grid grid-cols-2 gap-4 text-xs">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-gray-500">
            Modelo
          </div>
          <div className="font-mono text-gray-900 dark:text-gray-100">
            {prompt.model}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-gray-500">
            Fallback
          </div>
          <div className="font-mono text-gray-900 dark:text-gray-100">
            {prompt.fallback_model ?? "—"}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-gray-500">
            Temperature
          </div>
          <div className="font-mono text-gray-900 dark:text-gray-100">
            {prompt.temperature.toFixed(2)}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-gray-500">
            Max tokens
          </div>
          <div className="font-mono text-gray-900 dark:text-gray-100">
            {prompt.max_tokens.toLocaleString("pt-BR")}
          </div>
        </div>
        <div className="col-span-2">
          <div className="text-[10px] uppercase tracking-wider text-gray-500">
            Cache strategy
          </div>
          <div className="font-mono text-gray-900 dark:text-gray-100">
            {prompt.cache_strategy}
          </div>
        </div>
      </div>

      <Divider />

      <PromptTextSection title="System text" text={prompt.system_text} />
      {prompt.user_context_template && (
        <PromptTextSection
          title="User context template"
          text={prompt.user_context_template}
        />
      )}
      {prompt.assistant_prime && (
        <PromptTextSection
          title="Assistant prime"
          text={prompt.assistant_prime}
        />
      )}
    </div>
  )
}

function PromptTextSection({ title, text }: { title: string; text: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
          {title}
        </span>
        <span className="text-[10px] text-gray-400 dark:text-gray-600">
          {text.length.toLocaleString("pt-BR")} chars
        </span>
      </div>
      <pre className="overflow-x-auto rounded border border-gray-200 bg-gray-50 p-3 font-mono text-[11px] leading-relaxed text-gray-900 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-100 whitespace-pre-wrap">
        {text}
      </pre>
    </div>
  )
}
