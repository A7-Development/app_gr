"use client"

//
// AgentStatsPanel — aba "Uso" do cockpit (Fatia B).
//
// Telemetria REAL de uso, agregada de `agent_analysis_run` por nome do
// agente (cross-tenant, visao do system maintainer). Read-only.
//
// Escopo honesto (§7.3): so mostra o que e mensuravel de verdade —
// execucoes, tokens, custo, erros, duracao. Nao inventa "ROI" (juizo
// qualitativo, nao computavel) nem limites por agente (nao existem no DB).
//

import * as React from "react"
import {
  RiCheckLine,
  RiCloseLine,
  RiErrorWarningLine,
  RiLoader4Line,
} from "@remixicon/react"
import type { ColumnDef } from "@tanstack/react-table"
import { formatDistanceToNow, parseISO } from "date-fns"
import { ptBR } from "date-fns/locale"

import { DataTable } from "@/design-system/components/DataTable"
import { DenseTable } from "@/design-system/components/DenseTable"
import { tableTokens } from "@/design-system/tokens/table"
import { useAgentDefinitionStats } from "@/lib/hooks/admin-ai"
import type { AIAgentRunRecent } from "@/lib/api-client"
import { cx } from "@/lib/utils"

const brl = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
})
const num = new Intl.NumberFormat("pt-BR")

