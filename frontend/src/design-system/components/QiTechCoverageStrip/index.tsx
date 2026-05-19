"use client"

/**
 * QiTechCoverageStrip — strip horizontal compacto de saude de reports QiTech
 * para UMA DATA especifica. Espelha visualmente o `<CoverageHeatmap>`, mas em
 * vez de uma matriz endpoint × range de datas, e UMA linha endpoint × 1 dia.
 *
 * Uso canonico: Cota Sub e qualquer outra pagina derivada de snapshot diario
 * QiTech que precise gate de "so renderiza com 8/8 prontos". Mesma logica de
 * `deriveHealth()` do CoverageHeatmap — 5 estados projetados a partir do
 * cross-product (status, completeness, tolerance_state).
 *
 * Comportamento:
 *  - Quando TODOS os entries estao em `ready`/`may_change`: pill compacta
 *    ("✓ N/N reports prontos · 16/05") com chevron pra expandir.
 *  - Quando algum entry esta em `in_progress`/`blocked`/`na`: strip ja nasce
 *    expandido, mostrando chips coloridos por estado.
 *  - Chip clicavel abre Popover com label completo, status bruto, e botao
 *    "Forcar sync" quando `onBackfill` esta definido e o estado e bloqueador.
 */

import * as React from "react"
import {
  RiCheckLine,
  RiAlertLine,
  RiArrowRightSLine,
  RiLoader4Line,
  RiPlayLine,
  RiTimeLine,
} from "@remixicon/react"

import { cx } from "@/lib/utils"
import { Button } from "@/components/tremor/Button"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/tremor/Popover"
import {
  deriveHealth,
  HEALTH_STYLES,
  type DataHealth,
} from "../CoverageHeatmap"
import type {
  Completeness,
  CoverageDay,
  CoverageStatus,
  PublicationState,
} from "@/lib/api-client"

// ─────────────────────────────────────────────────────────────────────────────
// Tipos publicos
// ─────────────────────────────────────────────────────────────────────────────

export type CoverageStripEntry = {
  /** Nome canonico do endpoint, ex.: "market.tesouraria". */
  name: string
  /** Label curto exibido no chip (ex.: "Tesouraria"). */
  shortLabel: string
  /** Label completo (ex.: "Mercado · Tesouraria") exibido no Popover. */
  fullLabel?: string
  /** Saude derivada para o dia em foco. */
  health: DataHealth
  /**
   * Endpoint "advisory": pode legitimamente ficar vazio em dias normais
   * (ex.: rf_compromissadas, outros_ativos — so existe quando ha operacao
   * naquela natureza). Quando true E o health e nao-saudavel, o chip
   * renderiza com estilo neutro (dashed cinza) em vez de alerta vermelho;
   * popover sinaliza que o estado nao bloqueia a analise. Quando o health
   * e saudavel (ready/may_change), a flag advisory nao muda o visual.
   */
  advisory?: boolean
  /** Dados brutos do dia (status, completeness, tolerance) — usado no Popover. */
  raw?: {
    status: CoverageStatus
    completeness: Completeness | null
    toleranceState: PublicationState | null
    httpStatus: number | null
  }
}

