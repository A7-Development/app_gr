// src/app/(app)/admin/ia/agents/new/page.tsx
//
// Cockpit de criacao de agent_definition (vira v1, ativado). Rota dedicada
// (promovida do DrillDownSheet, decisao 2026-06-16). Ao criar, navega para
// o cockpit da nova versao.

"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { toast } from "sonner"
import { RiArrowLeftLine } from "@remixicon/react"

import {
  useAdminAgentModels,
  useCreateAgentDefinition,
  useExpertises,
  usePersonas,
  usePrompts,
  useTools,
} from "@/lib/hooks/admin-ai"
import {
  buildCreatePayload,
  type AgentDefinitionCreateValues,
} from "@/lib/schemas/ai-agent-definition-schema"

import { AgentCreateForm } from "../_components/AgentForm"

const LIST_HREF = "/admin/ia/agents"

export default function AgentCreatePage() {
  const router = useRouter()

  const personasQuery = usePersonas()
  const expertisesQuery = useExpertises()
  const promptsQuery = usePrompts()
  const modelsQuery = useAdminAgentModels()
  const toolsQuery = useTools()

  const createMut = useCreateAgentDefinition()

  const handleCreate = async (values: AgentDefinitionCreateValues) => {
    try {
      const created = await createMut.mutateAsync(buildCreatePayload(values))
      toast.success(`Agente ${created.name}@v${created.version} criado.`)
      router.push(`${LIST_HREF}/${created.id}`)
    } catch (e) {
      toast.error(`Falha ao criar: ${(e as Error).message}`)
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

      <div className="rounded-lg border border-gray-200 bg-white p-6 dark:border-gray-800 dark:bg-gray-950">
        <div className="mb-1 text-lg font-semibold text-gray-900 dark:text-gray-50">
          Novo agente
        </div>
        <p className="mb-4 text-[13px] text-gray-500 dark:text-gray-400">
          Componha persona + expertises + prompt task + modelo. Vira v1 e e
          ativado automaticamente.
        </p>

        <AgentCreateForm
          personas={personasQuery.data ?? []}
          expertises={expertisesQuery.data ?? []}
          prompts={promptsQuery.data ?? []}
          models={modelsQuery.data ?? []}
          tools={toolsQuery.data ?? []}
          onSubmit={handleCreate}
          onCancel={() => router.push(LIST_HREF)}
          submitting={createMut.isPending}
        />
      </div>
    </div>
  )
}
