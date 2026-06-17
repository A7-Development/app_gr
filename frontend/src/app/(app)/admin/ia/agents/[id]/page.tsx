// src/app/(app)/admin/ia/agents/[id]/page.tsx
//
// Cockpit de edicao de um agent_definition (CLAUDE.md §19.12).
// Promovido do DrillDownSheet para rota dedicada (decisao 2026-06-16):
// editar um agente ponta a ponta e "novo foco de trabalho" -> rota, nao
// drawer (docs/navegacao-aprofundamento.md). Pagina larga comporta abas +
// editor de instrucoes + (futuro) telemetria.
//
// Mostra a versao por padrao (read-only). "Editar" cria nova versao
// (imutavel) e navega para ela. Activate/Archive/Preview disponiveis aqui.

"use client"

import * as React from "react"
import { useParams, useRouter } from "next/navigation"
import Link from "next/link"
import { toast } from "sonner"
import { RiArrowLeftLine, RiLoader4Line } from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/tremor/Dialog"
import type { AIAgentDefinitionPreview } from "@/lib/api-client"
import {
  useActivateAgentDefinitionVersion,
  useAdminAgentModels,
  useAgentDefinitionDetail,
  useArchiveAgentDefinition,
  useExpertises,
  usePersonas,
  usePreviewAgentDefinition,
  usePrompts,
  useTools,
  useUpdateAgentDefinition,
} from "@/lib/hooks/admin-ai"
import {
  buildUpdatePayload,
  type AgentDefinitionUpdateValues,
} from "@/lib/schemas/ai-agent-definition-schema"
import { cx } from "@/lib/utils"

import { AgentEditForm } from "../_components/AgentForm"
import { AgentDetailView } from "../_components/AgentDetailView"
import { AgentPreviewDialog } from "../_components/AgentPreviewDialog"
import { AgentStatsPanel } from "../_components/AgentStatsPanel"
import { AgentVersionsPanel } from "../_components/AgentVersionsPanel"

const LIST_HREF = "/admin/ia/agents"

type CockpitTab = "config" | "versoes" | "uso"

