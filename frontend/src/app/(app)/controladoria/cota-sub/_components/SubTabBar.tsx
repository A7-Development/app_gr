"use client"

/**
 * SubTabBar — segmented control L3.5 (sub-tab dentro da aba "Eventos do dia").
 *
 * Inspirado no handoff (variant-b). Alterna entre:
 *
 *   [Resumo narrativo]  [Detalhe contábil (COSIF · N contas)]
 *
 * E uma divisao VISUAL dentro de uma unica L3 (Eventos do dia) — nao
 * conflita com a regra de 3 niveis (§11.6 do CLAUDE.md) porque nao
 * introduz uma 4a camada de navegacao; e um toggle de modo dentro da
 * aba (filtro de view), como o segment control que ja usamos em listagens
 * CRUD via `<SegmentSwitch>`.
 */

import * as React from "react"
import { RiSparklingLine, RiTableLine } from "@remixicon/react"

import { cx, focusRing } from "@/lib/utils"

export type SubTabKey = "resumo" | "detalhe"

export type SubTabBarProps = {
  value:    SubTabKey
  onChange: (next: SubTabKey) => void
  /** Total de contas folhas (nivel >= 3) — exibido no badge do tab "Detalhe contabil". */
  contasCount?: number
  /** Texto a direita (ex.: "Ultima atualizacao: ha 4 min · QiTech"). */
  trailing?: React.ReactNode
}

export function SubTabBar({
  value,
  onChange,
  contasCount,
  trailing,
}: SubTabBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div
        role="tablist"
        className="inline-flex gap-0.5 rounded-md bg-gray-100 p-[3px] dark:bg-gray-900"
      >
        <SegmentButton
          active={value === "resumo"}
          onClick={() => onChange("resumo")}
          icon={
            <RiSparklingLine
              className={cx(
                "size-3.5 shrink-0",
                value === "resumo"
                  ? "text-blue-700 dark:text-blue-300"
                  : "text-gray-500 dark:text-gray-400",
              )}
              aria-hidden="true"
            />
          }
        >
          Resumo narrativo
        </SegmentButton>
        <SegmentButton
          active={value === "detalhe"}
          onClick={() => onChange("detalhe")}
          icon={
            <RiTableLine
              className={cx(
                "size-3.5 shrink-0",
                value === "detalhe"
                  ? "text-blue-700 dark:text-blue-300"
                  : "text-gray-500 dark:text-gray-400",
              )}
              aria-hidden="true"
            />
          }
        >
          Detalhe contábil
          {contasCount != null && (
            <span className="ml-1 font-normal text-gray-400 dark:text-gray-600">
              (COSIF · {contasCount} contas)
            </span>
          )}
        </SegmentButton>
      </div>

      {trailing && (
        <span className="ml-auto text-[11px] text-gray-500 dark:text-gray-400">
          {trailing}
        </span>
      )}
    </div>
  )
}

function SegmentButton({
  active,
  onClick,
  icon,
  children,
}: {
  active:   boolean
  onClick:  () => void
  icon?:    React.ReactNode
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cx(
        "inline-flex items-center gap-1.5 rounded px-3 py-1 text-[12.5px] font-medium leading-tight transition-colors",
        active
          ? "bg-white text-gray-900 shadow-[0_1px_2px_rgba(15,23,42,0.06)] dark:bg-gray-800 dark:text-gray-50"
          : "text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-200",
        focusRing,
      )}
    >
      {icon}
      {children}
    </button>
  )
}
