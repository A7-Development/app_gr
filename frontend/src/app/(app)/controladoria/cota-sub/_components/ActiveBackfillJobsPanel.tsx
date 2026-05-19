"use client"

/**
 * ActiveBackfillJobsPanel — visibilidade de jobs de sync QiTech em execucao
 * para o (fundo, data) selecionados na Cota Sub.
 *
 * Renderiza apenas quando ha jobs ativos (pending/running) que tocam o
 * dia selecionado. Backend ja filtra status via `/backfill/active` (so
 * pending+running); filtro de UA + data eh client-side.
 *
 * Auto-refresh via `useActiveBackfills(..., { pollMs: 3000 })` enquanto
 * houver jobs ativos. Quando todos terminam, lista zera, polling para,
 * e o painel some — a invalidacao do `useBackfillJob` (no jobId polling)
 * ja cuida do refresh do coverage strip, entao a transicao e suave.
 */

import * as React from "react"
import { formatDistanceToNowStrict } from "date-fns"
import { ptBR } from "date-fns/locale"
import { RiLoader4Line, RiTimeLine } from "@remixicon/react"

import { cx } from "@/lib/utils"
import { COTA_SUB_REPORTS } from "@/lib/hooks/controladoria"
import { useActiveBackfills } from "@/lib/hooks/integracoes"
import type { BackfillJob } from "@/lib/api-client"

type Props = {
  /** UUID do fundo (UA) selecionado. Null = nenhum fundo escolhido. */
  fundoId: string | null
  /** ISO date (YYYY-MM-DD) do dia analisado. Null = nenhum dia escolhido. */
  dayIso:  string | null
}

const LABEL_BY_NAME = new Map(
  COTA_SUB_REPORTS.map((r) => [r.name, r.shortLabel] as const),
)

function formatDateBr(iso: string): string {
  // iso = "YYYY-MM-DD"
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso)
  return m ? `${m[3]}/${m[2]}` : iso
}

function jobTouchesDay(job: BackfillJob, dayIso: string): boolean {
  return (
    job.dates_pending.includes(dayIso)
    || job.dates_done.includes(dayIso)
    || job.dates_failed.some((d) => d.date === dayIso)
  )
}

function progressFor(job: BackfillJob, dayIso?: string | null): { done: number; total: number } {
  if (dayIso) {
    // Progresso "deste dia": 0/1 enquanto pending, 1/1 quando done/failed.
    const inPending = job.dates_pending.includes(dayIso) ? 1 : 0
    const inDone    = job.dates_done.includes(dayIso) ? 1 : 0
    const inFailed  = job.dates_failed.some((d) => d.date === dayIso) ? 1 : 0
    return { done: inDone + inFailed, total: inPending + inDone + inFailed }
  }
  // Progresso global do job.
  const total = job.dates_pending.length + job.dates_done.length + job.dates_failed.length
  const done  = job.dates_done.length + job.dates_failed.length
  return { done, total }
}

function statusBadgeCls(status: BackfillJob["status"]): string {
  switch (status) {
    case "running":
      return "bg-blue-50 text-blue-700 ring-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:ring-blue-500/30"
    case "pending":
      return "bg-amber-50 text-amber-700 ring-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/30"
    default:
      return "bg-gray-100 text-gray-600 ring-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:ring-gray-700"
  }
}

function statusLabel(status: BackfillJob["status"]): string {
  switch (status) {
    case "running": return "em execução"
    case "pending": return "na fila"
    default:        return status
  }
}

export function ActiveBackfillJobsPanel({ fundoId, dayIso }: Props) {
  const q = useActiveBackfills("admin:qitech", undefined, { pollMs: 3000 })

  const jobs = React.useMemo<BackfillJob[]>(() => {
    if (!q.data || !fundoId || !dayIso) return []
    return q.data.filter(
      (j) =>
        j.unidade_administrativa_id === fundoId
        && jobTouchesDay(j, dayIso),
    )
  }, [q.data, fundoId, dayIso])

  if (jobs.length === 0) return null

  return (
    <div className="rounded border border-blue-200 bg-blue-50/60 px-4 py-3 dark:border-blue-500/30 dark:bg-blue-500/5">
      <div className="mb-2 flex items-baseline gap-2">
        <RiLoader4Line className="size-4 animate-spin text-blue-600 dark:text-blue-400" aria-hidden="true" />
        <span className="text-[13px] font-semibold text-blue-900 dark:text-blue-200">
          {jobs.length === 1
            ? "1 sync em andamento para este dia"
            : `${jobs.length} syncs em andamento para este dia`}
        </span>
        <span className="text-[11.5px] text-blue-700/80 dark:text-blue-300/70">
          atualiza a cada 3s — o strip vira verde quando concluir
        </span>
      </div>

      <ul className="flex flex-col gap-1.5">
        {jobs.map((job) => (
          <JobRow key={job.id} job={job} dayIso={dayIso} />
        ))}
      </ul>
    </div>
  )
}

function JobRow({ job, dayIso }: { job: BackfillJob; dayIso: string | null }) {
  const { done, total } = progressFor(job, dayIso)
  const label = LABEL_BY_NAME.get(job.endpoint_name) ?? job.endpoint_name
  const startedAt = job.started_at ?? job.created_at
  const since = formatDistanceToNowStrict(new Date(startedAt), {
    locale:    ptBR,
    addSuffix: false,
  })

  // Job id compacto para fins de auditoria — primeiros 8 chars.
  const jobShort = job.id.slice(0, 8)

  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded border border-blue-200/60 bg-white px-3 py-1.5 text-[12px] dark:border-blue-500/20 dark:bg-gray-950">
      <span className="font-medium text-gray-900 dark:text-gray-50">{label}</span>
      {dayIso && (
        <span className="font-mono text-[11px] text-gray-500 dark:text-gray-400">
          {formatDateBr(dayIso)}
        </span>
      )}
      <span
        className={cx(
          "inline-flex items-center rounded px-1.5 py-0.5 text-[10.5px] font-medium ring-1 ring-inset",
          statusBadgeCls(job.status),
        )}
      >
        {statusLabel(job.status)}
      </span>
      <span className="tabular-nums text-gray-600 dark:text-gray-300">
        {done}/{total} {total === 1 ? "data" : "datas"}
      </span>
      <span className="inline-flex items-center gap-1 text-gray-500 dark:text-gray-400">
        <RiTimeLine className="size-3" aria-hidden="true" />
        há {since}
      </span>
      <span className="ml-auto font-mono text-[10.5px] text-gray-400 dark:text-gray-600">
        job {jobShort}
      </span>
    </li>
  )
}
