"use client"

import * as React from "react"
import { format, parseISO } from "date-fns"
import { ptBR } from "date-fns/locale"
import { RiInformationLine } from "@remixicon/react"

import { Tooltip } from "@/components/tremor/Tooltip"
import { cx } from "@/lib/utils"
import type { CoverageStatus, EndpointCoverage } from "@/lib/api-client"

const STATUS_STYLES: Record<CoverageStatus, { bg: string; label: string }> = {
  ok: { bg: "bg-emerald-500", label: "Coletado" },
  not_published: { bg: "bg-amber-300", label: "Sem publicação (4xx)" },
  gap: { bg: "bg-red-500", label: "FURO — dia útil sem dado" },
  weekend: {
    bg: "bg-gray-200 dark:bg-gray-800",
    label: "Fim de semana",
  },
  holiday: {
    bg: "bg-gray-200 dark:bg-gray-800",
    label: "Feriado",
  },
  pending: { bg: "bg-blue-300", label: "Pendente (data futura/hoje)" },
  before_first_sync: {
    bg: "bg-gray-100 dark:bg-gray-900",
    label: "Antes do primeiro sync",
  },
  unsupported: {
    bg: "bg-gray-100 dark:bg-gray-900",
    label: "Não aplicável",
  },
}

/**
 * Heatmap horizontal de cobertura de datas por endpoint.
 *
 * Layout: 1 linha por endpoint. Cada linha tem nome+contadores à esquerda
 * e o heatmap horizontal de N dias à direita. Cores por status.
 *
 * Recomendado pra ~30..180 dias. Acima disso considere paginar por mês.
 */
export function CoverageHeatmap({
  endpoints,
  startDate,
  endDate,
}: {
  endpoints: EndpointCoverage[]
  startDate: string
  endDate: string
}) {
  // Tick markers de mês (a posição em índice de dia onde começa cada mês)
  const monthTicks = React.useMemo(() => {
    const start = parseISO(startDate)
    const end = parseISO(endDate)
    const ticks: { dayIndex: number; label: string }[] = []
    const cursor = new Date(start)
    let idx = 0
    while (cursor <= end) {
      if (cursor.getDate() === 1 || idx === 0) {
        ticks.push({
          dayIndex: idx,
          label: format(cursor, "MMM", { locale: ptBR }),
        })
      }
      cursor.setDate(cursor.getDate() + 1)
      idx++
    }
    return ticks
  }, [startDate, endDate])

  const totalDays = endpoints[0]?.days.length ?? 0

  return (
    <div className="flex flex-col gap-3 rounded border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-[#090E1A]">
      <Legend />

      {/* Header com ticks de mês */}
      <div className="flex items-center gap-4 pl-[280px] pr-2 text-[10px] uppercase tracking-wider text-gray-500 dark:text-gray-400">
        <div
          className="relative flex-1"
          style={{ minHeight: 16 }}
        >
          {monthTicks.map((t) => (
            <span
              key={`${t.dayIndex}-${t.label}`}
              className="absolute top-0"
              style={{ left: `${(t.dayIndex / totalDays) * 100}%` }}
            >
              {t.label}
            </span>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        {endpoints.map((ep) => (
          <EndpointRow key={ep.name} ep={ep} />
        ))}
      </div>

      <p className="flex items-center gap-1 pt-2 text-[11px] text-gray-500 dark:text-gray-400">
        <RiInformationLine className="size-3" aria-hidden />
        Cobertura de {format(parseISO(startDate), "dd/MMM/yyyy", { locale: ptBR })} a{" "}
        {format(parseISO(endDate), "dd/MMM/yyyy", { locale: ptBR })}. Furos vermelhos
        são dias úteis ANBIMA sem nenhuma linha raw — investigar.
      </p>
    </div>
  )
}

function EndpointRow({ ep }: { ep: EndpointCoverage }) {
  if (!ep.supported) {
    return (
      <div className="flex items-center gap-4 text-[12px] text-gray-500 dark:text-gray-400">
        <div className="w-[200px] truncate font-medium" title={ep.label}>
          {ep.label}
        </div>
        <div className="w-[60px] text-right text-[11px]">—</div>
        <div className="flex-1 italic">
          Cobertura não aplicável ({ep.schedule_kind})
        </div>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-4">
      <div
        className="w-[200px] truncate text-[12px] font-medium text-gray-900 dark:text-gray-100"
        title={ep.label}
      >
        {ep.label}
      </div>

      <div className="flex w-[60px] flex-col items-end text-[10px] leading-tight">
        <span className="text-emerald-700 dark:text-emerald-400">
          {ep.count_ok} ok
        </span>
        {ep.count_gap > 0 && (
          <span className="font-medium text-red-600 dark:text-red-400">
            {ep.count_gap} furo{ep.count_gap > 1 ? "s" : ""}
          </span>
        )}
      </div>

      <div className="flex flex-1 gap-[1px]">
        {ep.days.map((d) => (
          <Tooltip
            key={d.data}
            content={renderTooltip(d.data, d.status, d.http_status)}
            side="top"
          >
            <div
              className={cx(
                "h-4 flex-1 cursor-default rounded-[1px] transition-opacity hover:opacity-70",
                STATUS_STYLES[d.status].bg,
              )}
            />
          </Tooltip>
        ))}
      </div>
    </div>
  )
}

function renderTooltip(
  iso: string,
  status: CoverageStatus,
  httpStatus: number | null,
) {
  const dataFmt = format(parseISO(iso), "EEE dd/MMM/yyyy", { locale: ptBR })
  const statusLabel = STATUS_STYLES[status].label
  if (httpStatus !== null) {
    return `${dataFmt} · ${statusLabel} (HTTP ${httpStatus})`
  }
  return `${dataFmt} · ${statusLabel}`
}

function Legend() {
  const items: { status: CoverageStatus; label: string }[] = [
    { status: "ok", label: "Coletado" },
    { status: "not_published", label: "Sem publicação" },
    { status: "gap", label: "Furo" },
    { status: "weekend", label: "Fds/feriado" },
    { status: "pending", label: "Pendente" },
    { status: "before_first_sync", label: "Antes do 1º sync" },
  ]
  return (
    <div className="flex flex-wrap items-center gap-3 text-[11px] text-gray-600 dark:text-gray-400">
      {items.map((i) => (
        <div key={i.status} className="flex items-center gap-1.5">
          <span
            className={cx("inline-block h-3 w-3 rounded-[1px]", STATUS_STYLES[i.status].bg)}
            aria-hidden
          />
          {i.label}
        </div>
      ))}
    </div>
  )
}
