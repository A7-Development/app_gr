// src/app/(app)/admin/ia/agents/page.tsx
//
// Admin · IA · Modelos por Agente.
//
// MOTIVO (CLAUDE.md §7): nao usa pattern canonico (ListagemCrudInline,
// ListagemCrudCards) porque o numero de agentes e fixo (definido em codigo
// no CATALOG) — nao ha create/delete/criar-novo. So edicao do modelo de
// cada um. Reutilizamos `<DataTableShell>` (pattern de tabela CRUD) sem
// search/segments porque o conjunto e pequeno (~10 rows) e a "criacao" e
// substituida por dropdown inline em cada linha.
//
// Lista os specialist agents do CATALOG e permite ao mantenedor escolher,
// por agente, qual modelo Anthropic usar (etapa 1 — provider fixo). A
// mudanca e persistida em `agent_config` no DB; runtime le essa tabela
// (com fallback ao default do catalog) a cada execucao do agente.

"use client"

import * as React from "react"
import { toast } from "sonner"
import {
  RiBrainLine,
  RiCpuLine,
  RiImage2Line,
} from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/tremor/Select"
import {
  DataTableShell,
  DateCell,
  PageHeader,
} from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import type {
  AIAgentConfigRead,
  AIAgentModelOption,
} from "@/lib/api-client"
import {
  useAdminAgentModels,
  useAdminAgents,
  useUpdateAdminAgent,
} from "@/lib/hooks/admin-ai"
import { cx } from "@/lib/utils"

const NONE_VALUE = "__none__"

// ───────────────────────────────────────────────────────────────────────────
// Cells custom
// ───────────────────────────────────────────────────────────────────────────

function AgentNameCell({ agent }: { agent: AIAgentConfigRead }) {
  return (
    <div className="flex items-start gap-2">
      <span className="mt-0.5 text-gray-400 dark:text-gray-600">
        <RiBrainLine className="size-4" aria-hidden />
      </span>
      <div className="flex flex-col gap-0.5">
        <div className="flex items-center gap-1.5">
          <span className={tableTokens.cellStrong}>{agent.agent_name}</span>
          {agent.multimodal && (
            <span
              className="inline-flex items-center text-blue-500 dark:text-blue-400"
              title="Agente multimodal — aceita imagens/PDFs como entrada."
            >
              <RiImage2Line className="size-3.5" aria-hidden />
            </span>
          )}
        </div>
        <span className={tableTokens.cellSecondary}>{agent.description}</span>
        <span className={cx(tableTokens.cellMuted, "font-mono")}>
          prompt: {agent.prompt_name}
        </span>
      </div>
    </div>
  )
}

function ModelOptionLabel({ option }: { option: AIAgentModelOption }) {
  return (
    <span className="flex items-center gap-2">
      <span
        className={cx(
          tableTokens.badge,
          "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400 uppercase",
        )}
      >
        {option.tier}
      </span>
      <span>{option.label}</span>
    </span>
  )
}

