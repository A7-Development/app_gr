// src/design-system/components/DataTable/cells/index.tsx
// Typed cell renderers for FIDC domain columns.

"use client"

import * as React from "react"
import * as HoverCardPrimitive from "@radix-ui/react-hover-card"
import * as TooltipPrimitive from "@radix-ui/react-tooltip"
import {
  RiFileCopyLine,
  RiCheckLine,
  RiExternalLinkLine,
} from "@remixicon/react"
import { cx } from "@/lib/utils"
import { StatusPill } from "@/design-system/components/StatusPill"
import { Sparkline } from "@/design-system/components/KpiStrip"
import type { StatusKey } from "@/design-system/tokens"
import { tableTokens } from "@/design-system/tokens/table"

function useCopy(text: string) {
  const [copied, setCopied] = React.useState(false)
  const copy = React.useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }, [text])
  return { copied, copy }
}

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
})

export function CurrencyCell({ value }: { value: number | null | undefined }) {
  if (value == null) return <span className={tableTokens.cellMuted}>—</span>
  const negative = value < 0
  return (
    <span
      className={cx(
        negative ? tableTokens.cellNumberSecondary : tableTokens.cellNumber,
        "font-medium text-right",
      )}
    >
      {negative ? `(${fmtBRL.format(Math.abs(value))})` : fmtBRL.format(value)}
    </span>
  )
}

export function PercentageCell({
  value,
  decimals = 2,
}: {
  value:     number | null | undefined
  decimals?: number
}) {
  if (value == null) return <span className={tableTokens.cellMuted}>—</span>
  return (
    <span className={tableTokens.cellNumber}>
      {value.toLocaleString("pt-BR", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}%
    </span>
  )
}

function relativeDate(isoDate: string): string {
  const diff = Math.floor((Date.now() - new Date(isoDate).getTime()) / 86_400_000)
  if (diff === 0) return "hoje"
  if (diff === 1) return "ontem"
  if (diff < 30)  return `há ${diff} dias`
  if (diff < 365) return `há ${Math.floor(diff / 30)} meses`
  return `há ${Math.floor(diff / 365)} anos`
}

function absoluteDate(isoDate: string): string {
  const [y, m, d] = isoDate.split("T")[0].split("-")
  return `${d}/${m}/${y}`
}

export function DateCell({
  value,
  format = "relative",
}: {
  value:   string | null | undefined
  format?: "relative" | "absolute"
}) {
  if (!value) return <span className={tableTokens.cellMuted}>—</span>

  const display = format === "relative" ? relativeDate(value) : absoluteDate(value)
  const tooltip = absoluteDate(value)

  return (
    <TooltipPrimitive.Provider delayDuration={400}>
      <TooltipPrimitive.Root>
        <TooltipPrimitive.Trigger asChild>
          <span className={cx(tableTokens.cellNumberSecondary, "cursor-default")}>{display}</span>
        </TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content
            className="z-50 rounded bg-gray-900 px-2 py-1 text-xs text-white shadow-lg dark:bg-gray-800"
            sideOffset={4}
          >
            {tooltip}
            <TooltipPrimitive.Arrow className="fill-gray-900 dark:fill-gray-800" />
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  )
}

export function StatusCell({ value }: { value: StatusKey }) {
  return <StatusPill status={value} />
}

export function IdCell({ value, maxLen = 16 }: { value: string; maxLen?: number }) {
  const { copied, copy } = useCopy(value)
  const truncated = value.length > maxLen ? `${value.slice(0, maxLen)}…` : value

  return (
    <TooltipPrimitive.Provider delayDuration={300}>
      <TooltipPrimitive.Root>
        <TooltipPrimitive.Trigger asChild>
          <button
            type="button"
            onClick={copy}
            className={cx(
              "group inline-flex items-center gap-1 tabular-nums",
              tableTokens.cellTextMono,
              // Override cor: blue indica "clicavel/copiavel" (semantica de acao).
              "!text-blue-600 dark:!text-blue-400 hover:underline",
            )}
          >
            {truncated}
            {copied
              ? <RiCheckLine className="size-3 text-emerald-500" />
              : <RiFileCopyLine className="size-3 opacity-0 group-hover:opacity-100 text-gray-400 transition-opacity" />
            }
          </button>
        </TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content
            className="z-50 rounded bg-gray-900 px-2 py-1 font-mono text-xs text-white shadow-lg dark:bg-gray-800"
            sideOffset={4}
          >
            {value}
            <TooltipPrimitive.Arrow className="fill-gray-900 dark:fill-gray-800" />
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  )
}

function fmtDoc(raw: string): string {
  const d = raw.replace(/\D/g, "")
  if (d.length === 11) return d.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4")
  if (d.length === 14) return d.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, "$1.$2.$3/$4-$5")
  return raw
}