export type QiTechCoverageStripProps = {
  /** Data em foco (ISO yyyy-mm-dd) — exibida na pill. */
  date: string
  /** Entries (1 por endpoint). */
  entries: CoverageStripEntry[]
  /** Callback "Forcar sync" para um endpoint. */
  onBackfill?: (endpointName: string) => void
  /** Endpoints com backfill job em curso (anima o chip). */
  activeJobs?: ReadonlySet<string>
  /** Mostra skeleton enquanto a query inicial nao retornou. */
  loading?: boolean
  className?: string
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers publicos para o consumer
// ─────────────────────────────────────────────────────────────────────────────

const HEALTHY_STATES: ReadonlySet<DataHealth> = new Set<DataHealth>(["ready", "may_change"])

/** True se o entry esta em estado saudavel (ready ou may_change). */
export function isEntryHealthy(entry: CoverageStripEntry): boolean {
  return HEALTHY_STATES.has(entry.health)
}

/** Constroi um CoverageStripEntry a partir de um CoverageDay opcional. */
export function buildEntry(args: {
  name: string
  shortLabel: string
  fullLabel?: string
  /** Marca o endpoint como advisory: vazio nao bloqueia analise. */
  advisory?: boolean
  day?: CoverageDay
}): CoverageStripEntry {
  const { name, shortLabel, fullLabel, advisory, day } = args
  if (!day) {
    return {
      name,
      shortLabel,
      fullLabel,
      advisory,
      health: "na",
    }
  }
  return {
    name,
    shortLabel,
    fullLabel,
    advisory,
    health: deriveHealth(day.status, day.tolerance_state, day.completeness),
    raw: {
      status: day.status,
      completeness: day.completeness,
      toleranceState: day.tolerance_state,
      httpStatus: day.http_status,
    },
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Componente
// ─────────────────────────────────────────────────────────────────────────────

export function QiTechCoverageStrip({
  date,
  entries,
  onBackfill,
  activeJobs,
  loading = false,
  className,
}: QiTechCoverageStripProps) {
  const [forceExpand, setForceExpand] = React.useState(false)

  const allHealthy = React.useMemo(
    () => entries.length > 0 && entries.every(isEntryHealthy),
    [entries],
  )

  const counts = React.useMemo(() => {
    const map: Record<DataHealth, number> = {
      ready: 0,
      may_change: 0,
      in_progress: 0,
      blocked: 0,
      na: 0,
    }
    for (const e of entries) map[e.health]++
    return map
  }, [entries])

  // Quando ha bloqueante OU user clicou pra expandir, mostra strip completo.
  const expanded = forceExpand || !allHealthy

  // ── Skeleton ────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div
        className={cx(
          "flex h-7 animate-pulse items-center gap-1.5 rounded border px-2",
          "border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900",
          className,
        )}
      >
        <RiLoader4Line className="size-3.5 animate-spin text-gray-400" aria-hidden="true" />
        <span className="text-[11px] text-gray-500 dark:text-gray-400">
          Carregando saude dos reports…
        </span>
      </div>
    )
  }

  // ── Pill colapsada (8/8 prontos) ───────────────────────────────────────
  if (!expanded) {
    const total = entries.length
    const okCount = counts.ready + counts.may_change
    const hasMayChange = counts.may_change > 0
    return (
      <button
        type="button"
        onClick={() => setForceExpand(true)}
        className={cx(
          "group inline-flex items-center gap-1.5 rounded border px-2 py-1 text-[11px] transition-colors",
          "border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100",
          "dark:border-emerald-900/40 dark:bg-emerald-500/10 dark:text-emerald-300 dark:hover:bg-emerald-500/15",
          className,
        )}
        aria-label="Expandir saude dos reports QiTech"
      >
        <RiCheckLine className="size-3.5 shrink-0" aria-hidden="true" />
        <span className="font-medium">
          {okCount}/{total} reports prontos
        </span>
        <span className="text-emerald-600/80 dark:text-emerald-400/80">
          · {formatBR(date)}
        </span>
        {hasMayChange && (
          <span className="ml-1 rounded-sm bg-amber-100 px-1 text-[10px] font-medium text-amber-700 dark:bg-amber-500/15 dark:text-amber-300">
            {counts.may_change} pode mudar
          </span>
        )}
        <RiArrowRightSLine
          className="size-3.5 shrink-0 text-emerald-500 transition-transform group-hover:translate-x-0.5 dark:text-emerald-400"
          aria-hidden="true"
        />
      </button>
    )
  }

  // ── Strip expandido ─────────────────────────────────────────────────────
  return (
    <div
      className={cx(
        "flex flex-wrap items-center gap-1.5 rounded border px-2 py-1.5",
        "border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
        className,
      )}
      role="group"
      aria-label={`Saude dos reports QiTech para ${formatBR(date)}`}
    >
      <span className="mr-1 text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-500 dark:text-gray-400">
        Reports · {formatBR(date)}
      </span>

      {entries.map((entry) => (
        <EntryChip
          key={entry.name}
          entry={entry}
          inProgressJob={activeJobs?.has(entry.name) ?? false}
          onBackfill={onBackfill}
        />
      ))}

      {/* Resumo */}
      <div className="ml-auto flex items-center gap-2 text-[11px] text-gray-500 dark:text-gray-400">
        {counts.blocked > 0 && (
          <span className="inline-flex items-center gap-1 text-red-700 dark:text-red-300">
            <RiAlertLine className="size-3.5" aria-hidden="true" />
            {counts.blocked} bloqueado
          </span>
        )}
        {counts.in_progress > 0 && (
          <span className="inline-flex items-center gap-1 text-blue-700 dark:text-blue-300">
            <RiTimeLine className="size-3.5" aria-hidden="true" />
            {counts.in_progress} em curso
          </span>
        )}
        {allHealthy && (
          <button
            type="button"
            onClick={() => setForceExpand(false)}
            className="text-[11px] text-gray-500 hover:underline dark:text-gray-400"
          >
            Recolher
          </button>
        )}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// EntryChip — chip individual com Popover de detalhes
// ─────────────────────────────────────────────────────────────────────────────

function EntryChip({
  entry,
  inProgressJob,
  onBackfill,
}: {
  entry: CoverageStripEntry
  inProgressJob: boolean
  onBackfill?: (endpointName: string) => void
}) {
  const style = HEALTH_STYLES[entry.health]
  const isUnhealthy =
    entry.health === "in_progress" ||
    entry.health === "blocked" ||
    entry.health === "na"
  // "Advisory degradado" = endpoint que pode legitimamente ficar vazio E
  // hoje esta em estado nao-saudavel. Tratamos visualmente como neutro
  // (dashed cinza) pra nao parecer erro — mas mantemos o canBackfill caso
  // o usuario queira forcar (vai ser zero real se nao tinha operacao).
  const isAdvisoryDegraded = !!entry.advisory && isUnhealthy
  const canBackfill = !!onBackfill && isUnhealthy && !inProgressJob

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cx(
            "inline-flex h-[24px] items-center gap-1.5 rounded border px-2 text-[11px] font-medium transition-colors",
            isAdvisoryDegraded
              ? "border-dashed border-gray-300 bg-white hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-950 dark:hover:bg-gray-900"
              : cx(
                  "border-gray-200 bg-white hover:bg-gray-50",
                  "dark:border-gray-800 dark:bg-gray-950 dark:hover:bg-gray-900",
                  entry.health === "blocked" &&
                    "border-red-200 dark:border-red-900/40",
                ),
          )}
          aria-label={`${entry.shortLabel}: ${style.label}${isAdvisoryDegraded ? " (advisory)" : ""}`}
        >
          <span
            className={cx(
              "inline-block size-1.5 rounded-full",
              isAdvisoryDegraded
                ? "bg-gray-300 dark:bg-gray-600"
                : style.bg,
              inProgressJob && "animate-pulse",
            )}
            aria-hidden="true"
          />
          <span
            className={cx(
              isAdvisoryDegraded
                ? "text-gray-500 dark:text-gray-400"
                : "text-gray-700 dark:text-gray-200",
            )}
          >
            {entry.shortLabel}
          </span>
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" sideOffset={6} className="w-72 p-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="flex items-center gap-1.5">
              <span className="text-[13px] font-semibold text-gray-900 dark:text-gray-50">
                {entry.fullLabel ?? entry.shortLabel}
              </span>
              {entry.advisory && (
                <span className="inline-flex items-center rounded-sm bg-gray-100 px-1.5 py-0.5 text-[9.5px] font-semibold uppercase tracking-[0.05em] text-gray-600 dark:bg-gray-800 dark:text-gray-300">
                  Advisory
                </span>
              )}
            </div>
            <div className="mt-0.5 text-[11px] text-gray-500 dark:text-gray-400 font-mono">
              {entry.name}
            </div>
          </div>
          <span
            className={cx(
              "shrink-0 inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.04em]",
              isAdvisoryDegraded
                ? "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300"
                : healthBadgeStyle(entry.health),
            )}
          >
            <span
              className={cx(
                "inline-block size-1.5 rounded-full",
                isAdvisoryDegraded
                  ? "bg-gray-300 dark:bg-gray-600"
                  : style.bg,
              )}
              aria-hidden="true"
            />
            {isAdvisoryDegraded ? "sem dado" : style.label}
          </span>
        </div>

        <p className="mt-2 text-[12px] leading-snug text-gray-600 dark:text-gray-300">
          {isAdvisoryDegraded
            ? "Este endpoint pode ficar vazio em dias normais (so existe quando ha operacao naquela natureza). Nao bloqueia a analise da Cota Sub — o driver correspondente exibe zero quando nao ha posicao."
            : style.description}
        </p>

        {entry.raw && (
          <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
            <dt className="text-gray-500 dark:text-gray-400">Status</dt>
            <dd className="font-mono text-gray-700 dark:text-gray-200">
              {entry.raw.status}
            </dd>
            <dt className="text-gray-500 dark:text-gray-400">Completeness</dt>
            <dd className="font-mono text-gray-700 dark:text-gray-200">
              {entry.raw.completeness ?? "—"}
            </dd>
            <dt className="text-gray-500 dark:text-gray-400">Tolerance</dt>
            <dd className="font-mono text-gray-700 dark:text-gray-200">
              {entry.raw.toleranceState ?? "—"}
            </dd>
            <dt className="text-gray-500 dark:text-gray-400">HTTP</dt>
            <dd className="font-mono text-gray-700 dark:text-gray-200">
              {entry.raw.httpStatus ?? "—"}
            </dd>
          </dl>
        )}

        {inProgressJob && (
          <div className="mt-3 inline-flex items-center gap-1.5 text-[11px] text-blue-700 dark:text-blue-300">
            <RiLoader4Line className="size-3.5 animate-spin" aria-hidden="true" />
            Sync em curso…
          </div>
        )}

        {canBackfill && (
          <div className="mt-3 flex justify-end">
            <Button
              variant="secondary"
              className="h-7 px-2.5 text-[12px]"
              onClick={() => onBackfill?.(entry.name)}
            >
              <RiPlayLine className="size-3.5" aria-hidden="true" />
              Forcar sync
            </Button>
          </div>
        )}
      </PopoverContent>
    </Popover>
  )
}

function healthBadgeStyle(h: DataHealth): string {
  switch (h) {
    case "ready":
      return "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
    case "may_change":
      return "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300"
    case "in_progress":
      return "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
    case "blocked":
      return "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300"
    case "na":
      return "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"
  }
}

function formatBR(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  if (!m) return iso
  return `${m[3]}/${m[2]}/${m[1]}`
}
