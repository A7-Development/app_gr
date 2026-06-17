// src/app/(app)/admin/ia/agents/uso/page.tsx
//
// Uso do catalogo — ranking power-law dos agentes.
//
// Licao central do relatorio Prosus ("The Coming Age of AI Colleagues"):
// ~2% dos agentes geram impacto desproporcional. Este painel ranqueia por
// uso/custo/erro pra (a) achar em quem dobrar a aposta e (b) flagar quem
// nunca roda ("delete it tonight"). Read-only, agregado de agent_analysis_run.

"use client"

import * as React from "react"
import Link from "next/link"
import { RiArrowLeftLine, RiLoader4Line } from "@remixicon/react"
import { formatDistanceToNow, parseISO } from "date-fns"
import { ptBR } from "date-fns/locale"

import { PageHeader } from "@/design-system/components"
import {
  useAgentDefinitions,
  useAgentUsageOverview,
} from "@/lib/hooks/admin-ai"
import { cx } from "@/lib/utils"

import { ModuleBadge } from "../_components/AgentBadges"

const LIST_HREF = "/admin/ia/agents"
const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" })
const num = new Intl.NumberFormat("pt-BR")

function KpiTile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-md border border-gray-200 p-3 dark:border-gray-800">
      <div className="text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
        {label}
      </div>
      <div className="mt-1 text-[22px] font-semibold tabular-nums text-gray-900 dark:text-gray-50">
        {value}
      </div>
      {sub && (
        <div className="mt-0.5 text-[12px] text-gray-500 dark:text-gray-400">{sub}</div>
      )}
    </div>
  )
}

