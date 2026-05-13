"use client"

import * as React from "react"
import { format, parseISO } from "date-fns"
import { ptBR } from "date-fns/locale"
import { RiInformationLine, RiLoader4Line, RiPlayLine } from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { cx } from "@/lib/utils"
import type {
  BackfillJob,
  Completeness,
  CoverageStatus,
  EndpointCoverage,
} from "@/lib/api-client"

const STATUS_STYLES: Record<CoverageStatus, { bg: string; label: string }> = {
  ok: { bg: "bg-emerald-500", label: "Coletado" },
  // Escala de severidade da menor para a maior (Opcao A, 2026-05-13):
  // ok (emerald) -> partial (amber-300) -> not_published (orange-400) -> gap (red).
  partial: { bg: "bg-amber-300", label: "Publicação parcial" },
  not_published: { bg: "bg-orange-400", label: "Sem publicação (4xx)" },
  gap: { bg: "bg-red-500", label: "FURO — dia útil sem dado" },
  weekend: { bg: "bg-gray-200 dark:bg-gray-800", label: "Fim de semana" },
  holiday: { bg: "bg-gray-200 dark:bg-gray-800", label: "Feriado" },
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

const LABEL_COL = "minmax(220px, 280px)"

/**
 * Heatmap horizontal de cobertura de datas por endpoint.
 *
 * Cada linha tem: label + (botao Backfill se houver furos) + heatmap.
 * Tooltips via `title` HTML nativo.
 *
 * Suporta qualquer range (30..730 dias). Acima de 365 dias ativa scroll
 * horizontal.
 *
 * Backfill: quando um endpoint tem um `activeJobByEndpoint[name]`, as
 * datas em `dates_pending` daquele job sao pintadas como "processando"
 * (azul claro, animado).
 */
export function CoverageHeatmap({
  endpoints,
  startDate,
  endDate,
  onBackfill,
  activeJobByEndpoint = {},
}: {
  endpoints: EndpointCoverage[]
  startDate: string
  endDate: string
  /** Quando undefined, oculta os botoes de backfill (modo somente-leitura). */
  onBackfill?: (endpointName: string, dates: string[]) => void
  /** Job ativo por endpoint_name. Usado pra pintar celulas em processamento. */
  activeJobByEndpoint?: Record<string, BackfillJob>
}) {
  const totalDays = endpoints[0]?.days.length ?? 0

  const monthMarkers = React.useMemo(() => {
    if (!endpoints[0]) return []
    return endpoints[0].days.map((d, i) => {
      const date = parseISO(d.data)
      const isFirstOfMonth = date.getUTCDate() === 1 || i === 0
      return {
        index: i,
        label: isFirstOfMonth ? format(date, "MMM/yy", { locale: ptBR }) : null,
      }
    })
  }, [endpoints])

  const enableScroll = totalDays > 365
  const cellMinWidth = enableScroll ? "3px" : "0"

  return (
    <div className="rounded border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-[#090E1A]">
      <Legend />

      <div className={cx("mt-4", enableScroll && "overflow-x-auto")}>
        <div
          className="grid items-center gap-x-3 gap-y-2"
          style={{
            gridTemplateColumns: `${LABEL_COL} 1fr`,
            minWidth: enableScroll ? `${280 + totalDays * 4}px` : undefined,
          }}
        >
          <div />
          <div
            className="grid items-end gap-[1px] pb-1"
            style={{
              gridTemplateColumns: `repeat(${totalDays}, minmax(${cellMinWidth}, 1fr))`,
            }}
          >
            {monthMarkers.map((m) => (
              <div
                key={m.index}
                className="h-3 text-[10px] uppercase tracking-wider text-gray-500 dark:text-gray-400"
              >
                {m.label && (
                  <span className="whitespace-nowrap">{m.label}</span>
                )}
              </div>
            ))}
          </div>

          {endpoints.map((ep) => (
            <EndpointRow
              key={ep.name}
              ep={ep}
              cellMinWidth={cellMinWidth}
              onBackfill={onBackfill}
              activeJob={activeJobByEndpoint[ep.name]}
            />
          ))}
        </div>
      </div>

      <p className="mt-4 flex items-start gap-1.5 text-[11px] text-gray-500 dark:text-gray-400">
        <RiInformationLine className="size-3.5 shrink-0" aria-hidden />
        <span>
          Cobertura de{" "}
          <span className="font-medium">
            {format(parseISO(startDate), "dd/MMM/yyyy", { locale: ptBR })}
          </span>{" "}
          a{" "}
          <span className="font-medium">
            {format(parseISO(endDate), "dd/MMM/yyyy", { locale: ptBR })}
          </span>
          . Vermelho = dia útil ANBIMA sem nenhuma linha raw (furo real).
          Amarelo = publicação parcial (a fonte respondeu OK mas faltou
          subset esperado — ex.: relatório RF sem o POV principal).
          Cinza = fim de semana / feriado / antes do primeiro sync configurado.
          Click "Backfill" pra preencher os furos de um endpoint.
        </span>
      </p>
    </div>
  )
}

function EndpointRow({
  ep,
  cellMinWidth,
  onBackfill,
  activeJob,
}: {
  ep: EndpointCoverage
  cellMinWidth: string
  onBackfill?: (endpointName: string, dates: string[]) => void
  activeJob?: BackfillJob
}) {
  const gapDates = React.useMemo(
    () => ep.days.filter((d) => d.status === "gap").map((d) => d.data),
    [ep.days],
  )

  const processingSet = React.useMemo(() => {
    if (!activeJob) return new Set<string>()
    return new Set([
      ...activeJob.dates_pending,
      ...activeJob.dates_done,
      ...activeJob.dates_failed.map((f) => f.date),
    ])
  }, [activeJob])

  const pendingSet = React.useMemo(
    () => new Set(activeJob?.dates_pending ?? []),
    [activeJob],
  )

  const hasGaps = gapDates.length > 0
  const isJobActive =
    activeJob?.status === "pending" || activeJob?.status === "running"

  return (
    <>
      <div className="flex items-center gap-2 min-w-0">
        <div
          className="truncate text-[12px] font-medium text-gray-900 dark:text-gray-100"
          title={`${ep.label} · ${ep.schedule_kind}`}
        >
          {ep.label}
        </div>
        {hasGaps && onBackfill && !isJobActive && (
          <Button
            variant="ghost"
            className="h-6 shrink-0 px-2 text-[11px]"
            onClick={() => onBackfill(ep.name, gapDates)}
            title={`Preencher ${gapDates.length} furo${gapDates.length > 1 ? "s" : ""} chamando a API pra cada data`}
          >
            <RiPlayLine className="size-3 mr-1" aria-hidden />
            {gapDates.length} furo{gapDates.length > 1 ? "s" : ""}
          </Button>
        )}
        {isJobActive && (
          <span className="inline-flex shrink-0 items-center gap-1 rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-medium text-blue-700 dark:bg-blue-400/10 dark:text-blue-300">
            <RiLoader4Line className="size-3 animate-spin" aria-hidden />
            {activeJob.dates_done.length}/{activeJob.dates_done.length + activeJob.dates_pending.length + activeJob.dates_failed.length}
          </span>
        )}
      </div>
      <div
        className="grid gap-[1px]"
        style={{
          gridTemplateColumns: `repeat(${ep.days.length}, minmax(${cellMinWidth}, 1fr))`,
        }}
      >
        {ep.days.map((d) => {
          const isProcessing = pendingSet.has(d.data)
          const isInActiveJob = processingSet.has(d.data)
          return (
            <div
              key={d.data}
              title={renderTooltip(
                d.data,
                d.status,
                d.http_status,
                d.completeness,
                isProcessing,
              )}
              className={cx(
                "h-6 rounded-[1px] cursor-default transition-opacity hover:opacity-70",
                isProcessing
                  ? "bg-blue-300 animate-pulse"
                  : isInActiveJob && !pendingSet.has(d.data)
                  ? "bg-emerald-500"
                  : STATUS_STYLES[d.status].bg,
              )}
            />
          )
        })}
      </div>
    </>
  )
}

function renderTooltip(
  iso: string,
  status: CoverageStatus,
  httpStatus: number | null,
  completeness: Completeness | null,
  isProcessing: boolean,
) {
  const dataFmt = format(parseISO(iso), "EEE dd/MMM/yyyy", { locale: ptBR })
  if (isProcessing) return `${dataFmt} · Backfill em andamento…`
  const statusLabel = STATUS_STYLES[status].label
  // Detalha o "porque" quando partial — diferenca crucial vs zero real.
  // Empty: payload chegou mas vazio; partial: chegou mas falta subset.
  let suffix = ""
  if (status === "partial") {
    if (completeness === "empty") {
      suffix = " — payload vazio (a fonte respondeu mas sem dados)"
    } else {
      suffix = " — falta subset esperado (ex.: classe de cota ausente)"
    }
  }
  if (httpStatus !== null) {
    return `${dataFmt} · ${statusLabel} (HTTP ${httpStatus})${suffix}`
  }
  return `${dataFmt} · ${statusLabel}${suffix}`
}

function Legend() {
  const items: { status: CoverageStatus; label: string }[] = [
    { status: "ok", label: "Coletado" },
    { status: "partial", label: "Parcial" },
    { status: "not_published", label: "Sem publicação" },
    { status: "gap", label: "Furo" },
    { status: "weekend", label: "Fds / feriado" },
    { status: "pending", label: "Pendente" },
    { status: "before_first_sync", label: "Antes do 1º sync" },
  ]
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-gray-600 dark:text-gray-400">
      {items.map((i) => (
        <div key={i.status} className="flex items-center gap-1.5">
          <span
            className={cx(
              "inline-block h-3 w-3 rounded-[1px] ring-1 ring-inset ring-gray-200 dark:ring-gray-700",
              STATUS_STYLES[i.status].bg,
            )}
            aria-hidden
          />
          {i.label}
        </div>
      ))}
    </div>
  )
}
