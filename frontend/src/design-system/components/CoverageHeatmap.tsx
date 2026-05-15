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
  PublicationState,
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

// Override por `tolerance_state` (2026-05-15) — substitui cor do STATUS_STYLES
// quando o dia esta em GAP/NOT_PUBLISHED/PENDING. Distingue:
//   ESPERADO        — slate (sem alarde, ainda dentro do SLA)
//   ATRASADO        — amber (passou do SLA, mas razoavel)
//   SUSPEITO        — red (provavel problema)
//   FURO_DEFINITIVO — gray escuro com hatch (sistema desistiu)
const TOLERANCE_STYLES: Record<
  PublicationState,
  { bg: string; label: string }
> = {
  esperado: { bg: "bg-slate-300 dark:bg-slate-700", label: "Esperado" },
  atrasado: { bg: "bg-amber-400", label: "Atrasado" },
  suspeito: { bg: "bg-red-500", label: "Suspeito" },
  furo_definitivo: {
    bg: "bg-gray-400 dark:bg-gray-600",
    label: "Furo definitivo",
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
          . Dias sem dado são classificados pela tolerância configurada do
          endpoint:{" "}
          <strong>esperado</strong> (dentro do prazo),{" "}
          <strong>atrasado</strong> (passou do prazo, sistema ainda tenta),{" "}
          <strong>suspeito</strong> (provavel problema na fonte) e{" "}
          <strong>furo definitivo</strong> (sistema desistiu — clique em
          Reabrir pra forçar). Janela de cada endpoint configurável na aba
          Endpoints.
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

  // Sub-titulo: janela efetiva legivel. Se o endpoint nao suporta coverage
  // (unsupported), os campos sao null e nao mostramos legenda.
  const hasWindow =
    ep.expected_lag_business_days !== null &&
    ep.tolerance_business_days !== null &&
    ep.give_up_business_days !== null

  // Botao de backfill conta APENAS furos definitivos (sistema desistiu).
  // Datas em ESPERADO/ATRASADO/SUSPEITO o reconciler ainda esta tentando —
  // operador nao precisa forcar manualmente.
  const furosDefinitivosDates = React.useMemo(
    () =>
      ep.days
        .filter((d) => d.tolerance_state === "furo_definitivo")
        .map((d) => d.data),
    [ep.days],
  )
  const hasFurosDefinitivos = furosDefinitivosDates.length > 0

  return (
    <>
      <div className="flex items-center gap-2 min-w-0">
        <div className="flex flex-col min-w-0">
          <div
            className="truncate text-[12px] font-medium text-gray-900 dark:text-gray-100"
            title={`${ep.label} · ${ep.schedule_kind}`}
          >
            {ep.label}
          </div>
          {hasWindow && (
            <div
              className="text-[10px] text-gray-500 dark:text-gray-400"
              title="Janela efetiva (override do tenant ou default do catálogo)"
            >
              esperado D+{ep.expected_lag_business_days} · atrasado D+
              {(ep.tolerance_business_days as number) + 1} · suspeito até D+
              {ep.give_up_business_days}
            </div>
          )}
        </div>
        {hasFurosDefinitivos && onBackfill && !isJobActive && (
          <Button
            variant="ghost"
            className="h-6 shrink-0 px-2 text-[11px]"
            onClick={() => onBackfill(ep.name, furosDefinitivosDates)}
            title={`Reabrir ${furosDefinitivosDates.length} furo${furosDefinitivosDates.length > 1 ? "s" : ""} definitivo${furosDefinitivosDates.length > 1 ? "s" : ""} — sistema havia desistido, força nova tentativa`}
          >
            <RiPlayLine className="size-3 mr-1" aria-hidden />
            Reabrir {furosDefinitivosDates.length}
          </Button>
        )}
        {!hasFurosDefinitivos && hasGaps && onBackfill && !isJobActive && (
          // Fallback: nenhum furo definitivo mas ainda há gaps em estados
          // recuperáveis (ESPERADO/ATRASADO/SUSPEITO). Reconciler está
          // cuidando — botão fica disponivel pra forcar imediato.
          <Button
            variant="ghost"
            className="h-6 shrink-0 px-2 text-[11px] text-gray-600"
            onClick={() => onBackfill(ep.name, gapDates)}
            title={`Forçar backfill de ${gapDates.length} furo${gapDates.length > 1 ? "s" : ""} (o reconciler já está tentando — clicar acelera)`}
          >
            <RiPlayLine className="size-3 mr-1" aria-hidden />
            Forçar {gapDates.length}
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
          // Cor: tolerance_state sobrepoe status quando aplicavel.
          const cellBg = isProcessing
            ? "bg-blue-300 animate-pulse"
            : isInActiveJob && !pendingSet.has(d.data)
            ? "bg-emerald-500"
            : d.tolerance_state
            ? TOLERANCE_STYLES[d.tolerance_state].bg
            : STATUS_STYLES[d.status].bg
          return (
            <div
              key={d.data}
              title={renderTooltip(
                d.data,
                d.status,
                d.http_status,
                d.completeness,
                d.tolerance_state,
                isProcessing,
              )}
              className={cx(
                "h-6 rounded-[1px] cursor-default transition-opacity hover:opacity-70",
                cellBg,
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
  toleranceState: PublicationState | null,
  isProcessing: boolean,
) {
  const dataFmt = format(parseISO(iso), "EEE dd/MMM/yyyy", { locale: ptBR })
  if (isProcessing) return `${dataFmt} · Backfill em andamento…`
  // Quando tolerance_state esta presente, ele e a info mais relevante pro
  // operador (graduacao temporal); status base vira complementar.
  if (toleranceState) {
    const stateLabel = TOLERANCE_STYLES[toleranceState].label
    const baseLabel = STATUS_STYLES[status].label
    let detail = ""
    if (toleranceState === "esperado") {
      detail = " — ainda dentro do prazo esperado de publicação."
    } else if (toleranceState === "atrasado") {
      detail = " — passou do prazo, sistema continua tentando."
    } else if (toleranceState === "suspeito") {
      detail =
        " — muito atrasado, provavel problema na fonte. Sistema tenta com cadência reduzida."
    } else if (toleranceState === "furo_definitivo") {
      detail =
        " — sistema parou de tentar automaticamente. Clique em Reabrir pra forçar nova tentativa."
    }
    if (httpStatus !== null) {
      return `${dataFmt} · ${stateLabel} (${baseLabel.toLowerCase()}, HTTP ${httpStatus})${detail}`
    }
    return `${dataFmt} · ${stateLabel} (${baseLabel.toLowerCase()})${detail}`
  }
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
  // Legenda separa em 2 grupos: status base (presente) e tolerância (futuro).
  // Operador entende que tolerance_state se aplica a dias que estão sem dado.
  const statusItems: { status: CoverageStatus; label: string }[] = [
    { status: "ok", label: "Coletado" },
    { status: "partial", label: "Parcial" },
    { status: "weekend", label: "Fds / feriado" },
    { status: "before_first_sync", label: "Antes do 1º sync" },
  ]
  const toleranceItems: { state: PublicationState; label: string }[] = [
    { state: "esperado", label: "Esperado" },
    { state: "atrasado", label: "Atrasado" },
    { state: "suspeito", label: "Suspeito" },
    { state: "furo_definitivo", label: "Furo definitivo" },
  ]
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-gray-600 dark:text-gray-400">
        <span className="font-medium text-gray-700 dark:text-gray-300">
          Coletado:
        </span>
        {statusItems.map((i) => (
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
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-gray-600 dark:text-gray-400">
        <span className="font-medium text-gray-700 dark:text-gray-300">
          Ainda sem dado:
        </span>
        {toleranceItems.map((i) => (
          <div key={i.state} className="flex items-center gap-1.5">
            <span
              className={cx(
                "inline-block h-3 w-3 rounded-[1px] ring-1 ring-inset ring-gray-200 dark:ring-gray-700",
                TOLERANCE_STYLES[i.state].bg,
              )}
              aria-hidden
            />
            {i.label}
          </div>
        ))}
      </div>
    </div>
  )
}
