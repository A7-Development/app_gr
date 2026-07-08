"use client"

//
// AgentVersionsPanel — aba "Versoes" do cockpit.
//
// Governanca de versoes da familia (mesmo `name`): ver todas, qual esta
// ATIVA, e ativar/rollback em 1 clique (sem deploy) ou arquivar. O modelo
// ja e imutavel + active pointer — esta e a UI que faltava.
//
// Frontend-only: reusa a lista de agent_definitions (includeArchived) +
// os hooks de activate/archive. Nao precisa de endpoint novo.
//

import * as React from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import {
  RiCheckLine,
  RiDeleteBin6Line,
  RiExternalLinkLine,
  RiLoader4Line,
} from "@remixicon/react"
import type { ColumnDef } from "@tanstack/react-table"
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
import { DataTable } from "@/design-system/components/DataTable"
import { tableTokens } from "@/design-system/tokens/table"
import type { AIAgentDefinitionVersionInfo } from "@/lib/api-client"
import {
  useActivateAgentDefinitionVersion,
  useAgentVersions,
  useArchiveAgentDefinition,
  useDeleteAgentVersion,
} from "@/lib/hooks/admin-ai"
import { cx } from "@/lib/utils"

import { StatusBadge } from "./AgentBadges"

const BASE_HREF = "/admin/ia/agents"

