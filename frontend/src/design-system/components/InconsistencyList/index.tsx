// src/design-system/components/InconsistencyList/index.tsx
//
// Lista de inconsistencias detectadas pelo `cross_reference_analyst`.
// Cada item: severidade colorida + titulo + descricao + chips dos steps
// envolvidos (clicaveis pra navegar) + (opcional) evidencia.
//
// Hidden completamente quando lista vazia — quem decide se mostra ou nao
// e o caller (EvidencePanel oculta a secao se count === 0).

"use client"

import * as React from "react"
import {
  RiAlertLine,
  RiErrorWarningLine,
  RiInformationLine,
} from "@remixicon/react"

import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

export type InconsistencySeverity = "high" | "medium" | "info"

export type InconsistencyItem = {
  id: string
  severity: InconsistencySeverity
  title: string
  description: string
  /** node_ids envolvidos. Renderizados como chips clicaveis. */
  involved_node_ids?: string[]
  /** Mapa node_id -> label legivel (caller passa baseado no graph). */
  node_labels?: Record<string, string>
  /** Evidencia textual opcional (ex.: "Faturamento DRE R$ 5M vs balanco R$ 3M"). */
  evidence?: string | null
}

export type InconsistencyListProps = {
  items: InconsistencyItem[]
  /** Click num chip de step — caller geralmente atualiza ?step=<nodeId>. */
  onStepClick?: (nodeId: string) => void
  className?: string
}

const SEVERITY_META: Record<
  InconsistencySeverity,
  {
    label: string
    icon: typeof RiAlertLine
    container: string
    badge: string
    iconClass: string
  }
> = {
  high: {
    label: "Alta",
    icon: RiErrorWarningLine,
    container:
      "border-red-200 bg-red-50/50 dark:border-red-500/30 dark:bg-red-500/5",
    badge:
      "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",
    iconClass: "text-red-500",
  },
  medium: {
    label: "Media",
    icon: RiAlertLine,
    container:
      "border-amber-200 bg-amber-50/50 dark:border-amber-500/30 dark:bg-amber-500/5",
    badge:
      "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
    iconClass: "text-amber-500",
  },
  info: {
    label: "Informativo",
    icon: RiInformationLine,
    container:
      "border-gray-200 bg-gray-50/50 dark:border-gray-800 dark:bg-gray-900/30",
    badge:
      "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
    iconClass: "text-gray-500 dark:text-gray-400",
  },
}

export function InconsistencyList({
  items,
  onStepClick,
  className,
}: InconsistencyListProps) {
  if (items.length === 0) return null

  // Ordena: high primeiro, depois medium, depois info.
  const sorted = [...items].sort((a, b) => {
    const order: Record<InconsistencySeverity, number> = {
      high: 0,
      medium: 1,
      info: 2,
    }
    return order[a.severity] - order[b.severity]
  })

  return (
    <ul className={cx("space-y-2", className)}>
      {sorted.map((item) => {
        const meta = SEVERITY_META[item.severity]
        const Icon = meta.icon
        return (
          <li
            key={item.id}
            className={cx(
              "flex gap-2 rounded-md border p-3",
              meta.container,
            )}
          >
            <Icon
              className={cx("mt-0.5 size-4 shrink-0", meta.iconClass)}
              aria-hidden
            />
            <div className="min-w-0 flex-1 space-y-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {item.title}
                </span>
                <span className={cx(tableTokens.badge, meta.badge)}>
                  {meta.label}
                </span>
              </div>
              <p className="text-xs text-gray-700 dark:text-gray-300">
                {item.description}
              </p>
              {item.evidence && (
                <p className="text-[11px] italic text-gray-500 dark:text-gray-500">
                  Evidencia: {item.evidence}
                </p>
              )}
              {item.involved_node_ids && item.involved_node_ids.length > 0 && (
                <div className="flex flex-wrap items-center gap-1 pt-0.5">
                  <span className={tableTokens.cellSecondary}>Etapas:</span>
                  {item.involved_node_ids.map((nodeId) => {
                    const label = item.node_labels?.[nodeId] ?? nodeId
                    const isClickable = Boolean(onStepClick)
                    return (
                      // MOTIVO: <button> cru — chip pequeno; Button Tremor
                      // teria padding default que infla o visual de chip.
                      <button
                        key={nodeId}
                        type="button"
                        onClick={
                          isClickable ? () => onStepClick?.(nodeId) : undefined
                        }
                        disabled={!isClickable}
                        className={cx(
                          "inline-flex items-center rounded border px-1.5 py-0.5 text-[11px] font-medium",
                          "border-gray-200 bg-white text-gray-700",
                          "dark:border-gray-700 dark:bg-gray-950 dark:text-gray-300",
                          isClickable
                            ? "cursor-pointer hover:border-blue-500 hover:text-blue-700 dark:hover:border-blue-500 dark:hover:text-blue-300"
                            : "cursor-default",
                        )}
                        aria-label={`Ir para etapa ${label}`}
                      >
                        {label}
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          </li>
        )
      })}
    </ul>
  )
}
