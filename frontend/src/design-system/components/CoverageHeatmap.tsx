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

/**
 * Modelo de saude do dado — 5 estados voltados ao usuario.
 *
 * Decisao 2026-05-16 (Ricardo): UI projeta o cross-product de
 * (CoverageStatus × PublicationState × completeness) em 5 estados
 * canonicos. Backend mantem granularidade pra audit; aqui mostramos
 * "esta saude do dado e do sistema, agora".
 *
 *   ready       — dado pronto, sem expectativa de mudar
 *   may_change  — temos algo mas pode evoluir (partial, not_published,
 *                 ou complete recente sob refresh)
 *   in_progress — sem dado mas sistema esta cuidando (gap em retry)
 *   blocked     — sistema desistiu; precisa intervencao do operador
 *   na          — nao se aplica (fds, feriado, antes do 1o sync)
 */
export type DataHealth = "ready" | "may_change" | "in_progress" | "blocked" | "na"

export const HEALTH_STYLES: Record<
  DataHealth,
  { bg: string; label: string; description: string }
> = {
  ready: {
    bg: "bg-emerald-500",
    label: "Pronto",
    description: "Dado completo, sem expectativa de mudança.",
  },
  may_change: {
    bg: "bg-amber-400",
    label: "Pode mudar",
    description:
      "Temos algum dado mas pode evoluir — sistema continua re-checando.",
  },
  in_progress: {
    bg: "bg-blue-400",
    label: "Sistema cuidando",
    description:
      "Sem dado ainda; sistema está tentando dentro da janela esperada.",
  },
  blocked: {
    bg: "bg-red-500",
    label: "Bloqueado",
    description:
      "Sistema parou de tentar — operador decide reabrir ou aceitar.",
  },
  na: {
    bg: "bg-gray-200 dark:bg-gray-800",
    label: "N/A",
    description: "Fim de semana, feriado ou antes do primeiro sync.",
  },
}

/**
 * Projeta o tuplo (status, tolerance_state, completeness) -> DataHealth.
 *
 * Regras:
 *   ok+complete (ou completeness=null por legacy)  -> ready
 *   ok+partial/empty                                -> may_change
 *   partial (qualquer tolerance)                    -> may_change
 *   not_published                                   -> blocked se FURO_DEFINITIVO
 *                                                      may_change caso contrario
 *   gap                                             -> blocked se FURO_DEFINITIVO
 *                                                      in_progress caso contrario
 *   pending                                         -> in_progress
 *   weekend/holiday/before_first_sync/unsupported   -> na
 */
export function deriveHealth(
  status: CoverageStatus,
  toleranceState: PublicationState | null,
  completeness: Completeness | null,
): DataHealth {
  if (toleranceState === "furo_definitivo") return "blocked"
  switch (status) {
    case "ok":
      // Legacy rows tinham completeness=null. Default benevolente = ready.
      return completeness && completeness !== "complete" ? "may_change" : "ready"
    case "partial":
      return "may_change"
    case "not_published":
      return "may_change"
    case "gap":
      return "in_progress"
    case "pending":
      return "in_progress"
    case "weekend":
    case "holiday":
    case "before_first_sync":
    case "unsupported":
      return "na"
    default:
      return "na"
  }
}

const LABEL_COL = "minmax(220px, 280px)"