export function AgentVersionsPanel({
  currentId,
}: {
  currentId: string
}) {
  const router = useRouter()
  // Endpoint dedicado: todas as versoes da familia (a lista principal colapsa).
  const q = useAgentVersions(currentId)
  const activateMut = useActivateAgentDefinitionVersion()
  const archiveMut = useArchiveAgentDefinition()
  const deleteMut = useDeleteAgentVersion()
  const [deleting, setDeleting] =
    React.useState<AIAgentDefinitionVersionInfo | null>(null)

  const versions = React.useMemo(
    () => (q.data ?? []).slice().sort((a, b) => b.version - a.version),
    [q.data],
  )

  const handleActivate = async (row: AIAgentDefinitionVersionInfo) => {
    try {
      await activateMut.mutateAsync({ name: row.name, versionId: row.id })
      toast.success(`${row.name}@v${row.version} ativado.`)
    } catch (e) {
      toast.error(`Falha ao ativar: ${(e as Error).message}`)
    }
  }

  const handleArchive = async (row: AIAgentDefinitionVersionInfo) => {
    try {
      await archiveMut.mutateAsync(row.id)
      toast.success(`${row.name}@v${row.version} arquivado.`)
    } catch (e) {
      toast.error(`Falha ao arquivar: ${(e as Error).message}`)
    }
  }

  const handleDelete = async () => {
    if (!deleting) return
    try {
      await deleteMut.mutateAsync(deleting.id)
      toast.success(`${deleting.name}@v${deleting.version} excluido.`)
      setDeleting(null)
    } catch (e) {
      toast.error(`Falha ao excluir: ${(e as Error).message}`)
    }
  }

  const columns = React.useMemo<
    ColumnDef<AIAgentDefinitionVersionInfo, unknown>[]
  >(
    () => [
      {
        id: "versao",
        header: "Versao",
        cell: ({ row }) => {
          const v = row.original
          const isCurrent = v.id === currentId
          return (
            <span className={cx(tableTokens.cellTextMono, "whitespace-nowrap")}>
              v{v.version}
              {isCurrent && (
                <span className={cx(tableTokens.cellSecondary, "ml-1.5 font-sans text-blue-600 dark:text-blue-400")}>
                  (aberta)
                </span>
              )}
            </span>
          )
        },
      },
      {
        id: "status",
        header: "Status",
        cell: ({ row }) => (
          <StatusBadge
            active={row.original.is_active}
            archived={row.original.archived_at !== null}
          />
        ),
      },
      {
        id: "persona",
        header: "Persona",
        cell: ({ row }) => (
          <span className={tableTokens.cellText}>
            {row.original.persona_name ?? "—"}
          </span>
        ),
      },
      {
        id: "prompt",
        header: "Prompt",
        cell: ({ row }) => (
          <span className={tableTokens.cellTextMono}>
            {row.original.prompt_name}
          </span>
        ),
      },
      {
        id: "modelo",
        header: "Modelo",
        cell: ({ row }) => (
          <span className={tableTokens.cellTextMono}>
            {row.original.model ?? "default"}
          </span>
        ),
      },
      {
        id: "criada",
        header: "Criada",
        cell: ({ row }) => (
          <span className={cx(tableTokens.cellSecondary, "whitespace-nowrap")}>
            {formatDistanceToNow(parseISO(row.original.created_at), {
              addSuffix: true,
              locale: ptBR,
            })}
          </span>
        ),
      },
      {
        id: "acoes",
        header: "Acoes",
        meta: { align: "right" },
        cell: ({ row }) => {
          const v = row.original
          const isCurrent = v.id === currentId
          const isArchived = v.archived_at !== null
          return (
            <div className="flex items-center justify-end gap-1.5">
              {!isCurrent && (
                <Button
                  variant="ghost"
                  className="h-7 px-2 text-[12px]"
                  onClick={() => router.push(`${BASE_HREF}/${v.id}`)}
                >
                  <RiExternalLinkLine className="mr-1 size-3.5" />
                  Abrir
                </Button>
              )}
              {!v.is_active && !isArchived && (
                <Button
                  variant="secondary"
                  className="h-7 px-2 text-[12px]"
                  onClick={() => handleActivate(v)}
                  disabled={activateMut.isPending}
                >
                  <RiCheckLine className="mr-1 size-3.5" />
                  Ativar
                </Button>
              )}
              {!v.is_active && !isArchived && (
                <Button
                  variant="ghost"
                  className="h-7 px-2 text-[12px]"
                  onClick={() => handleArchive(v)}
                  disabled={archiveMut.isPending}
                >
                  Arquivar
                </Button>
              )}
              {!v.is_active && (
                <Button
                  variant="ghost"
                  className="h-7 px-2 text-[12px] text-red-600 dark:text-red-500"
                  onClick={() => setDeleting(v)}
                  disabled={deleteMut.isPending}
                  aria-label="Excluir versao"
                >
                  <RiDeleteBin6Line className="size-3.5" />
                </Button>
              )}
            </div>
          )
        },
      },
    ],
    // handleActivate/handleArchive sao closures sobre mutateAsync (estavel);
    // re-criar a memo a cada render anularia o ganho — deps cobrem os flags
    // que mudam o disabled dos botoes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      currentId,
      router,
      activateMut.isPending,
      archiveMut.isPending,
      deleteMut.isPending,
    ],
  )

  if (q.isLoading) {
    return (
      <div className="flex items-center gap-2 py-10 text-[13px] text-gray-500">
        <RiLoader4Line className="size-4 animate-spin" aria-hidden />
        Carregando versoes...
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-[13px] text-gray-500 dark:text-gray-400">
        {versions.length} versao{versions.length === 1 ? "" : "es"} desta familia.
        Ativar troca a versao em producao em 1 clique (rollback sem deploy).
      </p>

      <DataTable<AIAgentDefinitionVersionInfo>
        data={versions}
        columns={columns}
        rowClassName={(v) =>
          v.id === currentId ? "bg-blue-50/50 dark:bg-blue-500/5" : ""
        }
      />

      {/* Excluir versao (hard-delete) */}
      <Dialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Excluir versao</DialogTitle>
            <DialogDescription>
              Exclui <b>{deleting?.name}@v{deleting?.version}</b> em definitivo.
              So versoes nao-ativas podem ser excluidas (ative outra antes, ou
              use &quot;Excluir agente&quot; na lista pra remover tudo).
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="secondary"
              onClick={() => setDeleting(null)}
              disabled={deleteMut.isPending}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteMut.isPending}
            >
              Excluir versao
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