export default function AgentUsageOverviewPage() {
  const overviewQuery = useAgentUsageOverview()
  // Versoes ativas — mapeia nome -> {id ativo, modulo} e revela agentes sem run.
  const defsQuery = useAgentDefinitions()

  // nome -> versao ativa (id pra link + modulo). Dedup por nome.
  const byName = React.useMemo(() => {
    const m = new Map<string, { id: string; module: string }>()
    for (const d of defsQuery.data ?? []) {
      if (d.is_active && d.archived_at === null) {
        m.set(d.name, { id: d.id, module: d.module })
      }
    }
    return m
  }, [defsQuery.data])

  const usage = React.useMemo(
    () => overviewQuery.data ?? [],
    [overviewQuery.data],
  )

  // Agentes do catalogo que nunca rodaram (candidatos a revisar).
  const neverRan = React.useMemo(() => {
    const used = new Set(usage.map((u) => u.agent_name))
    return Array.from(byName.keys())
      .filter((n) => !used.has(n))
      .sort()
  }, [byName, usage])

  const totalAgents = byName.size
  const withActivity = usage.length
  const costWindow = usage.reduce((acc, u) => acc + u.cost_brl_window, 0)
  const runsWindow = usage.reduce((acc, u) => acc + u.window_runs, 0)
  const leader = usage[0]

  // Limiar power-law: top decil (min 1) das familias com atividade.
  const powerLawCut = Math.max(1, Math.ceil(withActivity * 0.1))

  const loading = overviewQuery.isLoading || defsQuery.isLoading

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-5 px-6 pt-5 pb-10">
      <Link
        href={LIST_HREF}
        className="flex w-fit items-center gap-1 text-[13px] font-medium text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
      >
        <RiArrowLeftLine className="size-4" aria-hidden />
        Voltar para agentes
      </Link>

      <PageHeader
        title="Uso do catalogo"
        subtitle="Inteligencia Artificial · Administracao"
        info="Ranking power-law dos agentes (agregado de agent_analysis_run, cross-tenant). Os primeiros sao onde dobrar a aposta; os que nunca rodam sao candidatos a revisar. Ultimos 30 dias."
      />

      {loading ? (
        <div className="flex items-center gap-2 py-10 text-[13px] text-gray-500">
          <RiLoader4Line className="size-4 animate-spin" aria-hidden />
          Carregando uso do catalogo...
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <KpiTile
              label="Agentes ativos"
              value={num.format(totalAgents)}
              sub={`${num.format(withActivity)} com atividade`}
            />
            <KpiTile
              label="Execucoes (30d)"
              value={num.format(runsWindow)}
            />
            <KpiTile label="Custo (30d)" value={brl.format(costWindow)} />
            <KpiTile
              label="Agente lider (30d)"
              value={leader ? `${num.format(leader.window_runs)} runs` : "—"}
              sub={leader?.agent_name}
            />
          </div>

          {usage.length === 0 ? (
            <div className="rounded-md border border-dashed border-gray-300 p-8 text-center dark:border-gray-700">
              <p className="text-[14px] font-medium text-gray-900 dark:text-gray-100">
                Nenhuma execucao registrada ainda
              </p>
              <p className="mt-1 text-[13px] text-gray-500 dark:text-gray-400">
                Quando os agentes rodarem, o ranking de uso aparece aqui.
              </p>
            </div>
          ) : (
            <section>
              <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                Ranking por uso
              </h3>
              <div className="overflow-x-auto rounded-md border border-gray-200 dark:border-gray-800">
                <table className="w-full text-[13px]">
                  <thead className="bg-gray-50 text-left text-[11px] uppercase tracking-wide text-gray-500 dark:bg-gray-900 dark:text-gray-400">
                    <tr>
                      <th className="px-3 py-2 font-medium">#</th>
                      <th className="px-3 py-2 font-medium">Agente</th>
                      <th className="px-3 py-2 font-medium">Modulo</th>
                      <th className="px-3 py-2 text-right font-medium">Runs (30d / total)</th>
                      <th className="px-3 py-2 text-right font-medium">Custo (30d / total)</th>
                      <th className="px-3 py-2 text-right font-medium">Erros</th>
                      <th className="px-3 py-2 font-medium">Ultima</th>
                    </tr>
                  </thead>
                  <tbody>
                    {usage.map((u, i) => {
                      const ref = byName.get(u.agent_name)
                      const isPowerLaw = i < powerLawCut
                      return (
                        <tr
                          key={u.agent_name}
                          className={cx(
                            "border-t border-gray-100 dark:border-gray-800",
                            isPowerLaw &&
                              "border-l-2 border-l-blue-500 bg-blue-50/40 dark:bg-blue-500/5",
                          )}
                        >
                          <td className="px-3 py-2 tabular-nums text-gray-500">
                            {i + 1}
                          </td>
                          <td className="px-3 py-2">
                            {ref ? (
                              <Link
                                href={`${LIST_HREF}/${ref.id}`}
                                className="font-mono text-[12px] font-medium text-blue-600 hover:text-blue-700 dark:text-blue-400"
                              >
                                {u.agent_name}
                              </Link>
                            ) : (
                              <span
                                className="font-mono text-[12px] text-gray-500"
                                title="Sem versao ativa no catalogo"
                              >
                                {u.agent_name}
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-2">
                            {ref ? <ModuleBadge module={ref.module} /> : "—"}
                          </td>
                          <td className="px-3 py-2 text-right tabular-nums">
                            {num.format(u.window_runs)}{" "}
                            <span className="text-gray-400">
                              / {num.format(u.total_runs)}
                            </span>
                          </td>
                          <td className="px-3 py-2 text-right tabular-nums">
                            {brl.format(u.cost_brl_window)}{" "}
                            <span className="text-gray-400">
                              / {brl.format(u.cost_brl_total)}
                            </span>
                          </td>
                          <td
                            className={cx(
                              "px-3 py-2 text-right tabular-nums",
                              u.runs_error > 0
                                ? "text-red-600 dark:text-red-400"
                                : "text-gray-400",
                            )}
                          >
                            {num.format(u.runs_error)}
                          </td>
                          <td className="whitespace-nowrap px-3 py-2 text-gray-500 dark:text-gray-400">
                            {u.last_run_at
                              ? formatDistanceToNow(parseISO(u.last_run_at), {
                                  addSuffix: true,
                                  locale: ptBR,
                                })
                              : "—"}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              <p className="mt-1.5 text-[11px] text-gray-400 dark:text-gray-500">
                Linhas destacadas = top decil (em quem dobrar a aposta).
              </p>
            </section>
          )}

          {neverRan.length > 0 && (
            <section>
              <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                Nunca rodaram ({neverRan.length}) · candidatos a revisar
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {neverRan.map((name) => {
                  const ref = byName.get(name)
                  return ref ? (
                    <Link
                      key={name}
                      href={`${LIST_HREF}/${ref.id}`}
                      className="rounded bg-gray-100 px-2 py-1 font-mono text-[11px] text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
                    >
                      {name}
                    </Link>
                  ) : null
                })}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  )
}