/**
 * Heatmap horizontal de cobertura de datas por endpoint.
 *
 * Cada linha tem: label + (botao Backfill se houver furos) + heatmap.
 * Tooltips via `title` HTML nativo.
 *
 * Suporta qualquer range (30..2000 dias). Acima de 365 dias ativa scroll
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
          . As cores resumem a <strong>saúde do dado em cada dia</strong>:
          pronto, pode mudar, sistema cuidando, bloqueado, ou não-aplicável.
          Detalhes técnicos (HTTP, status, janela de tolerância) aparecem no
          tooltip de cada célula. Janela configurável na aba Endpoints.
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
  // Datas em estados retentaveis pelo reconciler (Fix A, 2026-05-16):
  // gap + partial + not_published que ainda nao viraram FURO_DEFINITIVO.
  // O botao "Forcar" antecipa a proxima tentativa pra TODAS elas.
  const retryableDates = React.useMemo(
    () =>
      ep.days
        .filter(
          (d) =>
            (d.status === "gap" ||
              d.status === "partial" ||
              d.status === "not_published") &&
            d.tolerance_state !== "furo_definitivo",
        )
        .map((d) => d.data),
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

  const isJobActive =
    activeJob?.status === "pending" || activeJob?.status === "running"

  // Sub-titulo: janela efetiva legivel. Se o endpoint nao suporta coverage
  // (unsupported), os campos sao null e nao mostramos legenda.
  const hasWindow =
    ep.expected_lag_business_days !== null &&
    ep.tolerance_business_days !== null &&
    ep.give_up_business_days !== null

  // Botoes:
  // - "Reabrir N" para FURO_DEFINITIVO (sistema desistiu — acao consciente)
  // - "Forçar N" para qualquer dia retentavel (sistema ainda tenta — acelera)
  const furosDefinitivosDates = React.useMemo(
    () =>
      ep.days
        .filter((d) => d.tolerance_state === "furo_definitivo")
        .map((d) => d.data),
    [ep.days],
  )
  const hasFurosDefinitivos = furosDefinitivosDates.length > 0
  const hasRetryable = retryableDates.length > 0

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
            title={`Reabrir ${furosDefinitivosDates.length} dia${furosDefinitivosDates.length > 1 ? "s" : ""} bloqueado${furosDefinitivosDates.length > 1 ? "s" : ""} — sistema havia desistido, força nova tentativa.`}
          >
            <RiPlayLine className="size-3 mr-1" aria-hidden />
            Reabrir {furosDefinitivosDates.length}
          </Button>
        )}
        {!hasFurosDefinitivos && hasRetryable && onBackfill && !isJobActive && (
          <Button
            variant="ghost"
            className="h-6 shrink-0 px-2 text-[11px] text-gray-600"
            onClick={() => onBackfill(ep.name, retryableDates)}
            title={`Forçar nova tentativa em ${retryableDates.length} dia${retryableDates.length > 1 ? "s" : ""} (sistema já está re-checando — clicar acelera).`}
          >
            <RiPlayLine className="size-3 mr-1" aria-hidden />
            Forçar {retryableDates.length}
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
          const wasProcessed = processingSet.has(d.data) && !isProcessing
          const health = deriveHealth(d.status, d.tolerance_state, d.completeness)
          const cellBg = isProcessing
            ? "bg-blue-300 animate-pulse"
            : wasProcessed
            ? HEALTH_STYLES.ready.bg
            : HEALTH_STYLES[health].bg
          return (
            <div
              key={d.data}
              title={renderTooltip(
                d.data,
                d.status,
                d.http_status,
                d.completeness,
                d.tolerance_state,
                health,
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
  health: DataHealth,
  isProcessing: boolean,
) {
  const dataFmt = format(parseISO(iso), "EEE dd/MMM/yyyy", { locale: ptBR })
  if (isProcessing) return `${dataFmt} · Backfill em andamento…`

  const healthLabel = HEALTH_STYLES[health].label
  const technical = describeTechnical(status, httpStatus, completeness, toleranceState)
  const why = describeWhy(health, status, completeness, toleranceState)
  return `${dataFmt} · ${healthLabel}\n${technical}\n${why}`.trim()
}

function describeTechnical(
  status: CoverageStatus,
  httpStatus: number | null,
  completeness: Completeness | null,
  toleranceState: PublicationState | null,
): string {
  const bits: string[] = []
  if (httpStatus !== null) bits.push(`HTTP ${httpStatus}`)
  if (completeness && completeness !== "complete") bits.push(`payload ${completeness}`)
  if (status === "gap") bits.push("sem registro raw")
  if (toleranceState && toleranceState !== "furo_definitivo") {
    bits.push(`tolerância: ${toleranceState}`)
  }
  if (toleranceState === "furo_definitivo") bits.push("janela excedida")
  return bits.length > 0 ? `[${bits.join(" · ")}]` : ""
}

function describeWhy(
  health: DataHealth,
  status: CoverageStatus,
  completeness: Completeness | null,
  toleranceState: PublicationState | null,
): string {
  switch (health) {
    case "ready":
      return "Dado coletado e considerado completo."
    case "may_change":
      if (status === "partial") {
        if (completeness === "empty") {
          return "A fonte respondeu mas o payload veio vazio — sistema continua re-checando."
        }
        return "Falta um subset esperado (ex.: classe de cota ausente). Sistema continua re-checando."
      }
      if (status === "not_published") {
        return "A fonte respondeu sem publicação (4xx) — sistema continua tentando."
      }
      return "Dado pode evoluir — sistema continua re-checando periodicamente."
    case "in_progress":
      if (status === "pending") {
        return "Data futura ou hoje — coleta esperada em breve."
      }
      if (toleranceState === "esperado") {
        return "Sem dado ainda, mas ainda dentro do prazo esperado."
      }
      if (toleranceState === "atrasado") {
        return "Atrasado — sistema retenta a cada 4h."
      }
      if (toleranceState === "suspeito") {
        return "Bem atrasado — sistema retenta com cadência reduzida (24h)."
      }
      return "Sistema tentando coletar."
    case "blocked":
      return "Sistema desistiu de tentar automaticamente. Clique em Reabrir pra forçar."
    case "na":
      return "Sem expectativa de dado — fim de semana, feriado, ou antes do primeiro sync."
  }
}

function Legend() {
  const items: { health: DataHealth }[] = [
    { health: "ready" },
    { health: "may_change" },
    { health: "in_progress" },
    { health: "blocked" },
    { health: "na" },
  ]
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-gray-600 dark:text-gray-400">
      {items.map((i) => {
        const style = HEALTH_STYLES[i.health]
        return (
          <div
            key={i.health}
            className="flex items-center gap-1.5"
            title={style.description}
          >
            <span
              className={cx(
                "inline-block h-3 w-3 rounded-[1px] ring-1 ring-inset ring-gray-200 dark:ring-gray-700",
                style.bg,
              )}
              aria-hidden
            />
            {style.label}
          </div>
        )
      })}
    </div>
  )
}