function fmtBRL(v: number): string {
  return brl.format(v)
}
function fmtInt(v: number): string {
  return num.format(v)
}
function fmtDateTime(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

function KpiTile({
  label,
  value,
  sub,
}: {
  label: string
  value: string
  sub?: string
}) {
  return (
    <div className="rounded-md border border-gray-200 p-3 dark:border-gray-800">
      <div className="text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
        {label}
      </div>
      <div className="mt-1 text-[22px] font-semibold tabular-nums text-gray-900 dark:text-gray-50">
        {value}
      </div>
      {sub && (
        <div className="mt-0.5 text-[12px] text-gray-500 dark:text-gray-400">
          {sub}
        </div>
      )}
    </div>
  )
}

function StatusPill({ status }: { status: string }) {
  if (status === "success") {
    return (
      <span className="inline-flex items-center gap-1 text-[12px] text-emerald-700 dark:text-emerald-400">
        <RiCheckLine className="size-3.5" aria-hidden /> ok
      </span>
    )
  }
  if (status === "error") {
    return (
      <span className="inline-flex items-center gap-1 text-[12px] text-red-600 dark:text-red-400">
        <RiCloseLine className="size-3.5" aria-hidden /> erro
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-[12px] text-amber-600 dark:text-amber-400">
      <RiErrorWarningLine className="size-3.5" aria-hidden /> {status}
    </span>
  )
}

const recentRunsColumns: ColumnDef<AIAgentRunRecent, unknown>[] = [
  {
    id: "quando",
    header: "Quando",
    cell: ({ row }) => (
      <span className={cx(tableTokens.cellText, "whitespace-nowrap")}>
        {fmtDateTime(row.original.triggered_at)}
      </span>
    ),
  },
  {
    id: "versao",
    header: "Versao",
    cell: ({ row }) => (
      <span className={tableTokens.cellNumber}>v{row.original.version}</span>
    ),
  },
  {
    id: "modelo",
    header: "Modelo",
    cell: ({ row }) => (
      <span className={tableTokens.cellTextMono}>{row.original.model_used}</span>
    ),
  },
  {
    id: "status",
    header: "Status",
    cell: ({ row }) => <StatusPill status={row.original.status} />,
  },
  {
    id: "tokens",
    header: "Tokens (in/out)",
    meta: { align: "right" },
    cell: ({ row }) => (
      <span className={cx(tableTokens.cellNumber, "block text-right")}>
        {fmtInt(row.original.tokens_input)} / {fmtInt(row.original.tokens_output)}
      </span>
    ),
  },
  {
    id: "custo",
    header: "Custo",
    meta: { align: "right" },
    cell: ({ row }) => (
      <span className={cx(tableTokens.cellNumber, "block text-right")}>
        {row.original.cost_brl != null ? fmtBRL(row.original.cost_brl) : "—"}
      </span>
    ),
  },
  {
    id: "duracao",
    header: "Duracao",
    meta: { align: "right" },
    cell: ({ row }) => (
      <span className={cx(tableTokens.cellNumberSecondary, "block text-right")}>
        {row.original.duration_ms != null
          ? `${fmtInt(row.original.duration_ms)} ms`
          : "—"}
      </span>
    ),
  },
]

export function AgentStatsPanel({ agentId }: { agentId: string }) {
  const q = useAgentDefinitionStats(agentId)

  if (q.isLoading) {
    return (
      <div className="flex items-center gap-2 py-10 text-[13px] text-gray-500">
        <RiLoader4Line className="size-4 animate-spin" aria-hidden />
        Carregando uso...
      </div>
    )
  }
  if (q.isError || !q.data) {
    return (
      <div className="rounded-md border border-gray-200 p-6 text-center text-[13px] text-gray-500 dark:border-gray-800">
        Falha ao carregar a telemetria de uso.
      </div>
    )
  }

  const s = q.data
  const successRate =
    s.total_runs > 0 ? Math.round((s.runs_success / s.total_runs) * 100) : 0
  const tokensTotal =
    s.tokens_input + s.tokens_output + s.tokens_cache_read + s.tokens_cache_creation

  if (s.total_runs === 0) {
    return (
      <div className="rounded-md border border-dashed border-gray-300 p-8 text-center dark:border-gray-700">
        <p className="text-[14px] font-medium text-gray-900 dark:text-gray-100">
          Nenhuma execucao registrada
        </p>
        <p className="mt-1 text-[13px] text-gray-500 dark:text-gray-400">
          Este agente ainda nao rodou (ou as execucoes nao passaram pelo cache
          de analise). Assim que ele for usado, uso e custo aparecem aqui.
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-5">
      {/* KPIs */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <KpiTile
          label="Execucoes"
          value={fmtInt(s.total_runs)}
          sub={`${fmtInt(s.window_runs)} nos ultimos ${s.window_days}d`}
        />
        <KpiTile
          label="Taxa de sucesso"
          value={`${successRate}%`}
          sub={
            s.runs_error > 0
              ? `${fmtInt(s.runs_error)} erro(s)`
              : "sem erros"
          }
        />
        <KpiTile
          label="Custo total"
          value={fmtBRL(s.cost_brl_total)}
          sub={`${fmtBRL(s.window_cost_brl)} nos ultimos ${s.window_days}d`}
        />
        <KpiTile
          label="Tokens"
          value={fmtInt(tokensTotal)}
          sub={
            s.avg_duration_ms != null
              ? `${fmtInt(Math.round(s.avg_duration_ms))} ms/exec media`
              : undefined
          }
        />
      </div>

      {s.last_run_at && (
        <div className="text-[12px] text-gray-500 dark:text-gray-400">
          Ultima execucao{" "}
          {formatDistanceToNow(parseISO(s.last_run_at), {
            addSuffix: true,
            locale: ptBR,
          })}
          .
        </div>
      )}

      {/* Por modelo — leitura estatica, sem sort/acoes -> DenseTable */}
      <section>
        <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
          Por modelo
        </h3>
        <DenseTable
          columns={[
            { key: "model", label: "Modelo" },
            { key: "runs", label: "Execucoes", format: "numero" },
            { key: "tokens", label: "Tokens", format: "numero" },
            { key: "custo", label: "Custo", format: "brl" },
          ]}
          rows={s.by_model.map((m) => ({
            model: m.model,
            runs: m.runs,
            tokens: m.tokens_total,
            custo: m.cost_brl,
          }))}
        />
      </section>

      {/* Execucoes recentes — listagem read-only -> DataTable (Exploracao) */}
      <section>
        <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
          Execucoes recentes
        </h3>
        <DataTable<AIAgentRunRecent>
          data={s.recent_runs}
          columns={recentRunsColumns}
        />
      </section>

      <p className={cx("text-[11px] text-gray-400 dark:text-gray-500")}>
        Fonte: <code>agent_analysis_run</code> · agregado por nome do agente,
        cross-tenant. <code>ai_usage_event</code> nao carrega atribuicao por
        agente, entao chat conversacional puro nao entra aqui.
      </p>
    </div>
  )
}