export function CpfCnpjCell({ value }: { value: string }) {
  const { copied, copy } = useCopy(value)
  const formatted = fmtDoc(value)
  return (
    <button
      type="button"
      onClick={copy}
      title={copied ? "Copiado!" : "Clique para copiar"}
      className={cx(
        "group inline-flex items-center gap-1 tabular-nums tracking-[0.02em]",
        tableTokens.cellTextMono,
        "hover:text-blue-600 dark:hover:text-blue-400",
      )}
    >
      {formatted}
      {copied
        ? <RiCheckLine className="size-3 text-emerald-500" />
        : <RiFileCopyLine className="size-3 opacity-0 group-hover:opacity-100 text-gray-400 transition-opacity" />
      }
    </button>
  )
}

interface RelationshipMeta {
  label:        string
  href?:        string
  description?: string
  badge?:       string
}

export function RelationshipCell({
  value,
  meta,
}: {
  value: string
  meta?: RelationshipMeta
}) {
  if (!meta) {
    return <span className={tableTokens.cellText}>{value}</span>
  }

  return (
    <HoverCardPrimitive.Root openDelay={400} closeDelay={100}>
      <HoverCardPrimitive.Trigger asChild>
        <a
          href={meta.href ?? "#"}
          onClick={(e) => !meta.href && e.preventDefault()}
          className={cx(
            "inline-flex items-center gap-1",
            tableTokens.cellText,
            // Override cor: blue indica "clicavel" (link semantica).
            "!text-blue-600 dark:!text-blue-400 hover:underline",
          )}
        >
          {value}
          {meta.href && <RiExternalLinkLine className="size-3 shrink-0 opacity-60" aria-hidden="true" />}
        </a>
      </HoverCardPrimitive.Trigger>
      <HoverCardPrimitive.Portal>
        <HoverCardPrimitive.Content
          side="top"
          align="start"
          sideOffset={6}
          className={cx(
            "z-50 w-64 rounded border p-3 shadow-lg",
            "border-gray-200 dark:border-gray-800",
            "bg-white dark:bg-[#090E1A]",
            "animate-slide-up-and-fade",
          )}
        >
          <div className="flex items-start justify-between gap-2">
            <p className="text-sm font-semibold text-gray-900 dark:text-gray-50">{meta.label}</p>
            {meta.badge && (
              <span className="shrink-0 rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                {meta.badge}
              </span>
            )}
          </div>
          {meta.description && (
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{meta.description}</p>
          )}
          <HoverCardPrimitive.Arrow className="fill-gray-200 dark:fill-gray-800" />
        </HoverCardPrimitive.Content>
      </HoverCardPrimitive.Portal>
    </HoverCardPrimitive.Root>
  )
}

export function SparklineCell({
  data,
  color = "#3B82F6",
}: {
  data:   number[]
  color?: string
}) {
  return (
    <div className="w-[60px]">
      <Sparkline data={data} color={color} height={24} />
    </div>
  )
}

export function ProgressCell({
  value,
  max = 100,
  color = "bg-blue-500",
}: {
  value:  number
  max?:   number
  color?: string
}) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100))
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
        <div
          className={cx("h-full rounded-full transition-[width] duration-300", color)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-8 shrink-0 text-right text-[11px] tabular-nums text-gray-500 dark:text-gray-400">
        {Math.round(pct)}%
      </span>
    </div>
  )
}

