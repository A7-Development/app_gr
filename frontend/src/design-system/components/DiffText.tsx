// src/design-system/components/DiffText.tsx
//
// Diff de edição humana — a ÚNICA linguagem de edição do produto
// (bancada, conferência e parecer — handoff Conceito D):
//   removido = line-through + text-faint
//   inserido = fundo gray-100 + border-bottom 2px double gray-800 + pena
//
// Ajuste do analista sempre preserva o valor anterior: `42 dias ~~38~~`.

import * as React from "react"
import { RiQuillPenLine } from "@remixicon/react"

import { cx } from "@/lib/utils"

export function DiffRemoved({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <span className={cx("text-gray-400 line-through dark:text-gray-600", className)}>
      {children}
    </span>
  )
}

export function DiffInserted({
  children,
  className,
  showPen = true,
}: {
  children: React.ReactNode
  className?: string
  /** Ícone de pena adjacente (default true — assinatura do analista). */
  showPen?: boolean
}) {
  return (
    <>
      <span
        className={cx(
          "bg-gray-100 px-0.5 dark:bg-gray-800",
          className,
        )}
        style={{ borderBottom: "2px double var(--diff-inserted-line, #1F2937)" }}
      >
        {children}
      </span>
      {showPen && (
        <RiQuillPenLine
          className="ml-0.5 inline size-[13px] align-[-1px] text-gray-800 dark:text-gray-200"
          aria-label="ajustado pelo analista"
        />
      )}
    </>
  )
}

/** Valor anterior preservado ao lado do novo: `42 dias ~~38~~`. */
export function PreviousValue({ children }: { children: React.ReactNode }) {
  return (
    <span className="ml-1 text-[12px] font-normal text-gray-400 line-through dark:text-gray-600">
      {children}
    </span>
  )
}