export default function AgentCockpitPage() {
  const router = useRouter()
  const params = useParams<{ id: string }>()
  const id = params.id

  const [cockpitTab, setCockpitTab] = React.useState<CockpitTab>("config")
  const [editing, setEditing] = React.useState(false)
  const [archiving, setArchiving] = React.useState(false)
  const [previewing, setPreviewing] =
    React.useState<AIAgentDefinitionPreview | null>(null)

  const detailQuery = useAgentDefinitionDetail(id)
  const personasQuery = usePersonas()
  const expertisesQuery = useExpertises()
  const promptsQuery = usePrompts()
  const modelsQuery = useAdminAgentModels()
  const toolsQuery = useTools()

  const updateMut = useUpdateAgentDefinition()
  const activateMut = useActivateAgentDefinitionVersion()
  const archiveMut = useArchiveAgentDefinition()
  const previewMut = usePreviewAgentDefinition()

  const agent = detailQuery.data

  const handleEdit = async (values: AgentDefinitionUpdateValues) => {
    try {
      const updated = await updateMut.mutateAsync({
        id,
        payload: buildUpdatePayload(values),
      })
      toast.success(
        `Nova versao ${updated.name}@v${updated.version} criada (nao ativa).`,
      )
      setEditing(false)
      // Navega para a versao recem-criada.
      router.push(`${LIST_HREF}/${updated.id}`)
    } catch (e) {
      toast.error(`Falha ao salvar versao: ${(e as Error).message}`)
    }
  }

  const handleActivate = async () => {
    if (!agent) return
    try {
      await activateMut.mutateAsync({ name: agent.name, versionId: agent.id })
      toast.success(`${agent.name}@v${agent.version} ativado.`)
    } catch (e) {
      toast.error(`Falha ao ativar: ${(e as Error).message}`)
    }
  }

  const handleArchive = async () => {
    if (!agent) return
    try {
      const archived = await archiveMut.mutateAsync(agent.id)
      toast.success(`${archived.name}@v${archived.version} arquivado.`)
      setArchiving(false)
      router.push(LIST_HREF)
    } catch (e) {
      toast.error(`Falha ao arquivar: ${(e as Error).message}`)
    }
  }

  const handlePreview = async () => {
    if (!agent) return
    try {
      setPreviewing(await previewMut.mutateAsync(agent.id))
    } catch (e) {
      toast.error(`Falha ao gerar preview: ${(e as Error).message}`)
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-5 px-6 pt-5 pb-10">
      <Link
        href={LIST_HREF}
        className="flex w-fit items-center gap-1 text-[13px] font-medium text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
      >
        <RiArrowLeftLine className="size-4" aria-hidden />
        Voltar para agentes
      </Link>

      {detailQuery.isLoading ? (
        <div className="flex items-center gap-2 py-12 text-[13px] text-gray-500">
          <RiLoader4Line className="size-4 animate-spin" aria-hidden />
          Carregando agente...
        </div>
      ) : detailQuery.isError || !agent ? (
        <div className="rounded-md border border-gray-200 p-8 text-center dark:border-gray-800">
          <p className="text-[14px] font-medium text-gray-900 dark:text-gray-100">
            Agente nao encontrado
          </p>
          <p className="mt-1 text-[13px] text-gray-500">
            A versao pode ter sido removida.{" "}
            <Link href={LIST_HREF} className="text-blue-600 dark:text-blue-400">
              Voltar para a lista
            </Link>
            .
          </p>
        </div>
      ) : (
        <>
          {/* Abas do cockpit (L3): configuracao vs uso/telemetria */}
          <div
            role="tablist"
            className="flex gap-1 border-b border-gray-200 dark:border-gray-800"
          >
            {(
              [
                { id: "config", label: "Configuracao" },
                { id: "versoes", label: "Versoes" },
                { id: "uso", label: "Uso" },
              ] as const
            ).map((t) => {
              const isActive = cockpitTab === t.id
              return (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  onClick={() => setCockpitTab(t.id)}
                  className={cx(
                    "-mb-px border-b-2 px-3 py-2 text-[13px] font-medium transition-colors",
                    isActive
                      ? "border-blue-500 text-blue-700 dark:text-blue-300"
                      : "border-transparent text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200",
                  )}
                >
                  {t.label}
                </button>
              )
            })}
          </div>

          {cockpitTab === "config" ? (
            <div className="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-800 dark:bg-gray-950">
              <div className="mb-4 flex items-center justify-between">
                <h1 className="font-mono text-lg font-semibold text-gray-900 dark:text-gray-50">
                  {agent.name}
                </h1>
                {editing && (
                  <span className="text-[12px] text-gray-500 dark:text-gray-400">
                    editando · cria v{agent.version + 1}
                  </span>
                )}
              </div>

              {editing ? (
                <AgentEditForm
                  agent={agent}
                  personas={personasQuery.data ?? []}
                  expertises={expertisesQuery.data ?? []}
                  prompts={promptsQuery.data ?? []}
                  models={modelsQuery.data ?? []}
                  tools={toolsQuery.data ?? []}
                  onSubmit={handleEdit}
                  onCancel={() => setEditing(false)}
                  submitting={updateMut.isPending}
                />
              ) : (
                <AgentDetailView
                  agent={agent}
                  onEdit={() => setEditing(true)}
                  onActivate={handleActivate}
                  onArchive={() => setArchiving(true)}
                  onPreview={handlePreview}
                  activating={activateMut.isPending}
                  previewing={previewMut.isPending}
                />
              )}
            </div>
          ) : cockpitTab === "versoes" ? (
            <div className="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-800 dark:bg-gray-950">
              <AgentVersionsPanel agentName={agent.name} currentId={agent.id} />
            </div>
          ) : (
            <div className="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-800 dark:bg-gray-950">
              <AgentStatsPanel agentId={id} />
            </div>
          )}
        </>
      )}

      {/* Archive confirmation */}
      <Dialog open={archiving} onOpenChange={(open) => !open && setArchiving(false)}>
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
              onClick={() => setArchiving(false)}
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

      <AgentPreviewDialog
        preview={previewing}
        onClose={() => setPreviewing(null)}
      />
    </div>
  )
}
