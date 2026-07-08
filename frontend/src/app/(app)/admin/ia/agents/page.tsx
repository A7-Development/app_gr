// src/app/(app)/admin/ia/agents/page.tsx
//
// Admin · IA · Agents (DB-backed, F2.c.3, CLAUDE.md §19.12).
//
// Lista de agent_definitions. Editar/criar abrem o COCKPIT em rota dedicada
// (/admin/ia/agents/[id] e /new) — promovido do DrillDownSheet em 2026-06-16
// para comportar abas + editor de instrucoes + telemetria. Activate/Archive/
// Preview seguem como acoes rapidas direto da lista.

"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import {
  RiAddLine,
  RiBarChartBoxLine,
  RiCpuLine,
  RiDeleteBin6Line,
  RiEdit2Line,
  RiEyeLine,
  RiMoreLine,
} from "@remixicon/react"
import { type ColumnDef } from "@tanstack/react-table"

import { Button } from "@/components/tremor/Button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/tremor/Dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/tremor/DropdownMenu"
import { DataTableShell, PageHeader } from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import type {
  AIAgentDefinitionPreview,
  AIAgentDefinitionVersionInfo,
} from "@/lib/api-client"
import {
  useAgentDefinitions,
  useDeleteAgentFamily,
  usePreviewAgentDefinition,
} from "@/lib/hooks/admin-ai"
import { cx } from "@/lib/utils"

import { ModuleBadge, StatusBadge } from "./_components/AgentBadges"
import { AgentPreviewDialog } from "./_components/AgentPreviewDialog"

const BASE_HREF = "/admin/ia/agents"

export default function AgentsAdminPage() {
  const router = useRouter()

  // Agente (familia) a excluir — guarda a linha pra mostrar code/versoes no aviso.
  const [deleting, setDeleting] =
    React.useState<AIAgentDefinitionVersionInfo | null>(null)
  const [previewing, setPreviewing] =
    React.useState<AIAgentDefinitionPreview | null>(null)
  const [segment, setSegment] = React.useState<
    "todos" | "ativos" | "arquivados"
  >("todos")
  const [search, setSearch] = React.useState("")

  const includeArchived = segment === "arquivados" || segment === "todos"
  const agentsQuery = useAgentDefinitions({ includeArchived })

  const deleteFamilyMut = useDeleteAgentFamily()
  const previewMut = usePreviewAgentDefinition()

  const agentsData = React.useMemo(
    () => agentsQuery.data ?? [],
    [agentsQuery.data],
  )

  const openDetail = React.useCallback(
    (id: string) => router.push(`${BASE_HREF}/${id}`),
    [router],
  )
  const openCreate = React.useCallback(
    () => router.push(`${BASE_HREF}/new`),
    [router],
  )

  const handleDeleteFamily = async () => {
    if (!deleting) return
    try {
      await deleteFamilyMut.mutateAsync(deleting.id)
      toast.success(`Agente ${deleting.code} excluido.`)
      setDeleting(null)
    } catch (e) {
      toast.error(`Falha ao excluir: ${(e as Error).message}`)
    }
  }

  const handlePreview = async (id: string) => {
    try {
      setPreviewing(await previewMut.mutateAsync(id))
    } catch (e) {
      toast.error(`Falha ao gerar preview: ${(e as Error).message}`)
    }
  }

  const columns = React.useMemo<ColumnDef<AIAgentDefinitionVersionInfo>[]>(
    () => [
      {
        accessorKey: "code",
        header: "Codigo",
        cell: ({ row }) => (
          <span
            className={cx(tableTokens.badge, "font-mono bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300")}
            title="Codigo discreto do agente (rastreabilidade)"
          >
            {row.original.code}
          </span>
        ),
      },
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
            {row.original.version_count > 1 && (
              <span className={cx("ml-1", tableTokens.cellMuted)}>
                · {row.original.version_count} versoes
              </span>
            )}
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
          <span className={cx(tableTokens.cellSecondary, "font-mono")}>
            {row.original.prompt_name}
          </span>
        ),
      },
      {
        accessorKey: "model",
        header: "Modelo",
        cell: ({ row }) =>
          row.original.model ? (
            <span className={cx(tableTokens.cellSecondary, "font-mono")}>
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
                    openDetail(row.original.id)
                  }}
                >
                  <RiEdit2Line className="mr-2 size-4" />
                  Abrir cockpit
                </DropdownMenuItem>
                {/* Ativar/Arquivar sao por-versao -> vivem na aba Versoes do
                    cockpit. A lista lida com a familia (abrir / excluir). */}
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={(e) => {
                    e.stopPropagation()
                    setDeleting(row.original)
                  }}
                  className="text-red-600 dark:text-red-500"
                >
                  <RiDeleteBin6Line className="mr-2 size-4" />
                  Excluir agente
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

  return (
    <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
      <PageHeader
        title="Agentes de IA"
        subtitle="Inteligencia Artificial · Administracao"
        info="Catalogo central de agentes (CLAUDE.md §19.12). Cada agente compoe persona + expertises + prompt + modelo. Versionado: editar cria nova versao; ativar em 1 click sem deploy."
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              onClick={() => router.push(`${BASE_HREF}/uso`)}
            >
              <RiBarChartBoxLine className="mr-1 size-4" aria-hidden />
              Uso do catalogo
            </Button>
            <Button
              variant="primary"
              onClick={openCreate}
              disabled={agentsQuery.isLoading}
            >
              <RiAddLine className="mr-1 size-4" aria-hidden />
              Novo agente
            </Button>
          </div>
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
              filter: (a) => a.archived_at === null,
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

      {/* Excluir agente (familia inteira) */}
      <Dialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Excluir agente</DialogTitle>
            <DialogDescription>
              Exclui <b>{deleting?.code}</b> (<code>{deleting?.name}</code>) e
              suas {deleting?.version_count ?? 1} versao(es) — definitivo. Se o
              agente existir no codigo (CATALOG), volta a rodar pelo fallback; a
              tela que o usa nao quebra. Historico de uso e preservado.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="secondary"
              onClick={() => setDeleting(null)}
              disabled={deleteFamilyMut.isPending}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteFamily}
              disabled={deleteFamilyMut.isPending}
            >
              Excluir agente
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AgentPreviewDialog
        preview={previewing}
        onClose={() => setPreviewing(null)}
      />
    </div>
  )
}
