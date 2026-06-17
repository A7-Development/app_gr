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
import { RiCheckLine, RiExternalLinkLine, RiLoader4Line } from "@remixicon/react"
import { formatDistanceToNow, parseISO } from "date-fns"
import { ptBR } from "date-fns/locale"

import { Button } from "@/components/tremor/Button"
import type { AIAgentDefinitionVersionInfo } from "@/lib/api-client"
import {
  useActivateAgentDefinitionVersion,
  useAgentDefinitions,
  useArchiveAgentDefinition,
} from "@/lib/hooks/admin-ai"
import { cx } from "@/lib/utils"

import { StatusBadge } from "./AgentBadges"

const BASE_HREF = "/admin/ia/agents"

export function AgentVersionsPanel({
  agentName,
  currentId,
}: {
  agentName: string
  currentId: string
}) {
  const router = useRouter()
  // Inclui arquivadas — a aba de versoes mostra a familia inteira.
  const q = useAgentDefinitions({ includeArchived: true })
  const activateMut = useActivateAgentDefinitionVersion()
  const archiveMut = useArchiveAgentDefinition()

  const versions = React.useMemo(
    () =>
      (q.data ?? [])
        .filter((v) => v.name === agentName)
        .sort((a, b) => b.version - a.version),
    [q.data, agentName],
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

      <div className="overflow-x-auto rounded-md border border-gray-200 dark:border-gray-800">
        <table className="w-full text-[13px]">
          <thead className="bg-gray-50 text-left text-[11px] uppercase tracking-wide text-gray-500 dark:bg-gray-900 dark:text-gray-400">
            <tr>
              <th className="px-3 py-2 font-medium">Versao</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Persona</th>
              <th className="px-3 py-2 font-medium">Prompt</th>
              <th className="px-3 py-2 font-medium">Modelo</th>
              <th className="px-3 py-2 font-medium">Criada</th>
              <th className="px-3 py-2 text-right font-medium">Acoes</th>
            </tr>
          </thead>
          <tbody>
            {versions.map((v) => {
              const isCurrent = v.id === currentId
              const isArchived = v.archived_at !== null
              return (
                <tr
                  key={v.id}
                  className={cx(
                    "border-t border-gray-100 dark:border-gray-800",
                    isCurrent && "bg-blue-50/50 dark:bg-blue-500/5",
                  )}
                >
                  <td className="whitespace-nowrap px-3 py-2 font-mono tabular-nums text-gray-900 dark:text-gray-100">
                    v{v.version}
                    {isCurrent && (
                      <span className="ml-1.5 text-[10px] font-sans text-blue-600 dark:text-blue-400">
                        (aberta)
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <StatusBadge active={v.is_active} archived={isArchived} />
                  </td>
                  <td className="px-3 py-2 text-gray-700 dark:text-gray-300">
                    {v.persona_name ?? "—"}
                  </td>
                  <td className="px-3 py-2 font-mono text-[12px] text-gray-700 dark:text-gray-300">
                    {v.prompt_name}
                  </td>
                  <td className="px-3 py-2 font-mono text-[12px] text-gray-700 dark:text-gray-300">
                    {v.model ?? "default"}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-gray-500 dark:text-gray-400">
                    {formatDistanceToNow(parseISO(v.created_at), {
                      addSuffix: true,
                      locale: ptBR,
                    })}
                  </td>
                  <td className="px-3 py-2">
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
                          className="h-7 px-2 text-[12px] text-red-600 dark:text-red-500"
                          onClick={() => handleArchive(v)}
                          disabled={archiveMut.isPending}
                        >
                          Arquivar
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