function ModelSelectCell({
  value,
  models,
  onChange,
  disabled,
  placeholder,
  allowNone,
}: {
  value: string | null
  models: AIAgentModelOption[]
  onChange: (next: string | null) => void
  disabled: boolean
  placeholder: string
  allowNone: boolean
}) {
  return (
    <Select
      value={value ?? NONE_VALUE}
      onValueChange={(raw) => onChange(raw === NONE_VALUE ? null : raw)}
      disabled={disabled}
    >
      <SelectTrigger className="w-[210px]">
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {allowNone && (
          <SelectItem value={NONE_VALUE}>
            <span className="text-gray-500 dark:text-gray-400">
              Sem fallback
            </span>
          </SelectItem>
        )}
        {models.map((m) => (
          <SelectItem key={m.id} value={m.id}>
            <ModelOptionLabel option={m} />
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

function SourceBadge({ source }: { source: AIAgentConfigRead["source"] }) {
  if (source === "db_override") {
    return (
      <span
        className={cx(
          tableTokens.badge,
          "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300",
        )}
      >
        Customizado
      </span>
    )
  }
  return (
    <span
      className={cx(
        tableTokens.badge,
        "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
      )}
      title="Usando o valor padrao definido no codigo (CATALOG)."
    >
      Padrao
    </span>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Page
// ───────────────────────────────────────────────────────────────────────────

const col = createColumnHelper<AIAgentConfigRead>()

export default function AdminAgentsPage() {
  const agentsQuery = useAdminAgents()
  const modelsQuery = useAdminAgentModels()
  const updateMut = useUpdateAdminAgent()

  const agents = agentsQuery.data ?? []
  const models = modelsQuery.data ?? []

  const [pendingAgent, setPendingAgent] = React.useState<string | null>(null)

  const handleUpdate = React.useCallback(
    async (
      agent: AIAgentConfigRead,
      payload: { model: string; fallback_model: string | null },
    ) => {
      setPendingAgent(agent.agent_name)
      try {
        await updateMut.mutateAsync({
          agentName: agent.agent_name,
          payload,
        })
        toast.success(`${agent.agent_name}: modelo atualizado.`)
      } catch (err) {
        toast.error(
          err instanceof Error
            ? err.message
            : `Falha ao atualizar ${agent.agent_name}.`,
        )
      } finally {
        setPendingAgent(null)
      }
    },
    [updateMut],
  )

  const columns = React.useMemo<ColumnDef<AIAgentConfigRead, unknown>[]>(
    () => [
      col.display({
        id: "agent",
        header: "Agente",
        size: 320,
        cell: ({ row }) => <AgentNameCell agent={row.original} />,
      }) as ColumnDef<AIAgentConfigRead, unknown>,
      col.display({
        id: "model",
        header: "Modelo principal",
        size: 230,
        cell: ({ row }) => {
          const agent = row.original
          return (
            <ModelSelectCell
              value={agent.model}
              models={models}
              disabled={pendingAgent === agent.agent_name}
              placeholder="Selecionar modelo"
              allowNone={false}
              onChange={(next) => {
                if (next === null || next === agent.model) return
                handleUpdate(agent, {
                  model: next,
                  fallback_model: agent.fallback_model,
                })
              }}
            />
          )
        },
      }) as ColumnDef<AIAgentConfigRead, unknown>,
      col.display({
        id: "fallback_model",
        header: "Fallback",
        size: 230,
        cell: ({ row }) => {
          const agent = row.original
          return (
            <ModelSelectCell
              value={agent.fallback_model}
              models={models}
              disabled={pendingAgent === agent.agent_name}
              placeholder="Sem fallback"
              allowNone
              onChange={(next) => {
                if (next === agent.fallback_model) return
                handleUpdate(agent, {
                  model: agent.model,
                  fallback_model: next,
                })
              }}
            />
          )
        },
      }) as ColumnDef<AIAgentConfigRead, unknown>,
      col.accessor("source", {
        header: "Configuracao",
        size: 130,
        cell: (info) => <SourceBadge source={info.getValue()} />,
      }) as ColumnDef<AIAgentConfigRead, unknown>,
      col.accessor("updated_at", {
        header: "Atualizado em",
        size: 130,
        cell: (info) => {
          const v = info.getValue()
          return v ? (
            <DateCell value={v} />
          ) : (
            <span className={tableTokens.cellMuted}>—</span>
          )
        },
      }) as ColumnDef<AIAgentConfigRead, unknown>,
    ],
    [models, pendingAgent, handleUpdate],
  )

  return (
    <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
      <PageHeader
        title="Modelos por Agente"
        info="Cada agente especialista pode usar um modelo Anthropic diferente. A mudanca afeta todas as proximas execucoes (workflows de credito, extracoes de documento, etc) sem deploy. Provider fixo em Anthropic na etapa 1; OpenAI vem na etapa 2."
        subtitle="Inteligencia Artificial · Administracao"
      />

      <DataTableShell<AIAgentConfigRead>
        data={agents}
        columns={columns}
        loading={agentsQuery.isLoading || modelsQuery.isLoading}
        error={agentsQuery.error ?? modelsQuery.error}
        onRetry={() => {
          agentsQuery.refetch()
          modelsQuery.refetch()
        }}
        itemNoun={{ singular: "agente", plural: "agentes" }}
        emptyState={{
          icon: RiCpuLine,
          title: "Nenhum agente registrado",
          description:
            "O CATALOG do backend esta vazio. Verifique app/shared/agents/catalog.py.",
        }}
      />
    </div>
  )
}