/**
 * Cell renderer "X de Y etapas" para listagens de processos multi-step
 * (ex.: dossie de credito). Mostra barra fina + texto "4/8" + tooltip com
 * legenda da proxima acao. Cor adapta ao status agregado:
 *   - "draft" / "blocked" -> cinza
 *   - "in_progress"       -> blue (atencao)
 *   - "finalized"         -> emerald
 *   - "failed"            -> red
 */
export function StepProgressCell({
  completed,
  total,
  state = "in_progress",
  tooltip,
}: {
  completed: number
  total:     number
  state?:    "draft" | "in_progress" | "finalized" | "failed"
  tooltip?:  string
}) {
  const safeTotal = Math.max(0, total)
  const safeCompleted = Math.max(0, Math.min(completed, safeTotal))
  const pct =
    safeTotal === 0 ? 0 : Math.round((safeCompleted / safeTotal) * 100)

  const fillClass =
    state === "finalized"
      ? "bg-emerald-500"
      : state === "failed"
        ? "bg-red-500"
        : state === "draft"
          ? "bg-gray-300 dark:bg-gray-700"
          : "bg-blue-500"

  const inner = (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
        <div
          className={cx("h-full rounded-full transition-[width] duration-300", fillClass)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={cx(tableTokens.cellNumberSecondary, "shrink-0")}>
        {safeCompleted}/{safeTotal}
      </span>
    </div>
  )

  if (!tooltip) return inner

  return (
    <TooltipPrimitive.Provider delayDuration={300}>
      <TooltipPrimitive.Root>
        <TooltipPrimitive.Trigger asChild>
          <div className="cursor-help">{inner}</div>
        </TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content
            side="top"
            sideOffset={6}
            className={cx(
              "z-50 max-w-[260px] rounded border px-2.5 py-1.5 text-xs shadow-lg",
              "border-gray-200 bg-white text-gray-900",
              "dark:border-gray-800 dark:bg-[#090E1A] dark:text-gray-50",
            )}
          >
            {tooltip}
            <TooltipPrimitive.Arrow className="fill-gray-200 dark:fill-gray-800" />
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  )
}

/**
 * Cell renderer "Proxima acao" para listagens de processos multi-step.
 * Compacto: pequeno ponto colorido + label pt-BR.
 *
 * Cores espelham os 5 estados de NextActionKind do backend:
 *   - human_input        -> amber  (precisa de voce)
 *   - agent_running      -> blue   (IA trabalhando)
 *   - blocked            -> slate  (aguardando dependencia)
 *   - ready_to_finalize  -> emerald (pronto)
 *   - finalized          -> gray   (concluido)
 */
export type NextActionKind =
  | "human_input"
  | "agent_running"
  | "blocked"
  | "ready_to_finalize"
  | "finalized"

const NEXT_ACTION_DOT: Record<NextActionKind, string> = {
  human_input: "bg-amber-500",
  agent_running: "bg-blue-500",
  blocked: "bg-slate-400 dark:bg-slate-500",
  ready_to_finalize: "bg-emerald-500",
  finalized: "bg-gray-300 dark:bg-gray-600",
}

const NEXT_ACTION_TEXT: Record<NextActionKind, string> = {
  human_input: "text-amber-700 dark:text-amber-300",
  agent_running: "text-blue-700 dark:text-blue-300",
  blocked: "text-gray-600 dark:text-gray-400",
  ready_to_finalize: "text-emerald-700 dark:text-emerald-400",
  finalized: "text-gray-500 dark:text-gray-500",
}

export function NextActionCell({
  kind,
  label,
}: {
  kind:  NextActionKind
  label: string
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span
        aria-hidden
        className={cx(
          "size-2 shrink-0 rounded-full",
          NEXT_ACTION_DOT[kind],
          kind === "agent_running" && "animate-pulse",
        )}
      />
      <span className={cx(tableTokens.cellText, NEXT_ACTION_TEXT[kind])}>
        {label}
      </span>
    </div>
  )
}
